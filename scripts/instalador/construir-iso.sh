#!/usr/bin/env bash
# Construye la imagen de instalación de LeksSO (ISO): el Debian oficial con firmware, más el paquete de LeksSO.
#
# Uso: construir-iso.sh --iso DEBIAN.iso --offline CARPETA_REPO --version vX.Y.Z-alpha --salida LEKSSO.iso [--prueba CLAVE_PUBLICA_SSH]
#   --iso      imagen oficial «netinst con firmware» de Debian 13 (ya comprobada con su suma de Debian)
#   --offline  repositorio local de paquetes (lo crea construir-repo-offline.sh)
#   --version  versión de LeksSO que lleva, con su etiqueta firmada (v0.1.4-alpha)
#   --fase-pruebas  equipo real en pruebas: actualiza sin exigir firma y arranca con SSH en red local
#   --prueba   imagen de PRUEBAS: respuestas fijas (disco /dev/sda, claves de prueba) y acceso por SSH. NUNCA para uso real.
# Requiere: xorriso, git. Se ejecuta desde la raíz del repositorio de LeksSO (que debe tener la etiqueta).
set -euo pipefail

ISO=""; OFFLINE=""; VERSION=""; SALIDA=""; PRUEBA=""; FASE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --iso) ISO="$2"; shift 2 ;; --offline) OFFLINE="$2"; shift 2 ;; --version) VERSION="$2"; shift 2 ;;
    --salida) SALIDA="$2"; shift 2 ;; --prueba) PRUEBA="$2"; shift 2 ;; --fase-pruebas) FASE=1; shift ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
