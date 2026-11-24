#!/usr/bin/env bash
# Prueba de leksso-npm-fijado con un «npm» falso: no instala nada de verdad ni toca la red.
# Uso: bash scripts/test_npm_fijado.sh
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
AYUDANTE="$AQUI/../config/bin/leksso-npm-fijado"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fallos=0
ok()  { printf '  ok     %s\n' "$1"; }
mal() { printf '  FALLA  %s\n' "$1"; fallos=$((fallos + 1)); }

mkdir -p "$T/bin"
# npm falso: «view» devuelve la suma que diga FALSO_SUMA; «install» anota lo que se le pidió.
cat > "$T/bin/npm" <<'EOF'
#!/bin/sh
case "$1" in
  view) [ "${FALSO_SIN_RED:-}" = 1 ] && exit 1; printf '%s\n' "$FALSO_SUMA" ;;
  install) printf '%s\n' "$*" >> "$FALSO_REGISTRO" ;;
esac
EOF
chmod +x "$T/bin/npm"
cat > "$T/versiones" <<'EOF'
# comentario
@anthropic-ai/claude-code 2.1.331 sha512-AAAA
@openai/codex 0.172.0 sha512-BBBB
@sin/suma 1.0.0
@mala/version 1.0.0;rm sha512-CCCC
EOF

correr() {  # paquete -> código; la salida va a $T/salida
  : > "$T/registro"
  PATH="$T/bin:$PATH" LEKSSO_NPM_FIJADO="$T/versiones" FALSO_REGISTRO="$T/registro" "$AYUDANTE" "$@" > "$T/salida" 2>&1
}

FALSO_SUMA="sha512-AAAA" correr @anthropic-ai/claude-code
[ $? -eq 0 ] && grep -qx "install -g @anthropic-ai/claude-code@2.1.331" "$T/registro" && ok "instala la versión fijada" || mal "instala la versión fijada"

FALSO_SUMA="sha512-OTRA" correr @anthropic-ai/claude-code
[ $? -ne 0 ] && [ ! -s "$T/registro" ] && grep -q "no coincide" "$T/salida" && ok "se niega si la suma no coincide" || mal "se niega si la suma no coincide"

FALSO_SUMA="sha512-AAAA" correr @desconocido/paquete
[ $? -ne 0 ] && [ ! -s "$T/registro" ] && grep -q "no tiene versión fijada" "$T/salida" && ok "se niega con un paquete sin fijar" || mal "se niega con un paquete sin fijar"

FALSO_SUMA="sha512-AAAA" correr @sin/suma
[ $? -ne 0 ] && [ ! -s "$T/registro" ] && ok "se niega si falta la suma" || mal "se niega si falta la suma"

FALSO_SUMA="sha512-CCCC" correr @mala/version
[ $? -ne 0 ] && [ ! -s "$T/registro" ] && ok "se niega con una versión rara" || mal "se niega con una versión rara"

FALSO_SUMA="sha512-AAAA" FALSO_SIN_RED=1 correr @anthropic-ai/claude-code
[ $? -ne 0 ] && [ ! -s "$T/registro" ] && ok "sin conexión no instala" || mal "sin conexión no instala"

FALSO_SUMA="sha512-AAAA" correr
[ $? -eq 2 ] && ok "sin argumentos da el uso" || mal "sin argumentos da el uso"

LEKSSO_NPM_FIJADO="$T/no-existe" PATH="$T/bin:$PATH" FALSO_REGISTRO="$T/registro" "$AYUDANTE" @openai/codex > "$T/salida" 2>&1
[ $? -ne 0 ] && ok "sin archivo de versiones no instala" || mal "sin archivo de versiones no instala"

# el archivo real: cada paquete con versión y suma sha512
real="$AQUI/../config/ia/versiones-npm"
for p in @anthropic-ai/claude-code @openai/codex; do
  awk -v p="$p" '$1 == p && $3 ~ /^sha512-/ && $2 ~ /^[0-9]+\.[0-9]+\.[0-9]+$/ { f = 1 } END { exit !f }' "$real" && ok "versiones-npm fija $p" || mal "versiones-npm fija $p"
done

echo; [ "$fallos" -eq 0 ] && echo "Todo bien." || echo "$fallos fallo(s)."
exit "$fallos"
