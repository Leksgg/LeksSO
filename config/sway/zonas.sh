#!/bin/sh
# Monta las zonas de LeksSO: centro (explorador + apps y terminal como pestañas) | panel de IA.
# Las apps que abra el usuario van siempre a la zona central.
# Uso: leksso-zonas              monta las zonas al iniciar la sesión
#      leksso-zonas --restaurar  vuelve a la vista por defecto sin cerrar las apps del usuario
#      leksso-zonas --plegar     muestra u oculta el panel de carpetas del explorador (más sitio para la app)
#      leksso-zonas --explorador cierra y vuelve a abrir el explorador en su sitio (para que estrene los iconos de la apariencia nueva)
#      leksso-zonas --medir      muestra los tamaños actuales de las zonas (en % de la pantalla)
#      leksso-zonas --guardar    guarda ahora los tamaños actuales (normalmente se hace solo cada 15 s)
#      leksso-zonas --zona-ia [--auto]  crea la zona del panel de la IA si no existe (se crea al abrir un asistente o el panel)
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
ZONA_AUTO="${XDG_RUNTIME_DIR:-/tmp}/leksso-zona-ia.auto"    # existe si el panel lo abrió un asistente (y se cierra con el último)
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

# Crea la zona de la derecha (panel de la IA) si no existe. Con --auto la zona la abre un asistente: se cierra sola al
# cerrarse el último asistente; si la abres tú (Mod+A, la barra, un aviso), se queda hasta que la cierres.
zona_ia() {
  if swaymsg -t get_marks 2>/dev/null | grep -q '"panel-ia"'; then
    return 0
  fi
  cargar
  if swaymsg -t get_tree 2>/dev/null | grep -q '"app_id": "leksso-asistente'; then
    swaymsg '[app_id="^leksso-asistente"] focus' >/dev/null 2>&1       # ya hay asistentes sin panel: el panel entra en su zona
  else
    swaymsg '[con_mark="centro"] focus' >/dev/null 2>&1
    swaymsg 'focus parent' >/dev/null 2>&1                              # el grupo de pestañas del centro: el panel se abre a su lado
  fi
  swaymsg exec "leksso-term -T \"Panel de la IA\" --app-id leksso-ia -e python3 /usr/local/lib/leksso-ia/panel.py" >/dev/null
  marcar 'app_id="leksso-ia"' panel-ia 60 || return 0
  swaymsg '[con_mark="panel-ia"] focus; splith; layout tabbed' >/dev/null 2>&1
  swaymsg "[con_mark=\"panel-ia\"] resize set width $PANEL ppt" >/dev/null 2>&1
  if [ "${1:-}" = "--auto" ]; then : > "$ZONA_AUTO"; else rm -f "$ZONA_AUTO"; fi
}

# Si el panel lo abrió un asistente y ya no queda ninguno, cierra el panel (y con él la zona).
cerrar_zona_auto() {
  [ -e "$ZONA_AUTO" ] || return 0
  [ $(( $(date +%s) - $(stat -c %Y "$ZONA_AUTO" 2>/dev/null || echo 0) )) -gt 20 ] || return 0     # margen mientras arranca el asistente
  swaymsg -t get_tree 2>/dev/null | grep -q '"app_id": "leksso-asistente' && return 0
  swaymsg '[con_mark="panel-ia"] kill' >/dev/null 2>&1
  rm -f "$ZONA_AUTO"
}

# Vigila los tamaños mientras dure la sesión de sway (cada 15 s: sway no avisa al redimensionar) y cierra el panel
# abierto por un asistente cuando se va el último (cada 3 s, solo si hay uno pendiente de cerrar).
vigilar() {
  n=0
  while swaymsg -t get_version >/dev/null 2>&1; do
    sleep 3
    cerrar_zona_auto
    n=$((n + 1))
    if [ "$n" -ge 5 ]; then n=0; guardar; fi
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
  # El panel de la IA ya no se monta al arrancar: la zona de la derecha solo existe mientras haya un asistente abierto
  # (o el panel abierto a mano). La crea zona_ia, que llaman leksso-asistentes al lanzar uno y leksso-panel-ia (Mod+A).
  swaymsg '[con_mark="centro"] focus; splith; layout tabbed' >/dev/null
  # Terminal: otra pestaña del centro
  swaymsg '[con_mark="centro"] focus' >/dev/null
  swaymsg exec "leksso-term -T Terminal --app-id leksso-terminal" >/dev/null
  marcar 'app_id="leksso-terminal"' terminal
  swaymsg '[con_mark="terminal"] move container to mark centro' >/dev/null


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
  # Las carpetas son el panel lateral del explorador (PCManFM-Qt), que vive en la zona central: se muestra u oculta con F9.
  # Se trae el explorador al frente y se le manda esa tecla (wtype usa el protocolo de teclado virtual de sway: no hace falta
  # ningún permiso especial). Antes esto escondía una ventana «Carpetas» aparte que ya no existe, y el botón no hacía nada.
  if ! command -v wtype >/dev/null 2>&1; then
    notify-send -a LeksSO "Carpetas" "Falta la herramienta wtype. Pulsa F9 dentro del explorador para ver u ocultar las carpetas." 2>/dev/null
    swaymsg '[app_id="pcmanfm-qt"] focus' >/dev/null 2>&1
    return 0
  fi
  swaymsg '[app_id="pcmanfm-qt"] focus' >/dev/null 2>&1 || return 0
  sleep 0.15
  wtype -k F9
}

if [ "${1:-}" = "--plegar" ]; then
  plegar
elif [ "${1:-}" = "--vigilar" ]; then
  vigilar
elif [ "${1:-}" = "--zona-ia" ]; then
  zona_ia "${2:-}"
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
