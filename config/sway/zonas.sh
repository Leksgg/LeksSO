#!/bin/sh
# Monta las zonas de LeksSO: centro (explorador + apps y terminal como pestañas) | panel de IA.
# Las apps que abra el usuario van siempre a la zona central.
# Uso: leksso-zonas              monta las zonas al iniciar la sesión
#      leksso-zonas --restaurar  vuelve a la vista por defecto sin cerrar las apps del usuario
#      leksso-zonas --plegar     pliega o despliega la columna de carpetas (más sitio para la app)
#      leksso-zonas --explorador cierra y vuelve a abrir el explorador en su sitio (para que estrene los iconos de la apariencia nueva)
#      leksso-zonas --medir      muestra los tamaños actuales de las zonas (en % de la pantalla)
#      leksso-zonas --guardar    guarda ahora los tamaños actuales (normalmente se hace solo cada 15 s)
#      leksso-zonas --fabrica    vuelve a los tamaños de fábrica (sin cerrar ni mover ventanas)
#
# Los tamaños de las zonas que dejes a tu gusto (arrastrando los bordes) se guardan solos en
# ~/.config/leksso/zonas y se vuelven a poner al iniciar sesión y al restaurar las zonas. Con --fabrica
# (o Ajustes, Zonas del escritorio) se borran y se vuelve a los de fábrica.

# Si se lanzó sin el socket de sway (p. ej. desde una barra reiniciada a mano), lo busca.
if [ -z "${SWAYSOCK:-}" ]; then
  SWAYSOCK="$(ls "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"/sway-ipc.*.sock 2>/dev/null | tail -1)"; export SWAYSOCK
fi

PLEGADO="${XDG_RUNTIME_DIR:-/tmp}/leksso-carpetas.plegado"
MONTANDO="${XDG_RUNTIME_DIR:-/tmp}/leksso-zonas.montando"
TAMANOS="$HOME/.config/leksso/zonas"

# Tamaños de las zonas en % (explorador y panel de IA, de ancho; terminal, de alto). Los guardados por el usuario
# mandan; los valores que no son un número entre 10 y 70 se ignoran.
cargar() {
  EXPL=22; PANEL=26; TERM=26
  [ -r "$TAMANOS" ] || return 0
  while IFS='=' read -r k v; do
    case "$v" in ''|*[!0-9]*) continue ;; esac
    [ "$v" -ge 10 ] && [ "$v" -le 70 ] || continue
    case "$k" in explorador) EXPL=$v ;; panel) PANEL=$v ;; terminal) TERM=$v ;; esac
  done < "$TAMANOS"
}

# Tamaños actuales ("explorador=22 panel=26 terminal=26"): solo las zonas que existen y no están plegadas.
medir() {
  swaymsg -t get_tree 2>/dev/null | python3 -c '
import json, sys
try:
    t = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
def walk(n, par=None):
    yield n, par
    for c in n.get("nodes", []) + n.get("floating_nodes", []):
        yield from walk(c, n)
ws = next((n for n, _ in walk(t) if n.get("type") == "workspace" and n.get("name") == "1"), None)
if ws is None:
    sys.exit(0)
r = {}
for n, p in walk(ws):
    m = n.get("marks", [])
    if "explorador" in m: r["explorador"] = round(100 * n["rect"]["width"] / ws["rect"]["width"])
    if "panel-ia" in m: r["panel"] = round(100 * n["rect"]["width"] / ws["rect"]["width"])
    if "terminal" in m and p: r["terminal"] = round(100 * n["rect"]["height"] / p["rect"]["height"])
print(" ".join("%s=%d" % kv for kv in r.items()))
'
}