done
for v in ISO OFFLINE VERSION SALIDA; do [ -n "${!v}" ] || { echo "Falta --${v,,}" >&2; exit 2; }; done
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-(alpha|beta|rc)$ ]] || { echo "Versión no válida: $VERSION" >&2; exit 2; }
[ -f "$ISO" ] && [ -f "$OFFLINE/Packages.gz" ] || { echo "No encuentro la ISO o el repositorio local." >&2; exit 1; }
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"
git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null || { echo "La etiqueta $VERSION no existe en este repositorio." >&2; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PAQ="$TMP/leksso"; mkdir -p "$PAQ"

# 1. El paquete de LeksSO: el repositorio con sus etiquetas (se verifica al instalar), el instalador de ESA versión
#    y los archivos de instalación automática.
# Solo la rama principal y las etiquetas: con --all se llevaría también cualquier rama privada o de trabajo.
git rev-parse -q --verify refs/heads/main >/dev/null || { echo "Falta la rama main en este repositorio." >&2; exit 1; }
git bundle create "$PAQ/leksso.bundle" refs/heads/main --tags >/dev/null 2>&1 || { echo "No se pudo crear el paquete del repositorio." >&2; exit 1; }
git show "$VERSION:scripts/instalar.sh" > "$PAQ/instalar.sh"
git show "$VERSION:scripts/instalador/preseed.cfg" > "$PAQ/preseed.cfg"
git show "$VERSION:scripts/instalador/receta.sh" > "$PAQ/receta.sh"
git show "$VERSION:scripts/instalador/elegir-disco.sh" > "$PAQ/elegir-disco.sh"
git show "$VERSION:scripts/instalador/postinstalar.sh" > "$PAQ/postinstalar.sh"
printf '%s\n' "$VERSION" > "$PAQ/VERSION_TAG"
cp -r "$OFFLINE" "$PAQ/offline"
# La clave incrustada en instalar.sh debe ser exactamente la de config/allowed_signers de esa versión.
CLAVE_EN_SCRIPT="$(sed -n "s/^CLAVE_PUBLICA='\(.*\)'\$/\1/p" "$PAQ/instalar.sh")"
[ -n "$CLAVE_EN_SCRIPT" ] && [ "$CLAVE_EN_SCRIPT" = "$(git show "$VERSION:config/allowed_signers" | head -n1)" ] \
  || { echo "La clave incrustada en instalar.sh no coincide con config/allowed_signers." >&2; exit 1; }

# 1a. Variantes de instalación, una entrada del menú cada una: el disco se cifra o no, y el usuario tiene contraseña o no.
#     La base (preseed.cfg) es «disco cifrado, con contraseña». Sin contraseña: el instalador no la pregunta (se deja
#     bloqueada) y postinstalar.sh quita la contraseña, activa la entrada automática y sudo sin clave.
sed -e 's#^d-i partman-auto/method string crypto#d-i partman-auto/method string lvm#' -e 's#^d-i partman-auto/init_automatically_partition select some_device_crypto#d-i partman-auto/init_automatically_partition select some_device_lvm#' "$PAQ/preseed.cfg" > "$PAQ/preseed-sin-cifrado.cfg"
for par in "preseed:preseed-sin-contrasena" "preseed-sin-cifrado:preseed-sin-cifrado-sin-contrasena"; do
  origen="${par%%:*}"; destino="${par##*:}"
  sed 's#^\(  in-target sh /opt/leksso-instalacion/postinstalar.sh\)$#\1 --sin-contrasena#' "$PAQ/$origen.cfg" > "$PAQ/$destino.cfg"
  printf '\n# --- Sin contraseña de usuario: la deja bloqueada y postinstalar.sh la quita ---\nd-i passwd/user-password-crypted password !\n' >> "$PAQ/$destino.cfg"
done

# 1a-ter. Variante EXPERIMENTAL «junto a Windows» con particionado MANUAL: no lleva receta ni elección de disco (esas BORRAN el disco
#     entero), así que el instalador de Debian enseña su propio particionador y el usuario elige el espacio libre, sin cifrar.
#     Nada se borra salvo lo que el usuario marque. El resto (usuario, paquetes, LeksSO) es igual que la variante «sin cifrar».
sed -e '/^d-i partman\/early_command/d' -e '/^d-i partman-auto/d' -e '/^d-i partman-lvm\//d' -e '/^d-i partman-md\//d' \
    -e '/^d-i partman-partitioning\//d' "$PAQ/preseed.cfg" > "$PAQ/preseed-manual.cfg"

# 1a-bis. Disco cifrado con DESBLOQUEO AUTOMÁTICO (TPM2): igual que «cifrado», pero en el primer arranque del escritorio se ofrece
#     enlazar el disco al TPM para no teclear la clave en cada encendido (la clave elegida queda de respaldo).
sed -E 's#^(  in-target sh /opt/leksso-instalacion/postinstalar.sh( --sin-contrasena)?)$#\1 --disco-automatico#' "$PAQ/preseed.cfg" > "$PAQ/preseed-disco-automatico.cfg"
sed -E 's#^(  in-target sh /opt/leksso-instalacion/postinstalar.sh( --sin-contrasena)?)$#\1 --disco-automatico#' "$PAQ/preseed-sin-contrasena.cfg" > "$PAQ/preseed-disco-automatico-sin-contrasena.cfg"

# 1b. Fase de pruebas en equipos reales: sin exigir firma en las actualizaciones y con acceso remoto en red local.
if [ "$FASE" = 1 ]; then echo "fase de pruebas" > "$PAQ/FASE_PRUEBAS"; fi

# 2. Imagen de pruebas: respuestas fijas para poder instalar sin nadie delante.
if [ -n "$PRUEBA" ]; then
  printf '%s\n' "$PRUEBA" > "$PAQ/PRUEBA"
  cat >> "$PAQ/preseed.cfg" <<'EOF'

# ===== SOLO IMAGEN DE PRUEBAS =====
d-i partman-auto/disk string /dev/sda
d-i partman-crypto/passphrase password prueba
d-i partman-crypto/passphrase-again password prueba
d-i partman-crypto/weak_passphrase boolean true
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true
d-i partman/choose_partition select finish
d-i passwd/user-fullname string LeksSO
d-i passwd/username string leksso
d-i passwd/user-password password Lks15
d-i passwd/user-password-again password Lks15
d-i user-setup/allow-password-weak boolean true
EOF
fi

# 3. Menú de arranque: una entrada nueva (la primera) que lanza la instalación de LeksSO.
ORIGEN_GRUB="$TMP/grub.orig"
xorriso -osirrox on -indev "$ISO" -extract /boot/grub/grub.cfg "$ORIGEN_GRUB" >/dev/null 2>&1
# Una imagen de pruebas no debe poder confundirse con una normal: lo dice el título de cada entrada del menú.
AVISO_PRUEBAS=""
[ "$FASE" = 1 ] && AVISO_PRUEBAS="[PRUEBAS] "
[ -n "$PRUEBA" ] && AVISO_PRUEBAS="[IMAGEN DE PRUEBAS] "
ENTRADA="menuentry --hotkey=l '${AVISO_PRUEBAS}Instalar LeksSO | Disco cifrado con clave | Usuario con contraseña (recomendada)' {
    set background_color=black
    linux    /install.amd/vmlinuz auto=true priority=critical file=/cdrom/leksso/preseed.cfg vga=788 --- quiet
    initrd   /install.amd/initrd.gz
}"
# Variantes (no en las imágenes de pruebas, que llevan respuestas fijas solo en la primera): cifrado sí/no, contraseña sí/no.
if [ -z "$PRUEBA" ]; then
  variante() {  # título, preseed
    printf "menuentry '${AVISO_PRUEBAS}%s' {\n    set background_color=black\n    linux    /install.amd/vmlinuz auto=true priority=critical file=/cdrom/leksso/%s vga=788 --- quiet\n    initrd   /install.amd/initrd.gz\n}\n" "$1" "$2"
  }
  ENTRADA="$ENTRADA
