#!/usr/bin/env bash
# Construye el repositorio local de paquetes que lleva el USB de instalación, para instalar LeksSO SIN internet.
#
# Qué hace: crea un Debian 13 mínimo en una carpeta (debootstrap), calcula todo lo que necesita LeksSO encima
# de ese sistema base y descarga solo esos paquetes (los de Debian, con las firmas de Debian comprobadas por apt).
# Deja una carpeta con los .deb y un índice (Packages.gz) que el instalador usa como fuente de apt local.
#
# Uso (en un Debian 13 con internet, como root): construir-repo-offline.sh SALIDA [RAIZ_REPO_LEKSSO] [IMAGEN_DEBIAN.iso]
#   SALIDA            carpeta donde quedará el repositorio (por ejemplo /var/tmp/leksso-offline)
#   RAIZ_REPO_LEKSSO   copia del repositorio de LeksSO de la que leer las listas de paquetes (por defecto, la de este script)
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta como root." >&2; exit 1; }
SALIDA="${1:?Indica la carpeta de salida}"
RAIZ="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ISO_DEBIAN="${3:-}"   # imagen «netinst» de Debian con la que se usará este repositorio (para no mezclar versiones, ver abajo)
MIRROR="${LEKSSO_MIRROR:-http://deb.debian.org/debian}"
# Carpeta de trabajo nueva y privada (no una ruta predecible que otra cuenta pueda preparar de antemano).
BASE="$(mktemp -d /var/tmp/leksso-base.XXXXXXXX)"
chmod 0755 "$BASE"

apt-get install -y -qq debootstrap dpkg-dev >/dev/null

# 1. Las listas de paquetes salen del propio script de instalación (una sola fuente de verdad).
LISTA="$(bash -c '
  set -e
  eval "$(sed -n "/^ESCRITORIO=(/,/^COMPATIBILIDAD=(/p" "'"$RAIZ"'/scripts/provision-base.sh")"
  printf "%s\n" "${ESCRITORIO[@]}" "${AUDIO[@]}" "${AISLAMIENTO[@]}" "${HERRAMIENTAS[@]}" "${RED[@]}" "${GRAFICA[@]}" "${COMPATIBILIDAD[@]}" "${HYPERV[@]}"
')"
# Lo que instalan después el endurecimiento y el bloque de firmware, y lo que necesita el instalador.
EXTRA="nftables unattended-upgrades isenkram-cli intel-microcode amd64-microcode thermald
firmware-iwlwifi firmware-sof-signed firmware-intel-misc firmware-intel-graphics firmware-amd-graphics
firmware-realtek firmware-atheros firmware-mediatek firmware-misc-nonfree firmware-brcm80211
lxqt-policykit cloud-guest-utils parted smartmontools gparted gnome-disk-utility
git openssh-client openssh-server ca-certificates python3 sudo locales
clevis clevis-luks clevis-tpm2 clevis-initramfs tpm2-tools
os-prober ntfs-3g"
TODOS="$(printf '%s\n%s\n' "$LISTA" "$EXTRA" | tr ' ' '\n' | sed '/^$/d' | sort -u | tr '\n' ' ')"
echo "Paquetes pedidos: $(echo "$TODOS" | wc -w)"

# 2. Sistema base mínimo, para saber qué falta encima de él.
echo "Creando el sistema base (debootstrap)…"
# (la carpeta acaba de crearse vacía: no se borra ni se vuelve a crear por nombre)
debootstrap --variant=minbase --components=main,contrib,non-free-firmware trixie "$BASE" "$MIRROR" >/dev/null
cat > "$BASE/etc/apt/sources.list" <<EOF
deb $MIRROR trixie main contrib non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free-firmware
EOF

# 3. Descargar (sin instalar) todo el cierre de dependencias.
mkdir -p "$SALIDA"
rm -f "$SALIDA"/*.deb
mkdir -p "$BASE/var/cache/leksso-descargas"
mount --bind "$SALIDA" "$BASE/var/cache/leksso-descargas"
trap 'umount "$BASE/var/cache/leksso-descargas" 2>/dev/null || true; rm -rf "$BASE"' EXIT
chroot "$BASE" apt-get update -qq

# 3b. Brave (navegador por defecto) viene de su propio repositorio, no de Debian. Su clave se descarga y SOLO se acepta si todas
# las huellas están en esta lista (la misma que HUELLAS["brave-browser"] de leksso-apps.py: si Brave rota su clave, se cambian las dos).
HUELLAS_BRAVE="DBF1A116C220B8C7164F98230686B78420038257 47D32A74E9A9E013A4B4926C68D513D36A73CD96 B2A3DCA350E67256740DF904DE4EC67BE4B0DCA0"
apt-get install -y -qq curl gnupg >/dev/null
CLAVE_BRAVE="$(mktemp)"
curl -fsSL https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg -o "$CLAVE_BRAVE"
FPR_BRAVE="$(gpg --show-keys --with-colons --fingerprint "$CLAVE_BRAVE" | awk -F: '/^pub/{p=1;next} p&&/^fpr/{print $10;p=0}')"
[ -n "$FPR_BRAVE" ] || { echo "ERROR: no se pudo leer la clave de Brave." >&2; exit 1; }
for f in $FPR_BRAVE; do
  case " $HUELLAS_BRAVE " in *" $f "*) ;; *) echo "ERROR: la clave de Brave no es la esperada ($f). No se descarga nada de Brave." >&2; exit 1 ;; esac
done
# (ca-certificates se instala con la misma carpeta de descargas, para que su .deb quede también en el repositorio local)
chroot "$BASE" env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
  -o Dir::Cache::archives=/var/cache/leksso-descargas ca-certificates >/dev/null
install -d "$BASE/usr/share/keyrings"
install -m 0644 "$CLAVE_BRAVE" "$BASE/usr/share/keyrings/brave-browser.gpg"; rm -f "$CLAVE_BRAVE"
echo "deb [signed-by=/usr/share/keyrings/brave-browser.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" \
  > "$BASE/etc/apt/sources.list.d/brave-browser.list"
chroot "$BASE" apt-get update -qq
TODOS="$TODOS brave-browser"
# shellcheck disable=SC2086
chroot "$BASE" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --download-only \
  -o Dir::Cache::archives=/var/cache/leksso-descargas $TODOS
rm -f "$SALIDA/lock"; rm -rf "$SALIDA/partial"

# 3c. Si se indica la imagen de Debian, se quitan los paquetes que ella ya trae en otra versión (mezclarlas rompe GRUB: ver el script).
if [ -n "$ISO_DEBIAN" ]; then
  python3 "$(dirname "${BASH_SOURCE[0]}")/filtrar-repo-offline.py" "$SALIDA" "$ISO_DEBIAN"
else
  echo "AVISO: sin la imagen de Debian como tercer argumento no se filtran versiones repetidas; pasa la ISO para evitar fallos al instalar GRUB." >&2
fi

# 4. Índice del repositorio local.
( cd "$SALIDA" && dpkg-scanpackages --multiversion . /dev/null 2>/dev/null | gzip -9 > Packages.gz )
echo
echo "Repositorio listo en $SALIDA: $(ls "$SALIDA"/*.deb | wc -l) paquetes, $(du -sh "$SALIDA" | cut -f1)."