# Guarda los tamaños si el usuario los ha cambiado (solo valores entre 10 y 70, para no guardar un estado roto).
guardar() {
  [ -e "$MONTANDO" ] && return 0
  cargar
  actual="explorador=$EXPL panel=$PANEL terminal=$TERM"
  for par in $(medir); do
    k="${par%%=*}"; v="${par#*=}"
    case "$v" in ''|*[!0-9]*) continue ;; esac
    [ "$v" -ge 10 ] && [ "$v" -le 70 ] || continue
    # un punto de diferencia es solo el redondeo al medir: no cuenta como cambio del usuario
    case "$k" in explorador) ant=$EXPL ;; panel) ant=$PANEL ;; terminal) ant=$TERM ;; *) continue ;; esac
    dif=$((v - ant)); [ "$dif" -lt 0 ] && dif=$((0 - dif)); [ "$dif" -ge 2 ] || continue
    case "$k" in explorador) EXPL=$v ;; panel) PANEL=$v ;; terminal) TERM=$v ;; esac
  done
  [ "explorador=$EXPL panel=$PANEL terminal=$TERM" = "$actual" ] && return 0
  mkdir -p "$(dirname "$TAMANOS")"
  printf 'explorador=%s\npanel=%s\nterminal=%s\n' "$EXPL" "$PANEL" "$TERM" > "$TAMANOS.nuevo" && mv -f "$TAMANOS.nuevo" "$TAMANOS"
}

# Vigila los tamaños mientras dure la sesión de sway (cada 15 s: sway no avisa al redimensionar).
vigilar() {
  while swaymsg -t get_version >/dev/null 2>&1; do
    sleep 15
    guardar
  done
}

# Espera a que exista una ventana que cumpla el criterio y le pone una marca.
marcar() {
  i=0
  while [ $i -lt "${3:-40}" ]; do
    swaymsg "[$1] mark --add $2" 2>/dev/null | grep -q '"success": true' && return 0
    i=$((i + 1)); sleep 0.25
  done
  return 1
}

restaurar_previo() {
  # Aparta todas las ventanas a un espacio de trabajo auxiliar (el 9) y cierra las de zona.
  swaymsg '[app_id=".*"] move container to workspace number 9' >/dev/null 2>&1
  swaymsg '[class=".*"] move container to workspace number 9' >/dev/null 2>&1
  swaymsg '[app_id="^leksso-"] kill' >/dev/null 2>&1
  swaymsg '[con_mark="explorador"] kill' >/dev/null 2>&1
  swaymsg '[con_mark="centro"] kill' >/dev/null 2>&1
  sleep 1
}

montar() {
  : > "$MONTANDO"
  cargar
  swaymsg 'workspace number 1; layout splith' >/dev/null
  rm -f "$PLEGADO"
  # Explorador completo (barra, árbol y contenido) en el centro: es lo que se ve cuando no hay ninguna app abierta.
  # El centro es un grupo de pestañas: lo que abra el usuario (y la terminal) entra como pestaña nueva.
  swaymsg exec pcmanfm-qt >/dev/null
  marcar 'app_id="pcmanfm-qt" workspace="1"' centro 160
  swaymsg exec "leksso-term -T \"Panel de la IA\" --app-id leksso-ia -e python3 /usr/local/lib/leksso-ia/panel.py" >/dev/null
  marcar 'app_id="leksso-ia"' panel-ia
  swaymsg '[con_mark="centro"] focus; splith; layout tabbed' >/dev/null
  # Terminal: otra pestaña del centro
  swaymsg '[con_mark="centro"] focus' >/dev/null
  swaymsg exec "leksso-term -T Terminal --app-id leksso-terminal" >/dev/null
  marcar 'app_id="leksso-terminal"' terminal
  swaymsg '[con_mark="terminal"] move container to mark centro' >/dev/null

  # La zona de la derecha pasa a ser un grupo de pestañas: panel de la IA y asistente
  swaymsg '[con_mark="panel-ia"] focus; splith; layout tabbed' >/dev/null

  # Proporciones (las que dejó el usuario, o las de fábrica)
  swaymsg "[con_mark=\"panel-ia\"] resize set width $PANEL ppt" >/dev/null

  # A partir de ahora, todo lo que abra el usuario va al centro (la regla se añade una sola vez)
  marca="${XDG_RUNTIME_DIR:-/tmp}/leksso-zonas.regla"
  if [ ! -e "$marca" ]; then
    # Todo lo que abre el usuario va al centro. Dos reglas, porque hay dos clases de programas: los de Wayland (tienen app_id) y los
    # de X11 (Steam y otros antiguos, por XWayland), que NO tienen app_id y antes se saltaban la regla: caían donde estuviera el foco
    # (debajo del centro o dentro del panel de la IA). Quedan fuera las zonas propias (panel de la IA, asistentes, centro, terminal)
    # y las ventanas flotantes de LeksSO. Así el panel de la IA solo recibe IA.
    swaymsg 'for_window [app_id="^(?!leksso-(ia|asistente|asistentes|centro|terminal|menu|energia|modo|calendario|dispositivos|notificaciones|redes|solicitud|remoto|pantalla|portapapeles|ajustes|actualizaciones)).*"] move container to mark centro' >/dev/null
    swaymsg 'for_window [shell="xwayland"] move container to mark centro' >/dev/null
    : > "$marca"
  fi
  swaymsg '[con_mark="centro"] focus' >/dev/null
  rm -f "$MONTANDO"
}