$(variante 'Instalar LeksSO | Disco cifrado con clave | Usuario sin contraseña' preseed-sin-contrasena.cfg)
$(variante 'Instalar LeksSO | Cifrado con TPM, sin clave | Usuario con contraseña' preseed-disco-automatico.cfg)
$(variante 'Instalar LeksSO | Cifrado con TPM, sin clave | Usuario sin contraseña' preseed-disco-automatico-sin-contrasena.cfg)
$(variante 'Instalar LeksSO | Disco sin cifrar | Usuario con contraseña' preseed-sin-cifrado.cfg)
$(variante 'Instalar LeksSO | Disco sin cifrar | Usuario sin contraseña' preseed-sin-cifrado-sin-contrasena.cfg)
$(printf "menuentry '${AVISO_PRUEBAS}[EXPERIMENTAL] Instalar LeksSO JUNTO a Windows | Particionado manual | Sin cifrar | Usuario con contraseña' {
    set background_color=black
    echo 'Se abrira el particionador de Debian. Elige el ESPACIO LIBRE. No toques las particiones de Windows.'
    sleep 4
    linux    /install.amd/vmlinuz auto=true priority=high file=/cdrom/leksso/preseed-manual.cfg vga=788 --- quiet
    initrd   /install.amd/initrd.gz
}")
$(printf "menuentry 'Reparar LeksSO que no arranca (rescate, no borra nada)' {
    set background_color=black
    echo 'MODO DE RESCATE. Elige el idioma y el teclado, abre el disco con tu clave y entra en la consola del sistema.'
    echo 'Alli escribe:  leksso-reparar     (para recuperar tus archivos: copialos a un USB desde esa consola)'
    sleep 6
    linux    /install.amd/vmlinuz rescue/enable=true vga=788 --- quiet
    initrd   /install.amd/initrd.gz
}")"
fi
# 3b. Temas del menú: la caja de Debian es estrecha (unos 46 caracteres) y cortaba los títulos justo donde se distinguen. Se
#     ensancha y se añade una leyenda fija debajo. Hay DOS temas: el 1 (menú de arriba) y el 2 (menú «Instalar LeksSO»), cada uno
#     con la leyenda que le toca. (Un «submenu» de GRUB pierde el tema; por eso el segundo nivel es otro archivo de menú.)
xorriso -osirrox on -indev "$ISO" -extract /boot/grub/theme/1 "$TMP/tema.orig" >/dev/null 2>&1
python3 -I - "$TMP/tema.orig" "$TMP/tema1" "$TMP/tema2" <<'PY'
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
t = re.sub(r"(\+ boot_menu \{\s*left = )18%(\s*width = )50%(\s*top = )200(\s*height = )200", r"\g<1>5%\g<2>90%\g<3>170\g<4>280", t)

def leyenda(lineas):
    s = "\n+ vbox {\n  top = 470\n  left = 5%\n  width = 90%\n"
    for texto, color in lineas:
        s += '  + label {text = "%s" font = "Sans 10" color = "%s" align = "left"}\n' % (texto, color)
    return s + "}\n"

