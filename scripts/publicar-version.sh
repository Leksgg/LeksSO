#!/usr/bin/env bash
# Publica una versión de LeksSO: etiqueta firmada y subida. Solo para quien mantiene el repositorio.
#
# Uso: scripts/publicar-version.sh 0.1.48           una versión concreta (VERSION y CHANGELOG ya preparados)
#      Las versiones normales son solo números (0.1.48). Las de prueba llevan -alpha, -beta o -rc y van por debajo.
#      añade --sin-subir para preparar y firmar en local sin publicar (por ejemplo, para probar el instalador)
#      añade --sin-firma para publicar SIN firmar (fase de pruebas): solo la instalan los equipos que tienen
#      /etc/leksso/sin-firma; los demás la rechazan. Una imagen de instalación sigue necesitando una versión firmada.
#      scripts/publicar-version.sh --auto          la siguiente versión (+1 en el último número), con lo que haya
#                                                  bajo «## Sin publicar» en CHANGELOG.md
#      añade --estable a --auto para pasar de una versión de prueba (0.1.47-beta) a la normal siguiente (0.1.48)
#
# Antes de publicar comprueba: que VERSION y CHANGELOG.md dicen lo mismo, que no hay cambios sin subir
# y que la etiqueta no existe. La etiqueta se firma con la clave de LEKSSO_CLAVE_FIRMA (por defecto
# ~/.ssh/leksso_release). Si la clave tiene contraseña, desbloquéala antes con scripts/desbloquear-firma.sh
# y se firmará sin preguntar. Los equipos solo instalan versiones firmadas con la clave de config/allowed_signers
# cuyo commit pertenezca a la rama principal.
set -euo pipefail

FIRMAR=1
for a in "$@"; do [ "$a" = "--sin-firma" ] && FIRMAR=0; done
CLAVE="${LEKSSO_CLAVE_FIRMA:-$HOME/.ssh/leksso_release}"
# la clave se llamaba lekso_release antes del cambio de nombre: si solo existe esa, se usa
[ -e "$CLAVE" ] || ! [ -e "$HOME/.ssh/lekso_release" ] || CLAVE="$HOME/.ssh/lekso_release"
SOCK="${LEKSSO_AGENTE:-$HOME/.ssh/leksso-agent.sock}"
[ "$FIRMAR" = 0 ] || [ -f "$CLAVE" ] || { echo "No encuentro la clave de firma: $CLAVE" >&2; exit 1; }
cd "$(dirname "$0")/.."

patron='^([0-9]+)\.([0-9]+)\.([0-9]+)(-(alpha|beta|rc))?$'
nombre_bonito() { echo "$1" | sed -E 's/^([0-9.]+)-alpha$/Alpha \1/; s/^([0-9.]+)-beta$/Beta \1/; s/^([0-9.]+)-rc$/RC \1/'; }

# Clave: con agente desbloqueado se firma sin preguntar; si no, se usa el archivo (pide la contraseña si la tiene).
FIRMA="$CLAVE"
if [ -S "$SOCK" ] && SSH_AUTH_SOCK="$SOCK" ssh-add -l >/dev/null 2>&1; then
  export SSH_AUTH_SOCK="$SOCK"
  FIRMA="$CLAVE.pub"
fi
if [ "$FIRMAR" = 1 ] && ssh-keygen -y -P "" -f "$CLAVE" >/dev/null 2>&1; then
  echo "AVISO: la clave de firma no tiene contraseña. Ponle una con: ssh-keygen -p -f \"$CLAVE\"" >&2
fi

[ -z "$(git status --porcelain)" ] || { echo "Hay cambios sin subir: haz commit antes." >&2; exit 1; }

SUBIR=1
for a in "$@"; do [ "$a" = "--sin-subir" ] && SUBIR=0; done
PREPARADA=0
# Si algo falla después de preparar la versión (por ejemplo, la clave sigue bloqueada), se deshace el commit
# de preparación para poder repetir el comando sin dejar nada a medias.
trap 'if [ "$PREPARADA" = 1 ]; then git reset -q --hard HEAD~1; echo "No se publicó nada: la preparación se ha deshecho." >&2; fi' EXIT

V="${1:-}"
if [ "$V" = "--auto" ]; then
  ACT="$(tr -d '[:space:]' < VERSION)"
  [[ "$ACT" =~ $patron ]] || { echo "VERSION no es una versión válida: $ACT" >&2; exit 1; }
  V="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.$((BASH_REMATCH[3] + 1))${BASH_REMATCH[4]}"
  for a in "$@"; do [ "$a" = "--estable" ] && V="${V%%-*}"; done
  grep -q '^## Sin publicar' CHANGELOG.md || { echo "CHANGELOG.md no tiene «## Sin publicar» con los cambios de esta versión." >&2; exit 1; }
  # debe haber algo escrito debajo de «Sin publicar»
  awk '/^## Sin publicar/{d=1;next} /^## /{d=0} d && NF{n++} END{exit n?0:1}' CHANGELOG.md \
    || { echo "«## Sin publicar» está vacío." >&2; exit 1; }
  BONITA="$(nombre_bonito "$V")"
  sed -i "s/^## Sin publicar\$/## $BONITA · $(date +%F)/" CHANGELOG.md
  printf '%s\n' "$V" > VERSION
  git add VERSION CHANGELOG.md
  git commit -q -m "Versión $BONITA"
  PREPARADA=1
  echo "Preparada la versión $BONITA."
fi

[[ "$V" =~ $patron ]] || { echo "Uso: $0 X.Y.Z | --auto [--estable]   (de prueba: X.Y.Z-alpha, -beta o -rc)" >&2; exit 2; }
BONITA="$(nombre_bonito "$V")"
[ "$(tr -d '[:space:]' < VERSION)" = "$V" ] || { echo "VERSION no dice $V" >&2; exit 1; }
grep -qE "^## .*(${V}|${BONITA})" CHANGELOG.md || { echo "CHANGELOG.md no tiene una sección «## $BONITA»" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "Hay cambios sin subir: haz commit antes." >&2; exit 1; }
git rev-parse "v$V" >/dev/null 2>&1 && { echo "La etiqueta v$V ya existe." >&2; exit 1; }

if [ "$FIRMAR" = 1 ]; then
  git -c gpg.format=ssh -c user.signingkey="$FIRMA" tag -s "v$V" -m "LeksSO $BONITA"
  git -c gpg.ssh.allowedSignersFile=config/allowed_signers tag -v "v$V"
else
  git tag -a "v$V" -m "LeksSO $BONITA (sin firmar: fase de pruebas)"
  echo "AVISO: v$V va SIN FIRMA. Solo la aceptan los equipos en fase de pruebas (/etc/leksso/sin-firma)."
fi
if [ "$SUBIR" = 1 ]; then
  git push origin HEAD:main "v$V"
  PREPARADA=0
  echo "Publicada: LeksSO $BONITA (v$V)"
else
  PREPARADA=0
  echo "Etiqueta v$V creada y firmada EN LOCAL (no se ha subido). Para publicarla: git push origin HEAD:main v$V"
fi