# El explorador guarda en memoria los iconos del tema que había al abrirlo: tras cambiar de apariencia se cierra y se
# abre de nuevo en su sitio (pestaña del centro). Lo llama leksso-tema. Los demás programas no se tocan.
reabrir_explorador() {
  pgrep -u "$(id -u)" -x pcmanfm-qt >/dev/null 2>&1 || return 0
  : > "$MONTANDO"
  swaymsg '[con_mark="centro"] focus' >/dev/null 2>&1
  swaymsg '[app_id="pcmanfm-qt"] kill' >/dev/null 2>&1
  i=0
  while [ $i -lt 20 ] && pgrep -u "$(id -u)" -x pcmanfm-qt >/dev/null 2>&1; do i=$((i + 1)); sleep 0.25; done
  swaymsg exec pcmanfm-qt >/dev/null
  marcar 'app_id="pcmanfm-qt" workspace="1"' centro 80
  swaymsg '[con_mark="centro"] focus' >/dev/null 2>&1
  rm -f "$MONTANDO"
}

plegar() {
  cargar
  if [ -e "$PLEGADO" ]; then
    # vuelve del escondite como ventana normal, se coloca junto a la columna central y pasa a su izquierda
    swaymsg '[con_mark="explorador"] scratchpad show' >/dev/null
    swaymsg '[con_mark="explorador"] floating disable' >/dev/null
    swaymsg '[con_mark="explorador"] move container to mark columna' >/dev/null
    swaymsg '[con_mark="explorador"] move left' >/dev/null
    swaymsg "[con_mark=\"explorador\"] resize set width $EXPL ppt" >/dev/null
    rm -f "$PLEGADO"
  else
    guardar    # antes de esconder la columna, se guarda el ancho que tenía
    swaymsg '[con_mark="explorador"] move scratchpad' >/dev/null && : > "$PLEGADO"
  fi
  # el sitio que se gana o se pierde es de la zona central: el panel de la IA conserva su ancho
  swaymsg "[con_mark=\"panel-ia\"] resize set width $PANEL ppt" >/dev/null
  swaymsg '[con_mark="centro"] focus' >/dev/null 2>&1
}

if [ "${1:-}" = "--plegar" ]; then
  plegar
elif [ "${1:-}" = "--fabrica" ]; then
  # Vuelve a los tamaños de fábrica sin cerrar ni mover ninguna ventana: borra lo guardado y los aplica.
  rm -f "$TAMANOS" "$TAMANOS.nuevo"
  cargar
  [ -e "$PLEGADO" ] || swaymsg "[con_mark=\"explorador\"] resize set width $EXPL ppt" >/dev/null 2>&1
  swaymsg "[con_mark=\"panel-ia\"] resize set width $PANEL ppt" >/dev/null 2>&1
  swaymsg "[con_mark=\"terminal\"] resize set height $TERM ppt" >/dev/null 2>&1
elif [ "${1:-}" = "--guardar" ]; then
  guardar
elif [ "${1:-}" = "--explorador" ]; then
  reabrir_explorador
elif [ "${1:-}" = "--medir" ]; then
  medir
elif [ "${1:-}" = "--restaurar" ]; then
  restaurar_previo
  montar
  # Devuelve las apps del usuario a la zona central
  swaymsg '[workspace="9"] move container to mark centro' >/dev/null 2>&1
  swaymsg '[con_mark="centro"] focus' >/dev/null 2>&1
else
  montar
  vigilar     # se queda en segundo plano guardando los tamaños que dejes a tu gusto
fi