arriba = leyenda([
    ("Elige qué quieres hacer. Con «Instalar» se te pedirá después el disco, y se BORRARÁ todo lo que tenga.", "#d0d0d0"),
    ("«Reparar» no borra nada: arregla un LeksSO que no arranca.", "#d0d0d0"),
])
instalar = leyenda([
    ("Cifrado con clave: tecleas la clave del disco en cada arranque.   Cifrado con TPM: el equipo abre el disco solo.", "#d0d0d0"),
    ("Usuario sin contraseña: entra directo al escritorio.   Sin cifrar: el disco queda legible si lo sacan del equipo.", "#d0d0d0"),
    ("Todas estas opciones BORRAN el disco que elijas en la pantalla siguiente.", "#ffd27a"),
])
open(sys.argv[2], "w", encoding="utf-8").write(t.rstrip() + "\n" + arriba)
open(sys.argv[3], "w", encoding="utf-8").write(t.rstrip() + "\n" + instalar)
PY
grep -q 'width = 90%' "$TMP/tema1" && grep -q 'width = 90%' "$TMP/tema2" || { echo "No se pudo ensanchar el tema del menú." >&2; exit 1; }

# Menú de dos niveles. Arriba: «Instalar LeksSO» (abre leksso-instalar.cfg con las variantes), «Instalar Windows 10» (solo si el
# pendrive tiene su partición con la etiqueta WIN10) y «Reparar». Se quitan las entradas originales de Debian (Graphical install...).
python3 -I - "$ORIGEN_GRUB" "$TMP/grub.cfg" "$TMP/leksso-instalar.cfg" "$ENTRADA" <<'PY'
import sys
orig = open(sys.argv[1], encoding="utf-8").read()
entrada = sys.argv[4]
k = entrada.find("menuentry 'Reparar")
i = orig.index("menuentry ")
cabecera = orig[:i]
# Sin cuenta atrás (timeout=-1): el menú espera; no debe empezar a borrar un disco solo.
if k > 0:
    variantes, reparar = entrada[:k], entrada[k:]
    arriba = (
        "menuentry 'Instalar LeksSO  (elige el tipo de instalacion)' {\n"
        "    configfile /boot/grub/leksso-instalar.cfg\n"
        "}\n"
        "if search --no-floppy --label WIN10 --set=win10; then\n"
        "  menuentry 'Instalar Windows 10 (desde este pendrive)' {\n"
        "    set background_color=black\n"
        "    echo 'Windows 10: el instalador te deja elegir el disco. No borra nada hasta que lo confirmes alli.'\n"
        "    sleep 3\n"
        "    search --no-floppy --label WIN10 --set=root\n"
        "    chainloader /efi/boot/bootx64.efi\n"
        "  }\n"
        "fi\n") + reparar
    segundo = (
        "set theme=/boot/grub/theme/2\nset default=0\nset timeout=-1\n" + variantes +
        "menuentry '<  Volver al menu anterior' {\n    configfile /boot/grub/grub.cfg\n}\n")
else:   # imagen de pruebas: una sola entrada, sin segundo nivel
    arriba, segundo = entrada, ""
espera = "-1" if k > 0 else "10"   # las imágenes de pruebas arrancan solas
open(sys.argv[2], "w", encoding="utf-8").write("set default=0\nset timeout=" + espera + "\n" + cabecera + arriba + "\n")
open(sys.argv[3], "w", encoding="utf-8").write(segundo)
PY

# 4. La imagen: la original más el paquete y el menú nuevo (el arranque se conserva).
rm -f "$SALIDA"
xorriso -indev "$ISO" -outdev "$SALIDA" -map "$PAQ" /leksso -map "$TMP/grub.cfg" /boot/grub/grub.cfg -map "$TMP/tema1" /boot/grub/theme/1 -map "$TMP/tema2" /boot/grub/theme/2 -map "$TMP/leksso-instalar.cfg" /boot/grub/leksso-instalar.cfg -boot_image any replay 2>&1 \
  | grep -iE 'fail|error|written|wrote' || true
echo
ls -la "$SALIDA"
sha256sum "$SALIDA"
