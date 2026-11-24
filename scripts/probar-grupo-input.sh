#!/usr/bin/env bash
# Prepara la decisión del hallazgo 7 de la revisión externa: ¿se puede quitar al usuario del grupo «input»?
#
# El grupo «input» da lectura de /dev/input/event*: teclados, ratones y mandos de TODOS los usuarios, también lo que
# se teclea en la pantalla de bloqueo y en sudo. sway recibe esos dispositivos a través de seatd/logind sin necesitar
# el grupo, pero hay que comprobarlo en un equipo real antes de quitarlo (si no, el escritorio arranca sin teclado).
#
# Uso (en un equipo con LeksSO, con tu usuario; usa sudo solo para simular «sin el grupo»):
#   leksso-grupo-input            diagnóstico: no cambia nada
#   sudo leksso-grupo-input quitar USUARIO     le quita el grupo (hay que cerrar sesión y volver a entrar)
#   sudo leksso-grupo-input poner USUARIO      se lo devuelve (por si algo falla)
set -u

accion="${1:-estado}"
usuario="${2:-${SUDO_USER:-$(id -un)}}"

case "$accion" in
  quitar) [ "$(id -u)" -eq 0 ] || { echo "Hace falta sudo." >&2; exit 1; }
          id -nG "$usuario" | tr ' ' '\n' | grep -qx input || { echo "$usuario ya no está en input."; exit 0; }
          gpasswd -d "$usuario" input && echo "Hecho. Cierra la sesión y vuelve a entrar; comprueba teclado, ratón, bloqueo (Super+L) y mandos." ; exit $? ;;
  poner)  [ "$(id -u)" -eq 0 ] || { echo "Hace falta sudo." >&2; exit 1; }
          usermod -aG input "$usuario" && echo "Devuelto. Cierra la sesión y vuelve a entrar."; exit $? ;;
  estado) ;;
  *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac

echo "== Estado de $usuario"
echo "Grupos: $(id -nG "$usuario")"
if id -nG "$usuario" | tr ' ' '\n' | grep -qx input; then en_input=1; echo "→ ESTÁ en el grupo input."; else en_input=0; echo "→ NO está en el grupo input."; fi
echo
echo "== Servicios de asiento y sesión"
estado_de() { local e; e="$(systemctl is-active "$1" 2>/dev/null)" || true; echo "${e:-desconocido}"; }
printf 'seatd:            %s\n' "$(estado_de seatd)"
printf 'systemd-logind:   %s\n' "$(estado_de systemd-logind)"
printf 'Sesión actual:    %s\n' "$(loginctl show-session "${XDG_SESSION_ID:-}" -p Type -p Class -p State 2>/dev/null | tr '\n' ' ')"
echo
echo "== Dispositivos de entrada y quién puede leerlos"
n=0
for ev in /dev/input/event*; do
  [ -e "$ev" ] || continue
  n=$((n + 1))
  nombre="$(cat "/sys/class/input/$(basename "$ev")/device/name" 2>/dev/null || echo '?')"
  printf '%-18s grupo=%-6s modo=%s  ACL de usuario: %s   «%s»\n' "$ev" "$(stat -c %G "$ev")" "$(stat -c %a "$ev")" \
    "$(getfacl -p "$ev" 2>/dev/null | grep -c "^user:[^:]")" "$nombre"
done
[ "$n" -gt 0 ] || echo "No hay /dev/input/event* (¿máquina virtual sin entrada?)."
echo
echo "== Simulación: ¿puede $usuario leer esos dispositivos SIN el grupo input?"
if [ "$(id -u)" -ne 0 ]; then
  echo "(para simularlo hace falta root: sudo leksso-grupo-input estado $usuario)"
else
  uid="$(id -u "$usuario")"; gid="$(id -g "$usuario")"
  grupos="$(id -G "$usuario" | tr ' ' '\n' | while read -r g; do [ "$g" = "$(getent group input | cut -d: -f3)" ] || printf '%s,' "$g"; done)"
  grupos="${grupos%,}"
  leen=0; total=0
  for ev in /dev/input/event*; do
    [ -e "$ev" ] || continue
    total=$((total + 1))
    if setpriv --reuid="$uid" --regid="$gid" --groups="${grupos:-$gid}" -- test -r "$ev" 2>/dev/null; then leen=$((leen + 1)); fi
  done
  echo "Sin el grupo, $usuario puede leer $leen de $total dispositivos."
  if [ "$total" -gt 0 ] && [ "$leen" -eq 0 ]; then
    echo "→ BIEN: quitar el grupo cierra la lectura directa. Lo que falta comprobar es que sway arranque (use «quitar»)."
  elif [ "$leen" -gt 0 ]; then
    echo "→ OJO: aun sin el grupo hay dispositivos legibles (listas de acceso por sesión o permisos abiertos)."
    echo "  Quitar el grupo no cerraría ese hueco para esos dispositivos; hay que mirar de dónde sale (getfacl)."
  fi
fi
echo
echo "== Lista de comprobación tras «quitar» (cerrar sesión y volver a entrar)"
cat <<'EOF'
  [ ] El escritorio arranca y el teclado y el ratón funcionan
  [ ] Pantalla de bloqueo: se bloquea (Super+L) y se escribe la contraseña
  [ ] Mando de juego / Steam: se reconoce (si usas uno)
  [ ] Stream Deck (leksso-streamdeck): sigue funcionando
  [ ] Dead by Daylight o el juego que uses: entrada correcta
  [ ] Wayvnc / «ver pantalla de otro equipo»: manejar ratón y teclado
  Si algo falla:  sudo leksso-grupo-input poner USUARIO  (y volver a entrar)
EOF
