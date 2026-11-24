#!/usr/bin/env bash
# Ejecuta la batería de pruebas de LeksSO y devuelve 0 solo si TODO pasa. La usa publicar-version.sh antes de firmar.
#   scripts/correr-pruebas.sh             toda la batería
#   scripts/correr-pruebas.sh rapida      sin las pruebas lentas (permisor por sockets)
# Las pruebas son de Linux (usan openat, bubblewrap, systemd). Desde Git Bash de Windows se relanza solo dentro de WSL.
# Se omiten (y se dice) las que necesitan PySide6 o bwrap si no están instalados: un equipo de desarrollo sin ellos no
# debería poder publicar «en verde» sin que se note que faltaron.
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    command -v wsl.exe >/dev/null 2>&1 || { echo "Estas pruebas necesitan Linux: instala WSL o ejecútalas en un equipo con LeksSO." >&2; exit 1; }
    ruta="$(cygpath -u "$AQUI/correr-pruebas.sh" | sed -E 's#^/([a-zA-Z])/#/mnt/\L\1/#')"
    MSYS_NO_PATHCONV=1 exec wsl.exe -e bash "$ruta" "$@" ;;
esac

RAIZ="$(dirname "$AQUI")"
RAPIDA=0; [ "${1:-}" = "rapida" ] && RAPIDA=1
fallos=0; omitidas=0; total=0
LOG="$(mktemp)"; trap 'rm -f "$LOG"' EXIT

resumen() { grep -E '^(Ran [0-9]+ tests?|OK|FAILED)' "$LOG" | tr '\n' ' '; }
correr() {  # nombre, orden...
  local nombre="$1"; shift
  total=$((total + 1))
  if "$@" > "$LOG" 2>&1; then
    printf '  ok       %-28s %s\n' "$nombre" "$(resumen)"
  elif grep -qE "No module named '?(PySide6|gi)'?|bwrap: command not found|bubblewrap" "$LOG" && ! grep -qE '^(FAIL|ERROR):' "$LOG"; then
    printf '  omitida  %-28s (falta una dependencia: PySide6 o bubblewrap)\n' "$nombre"
    omitidas=$((omitidas + 1))
  else
    printf '  FALLA    %-28s %s\n' "$nombre" "$(resumen)"
    grep -E '^(FAIL|ERROR):' "$LOG" | head -8 | sed 's/^/             /'
    fallos=$((fallos + 1))
  fi
}

echo "== scripts/"
cd "$RAIZ/scripts" || exit 1
for t in test_*.py; do correr "${t%.py}" python3 "$t"; done
correr test_npm_fijado bash test_npm_fijado.sh

echo "== leksso-ia/"
cd "$RAIZ/leksso-ia" || exit 1
for m in test_modelo test_ejecutar test_nucleo test_revision test_mcp test_ataques; do
  if [ "$RAPIDA" = 1 ] && { [ "$m" = test_mcp ] || [ "$m" = test_ataques ]; }; then continue; fi
  correr "$m" env PYTHONPATH=. python3 -m unittest "$m"
done

echo
echo "Pruebas: $total ejecutadas, $fallos con fallos, $omitidas omitidas."
[ "$fallos" -eq 0 ]
