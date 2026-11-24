#!/bin/sh
# Se ejecuta DENTRO del sistema recién instalado (en el instalador, con chroot), sin necesidad de red.
# Instala LeksSO con el instalador firmado: la versión sale del paquete del USB y se comprueba su firma.
set -e
PAQ=/opt/leksso-instalacion
# Todo lo que pase queda en un registro del sistema instalado, para poder revisar un fallo después.
exec >> /var/log/leksso-postinstalar.log 2>&1
set -x
export DEBIAN_FRONTEND=noninteractive

# 1. Los paquetes de Debian que necesita LeksSO están en el USB: se usan como fuente de apt local.
sed -i 's/^deb cdrom:/# deb cdrom:/' /etc/apt/sources.list      # el DVD del instalador ya no es fuente: solo el repositorio local
echo "deb [trusted=yes] file:$PAQ/offline ./" > /etc/apt/sources.list.d/leksso-offline.list
echo 'APT::Install-Recommends "false";' > /etc/apt/apt.conf.d/99leksso-sin-recomendados
apt-get update -qq 2>/dev/null || true      # si los espejos de red fallan por no haber conexión, no importa

# 2. Para quién se instala: el primer usuario que creó el instalador.
USUARIO="$(getent passwd 1000 | cut -d: -f1)"
[ -n "$USUARIO" ] || { echo "No encuentro el usuario creado por el instalador." >&2; exit 1; }

# 3. Solo para las imágenes de prueba (llevan un archivo PRUEBA): acceso por SSH para poder revisar la instalación.
if [ -f "$PAQ/PRUEBA" ]; then
  apt-get install -y -qq openssh-server sudo >/dev/null
  install -d -m 0700 -o "$USUARIO" -g "$USUARIO" "/home/$USUARIO/.ssh"
  install -m 0600 -o "$USUARIO" -g "$USUARIO" "$PAQ/PRUEBA" "/home/$USUARIO/.ssh/authorized_keys"
  echo "$USUARIO ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$USUARIO"; chmod 440 "/etc/sudoers.d/$USUARIO"
fi

# 3b. USB de FASE DE PRUEBAS (lleva un archivo FASE_PRUEBAS): el equipo acepta actualizaciones sin exigir firma
#     y arranca con el acceso remoto encendido (SSH solo desde la red local), para poder revisarlo.
if [ -f "$PAQ/FASE_PRUEBAS" ]; then
  apt-get install -y -qq openssh-server >/dev/null
  install -d /etc/leksso /etc/ssh/sshd_config.d
  touch /etc/leksso/sin-firma /etc/leksso/acceso-remoto
  printf '# LeksSO: acceso remoto
PermitRootLogin no
MaxAuthTries 4
X11Forwarding no
' > /etc/ssh/sshd_config.d/leksso.conf
fi

# 3d. «Disco cifrado con desbloqueo automático»: el disco se cifra con la clave que se eligió al instalar y, en el primer
#     arranque del escritorio, se ofrece enlazarlo al TPM2 (leksso-disco). No se hace aquí porque pide esa clave y el
#     estado del arranque del instalador no es el del sistema instalado. Las herramientas van en el USB (sin internet).
case " $* " in *" --disco-automatico "*)
  apt-get install -y -qq clevis clevis-luks clevis-tpm2 clevis-initramfs tpm2-tools >/dev/null || true
  install -d /etc/leksso
  touch /etc/leksso/disco-automatico-pendiente ;;
esac

# 4. LeksSO, con la comprobación de firma del instalador.
VERSION="$(cat "$PAQ/VERSION_TAG")"
SUDO_USER="$USUARIO" bash "$PAQ/instalar.sh" --origen "$PAQ/leksso.bundle" --version "$VERSION" --si

# 4b. Otros sistemas en el equipo (Windows): el menú de arranque de LeksSO (GRUB) los muestra, así se elige al encender,
#     y, si hay Windows, la hora de la placa se deja como la guarda él (hora local) para que no se desfase al alternar.
#     Si no hay otro sistema, no cambia nada. os-prober viene en el USB (sin internet).
apt-get install -y -qq os-prober >/dev/null 2>&1 || true
if command -v os-prober >/dev/null 2>&1; then
  if grep -q '^GRUB_DISABLE_OS_PROBER' /etc/default/grub; then
    sed -i 's/^GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=false/' /etc/default/grub
  else
    echo 'GRUB_DISABLE_OS_PROBER=false' >> /etc/default/grub
  fi
  OTROS="$(os-prober 2>/dev/null || true)"
  update-grub >/dev/null 2>&1 || true
  case "$OTROS" in
    *Windows*|*Microsoft*)
      echo "Windows detectado: GRUB lo muestra en su menú; hora de la placa en hora local."
      printf '0.0 0 0.0\n0\nLOCAL\n' > /etc/adjtime ;;
  esac
fi

# 5. Fuentes de apt normales para el sistema ya instalado (las actualizaciones de Debian irán por red) y limpieza.
rm -f /etc/apt/sources.list.d/leksso-offline.list /etc/apt/apt.conf.d/99leksso-sin-recomendados
cat > /etc/apt/sources.list <<'EOF'
deb http://deb.debian.org/debian trixie main contrib non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free-firmware
EOF
rm -rf "$PAQ/offline"
echo "LeksSO instalado."
