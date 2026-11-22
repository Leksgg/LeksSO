#!/usr/bin/env bash
# Convierte un Debian 13 mínimo en la base de LeksSO: escritorio, audio y aislamiento.
# Se puede ejecutar varias veces sin romper nada. Debe correr como root.
#
# Uso:
#   sudo ./scripts/provision-base.sh [usuario]
#
# Incluye escritorio por zonas, permisor de IA con su panel, caja, dispositivos, red e iconos.
# No incluye: controlador de NVIDIA (se instala con confirmación desde Ajustes → Actualizaciones), Ollama ni las aplicaciones (Brave, Steam, Obsidian...):
# esas se instalan después con `leksso-apps`.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta como root: sudo $0 [usuario]" >&2
  exit 1
fi

USUARIO="${1:-${SUDO_USER:-}}"
if [ -z "$USUARIO" ] || ! id "$USUARIO" >/dev/null 2>&1; then
  echo "Indica un usuario existente: sudo $0 <usuario>" >&2
  exit 1
fi

# Equipos instalados con el nombre antiguo («lekso»): mover sus datos antes de instalar
bash "$(dirname "${BASH_SOURCE[0]}")/migrar-nombre.sh" "$USUARIO" || true
HOME_USR="$(getent passwd "$USUARIO" | cut -d: -f6)"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Todo lo que se escribe en la carpeta personal se hace COMO EL USUARIO, nunca como root: así un enlace simbólico
# plantado en su carpeta no puede llevar una escritura, un cambio de propietario o un borrado a rutas del sistema.
U() { runuser -u "$USUARIO" -- "$@"; }
U test -r "$RAIZ/config/sway/config" || { echo "El usuario $USUARIO no puede leer $RAIZ: la copia de LeksSO debe ser legible (chmod a+rX)." >&2; exit 1; }

# Registro de instalaciones (leksso-auditoria): se instala lo primero, para anotar también lo que instala esta misma
# ejecución. El gancho de apt nunca impide instalar. Los datos (registro, sellos) los crea el propio programa y esta
# instalación no los toca.
install -m 0755 "$RAIZ/scripts/leksso-auditoria.py" /usr/local/bin/leksso-auditoria
install -d /etc/apt/apt.conf.d
install -m 0644 "$RAIZ/config/apt/99leksso-auditoria" /etc/apt/apt.conf.d/99leksso-auditoria

# Paquetes por capa. Todos existen en Debian 13 (trixie); winetricks necesita la sección contrib.
ESCRITORIO=(labwc sway swaybg waybar kitty fuzzel grim pcmanfm-qt qt6-wayland qt6-svg-plugins qt6ct xwayland fonts-font-awesome seatd xdg-desktop-portal-wlr micro imv zathura zathura-pdf-poppler mpv vlc xarchiver udisks2 udiskie gvfs gvfs-backends polkitd ntfs-3g exfatprogs usbutils v4l-utils bluez pavucontrol-qt swaylock wl-clipboard mako-notifier libnotify-bin swayidle brightnessctl slurp cliphist wdisplays blueman cups fonts-noto-color-emoji fonts-liberation ffmpegthumbnailer power-profiles-daemon playerctl wlr-randr network-manager streamdeck-ui python3-pyside6.qtwidgets python3-pyside6.qtgui python3-pyside6.qtcore python3-pyside6.qtsvg)
AUDIO=(pipewire pipewire-pulse wireplumber alsa-ucm-conf alsa-utils libspa-0.2-bluetooth)   # ucm: micrófono y altavoz del portátil; bluetooth: auriculares
AISLAMIENTO=(bubblewrap firejail python3-seccomp passt)
HERRAMIENTAS=(git curl btop lm-sensors python3 bc pciutils mokutil fwupd plocate restic efibootmgr)   # plocate: búsqueda de archivos; restic: copias de seguridad
# Red inalámbrica: NetworkManager necesita wpasupplicant para conectarse a cualquier Wi-Fi con contraseña; es un paquete «recomendado»
# y el instalador instala sin recomendados, así que sin esto un portátil solo con Wi-Fi se quedaba sin red. iw y wireless-regdb: canales y
# potencias permitidos por país.
RED=(network-manager wpasupplicant iw wireless-regdb)
GRAFICA=(mesa-vulkan-drivers)
HYPERV=(hyperv-daemons)       # solo útil dentro de una máquina virtual de Hyper-V
COMPATIBILIDAD=(wine winetricks)

# winetricks (y más adelante Steam) están en la sección contrib, que el instalador no activa.
# Cubre tanto /etc/apt/sources.list como el formato nuevo en /etc/apt/sources.list.d/*.sources.
if [ -f /etc/apt/sources.list ]; then
  sed -i -E '/^deb(-src)? /{/ contrib( |$)/!s/ main( |$)/ main contrib\1/}' /etc/apt/sources.list
fi
for f in /etc/apt/sources.list.d/*.sources; do
  [ -e "$f" ] || continue
  sed -i -E '/^Components:/{/contrib/!s/ main( |$)/ main contrib\1/}' "$f"
done

export DEBIAN_FRONTEND=noninteractive
apt-get update || echo "Sin conexión: se usan los paquetes locales disponibles."
apt-get install -y --no-install-recommends \
  "${ESCRITORIO[@]}" "${AUDIO[@]}" "${AISLAMIENTO[@]}" \
  "${HERRAMIENTAS[@]}" "${RED[@]}" "${GRAFICA[@]}" "${COMPATIBILIDAD[@]}"

# Herramientas de invitado solo si estamos en Hyper-V.
if [ "$(systemd-detect-virt 2>/dev/null || true)" = "microsoft" ]; then
  apt-get install -y --no-install-recommends "${HYPERV[@]}"
  # El cursor por hardware suele fallar en la pantalla virtual de Hyper-V.
  grep -q '^WLR_NO_HARDWARE_CURSORS=' /etc/environment 2>/dev/null || echo 'WLR_NO_HARDWARE_CURSORS=1' >> /etc/environment
fi

# El usuario necesita estos grupos para que el compositor acceda a pantalla y teclado.
usermod -aG video,input,render "$USUARIO" 2>/dev/null || true
systemctl enable --now seatd 2>/dev/null || true
usermod -aG seatd "$USUARIO" 2>/dev/null || true

# Configuración del escritorio.
U install -d "$HOME_USR/.config/sway"
U install -m 0644 "$RAIZ/config/sway/config" "$HOME_USR/.config/sway/config"
# En una máquina virtual de Hyper-V, resolución grande (en un equipo real se usa la nativa).
# Solo si el usuario no tiene ya su local.conf: ese archivo es suyo y una actualización no lo reescribe.
if [ "$(systemd-detect-virt 2>/dev/null || true)" = "microsoft" ] && [ ! -e "$HOME_USR/.config/sway/local.conf" ]; then
  echo "output * resolution 1920x1080" | U tee "$HOME_USR/.config/sway/local.conf" >/dev/null
fi

# Barra superior, tema de las aplicaciones Qt y estado de la IA.
U install -d "$HOME_USR/.config/waybar" "$HOME_USR/.config/qt6ct/colors" "$HOME_USR/.config/leksso"
U install -m 0644 "$RAIZ/config/waybar/config.jsonc" "$HOME_USR/.config/waybar/config.jsonc"
U install -m 0644 "$RAIZ/config/waybar/style.css" "$HOME_USR/.config/waybar/style.css"
U install -m 0644 "$RAIZ/config/qt6ct/colors/leksso.conf" "$HOME_USR/.config/qt6ct/colors/leksso.conf"
sed "s|@HOME@|$HOME_USR|g" "$RAIZ/config/qt6ct/qt6ct.conf" | U tee "$HOME_USR/.config/qt6ct/qt6ct.conf" >/dev/null

# Iconos de tipos de archivo (tema propio, hereda de Adwaita).
install -d /usr/share/icons
cp -r "$RAIZ/config/iconos/LeksSO" /usr/share/icons/
gtk-update-icon-cache -f /usr/share/icons/LeksSO 2>/dev/null || true
grep -q '^QT_QPA_PLATFORMTHEME=' /etc/environment 2>/dev/null || echo 'QT_QPA_PLATFORMTHEME=qt6ct' >> /etc/environment

# Permisor de IA, panel, gestor de modelos y caja (en /usr/local, solo lectura para el usuario).
install -d -m 0755 /usr/local/lib/leksso-ia
install -m 0644 "$RAIZ"/leksso-ia/nucleo.py "$RAIZ"/leksso-ia/permisor.py "$RAIZ"/leksso-ia/modelo.py "$RAIZ"/leksso-ia/equipo.py "$RAIZ"/leksso-ia/asistentes.py "$RAIZ"/leksso-ia/leksso_admin.py \
  "$RAIZ"/leksso-ia/panel.py "$RAIZ"/leksso-ia/leksso_ia.py "$RAIZ"/leksso-ia/mcp_permisor.py /usr/local/lib/leksso-ia/
printf '#!/bin/sh\nexec python3 /usr/local/lib/leksso-ia/leksso_ia.py "$@"\n' > /usr/local/bin/leksso-ia
install -m 0755 "$RAIZ/scripts/caja.sh" /usr/local/bin/caja
install -m 0755 "$RAIZ/scripts/leksso-claude.sh" /usr/local/bin/leksso-claude
install -m 0755 "$RAIZ/scripts/leksso-codex.sh" /usr/local/bin/leksso-codex
install -m 0755 "$RAIZ/config/bin/leksso-asistente" /usr/local/bin/leksso-asistente
install -m 0755 "$RAIZ/config/bin/leksso-asistentes" /usr/local/bin/leksso-asistentes
# Permisos de los asistentes: archivo del administrador. En una instalación nueva, todos apagados y en «solo archivos».
# Si el usuario ya había elegido uno con la versión anterior, se conserva activo (solo archivos).
install -d -m 0755 /etc/leksso
if [ ! -f /etc/leksso/asistentes.json ]; then
  ANTERIOR="$(U cat "$HOME_USR/.config/leksso/asistente" 2>/dev/null || true)"
  python3 -I - "$USUARIO" "$ANTERIOR" <<'PY'
import sys
sys.path.insert(0, "/usr/local/lib/leksso-ia")
import asistentes
usuario, anterior = sys.argv[1], sys.argv[2].strip()
asistentes.guardar(usuario, {anterior: {"activo": True}} if anterior in asistentes.NOMBRES else {})
PY
fi
install -m 0644 "$RAIZ/config/systemd/leksso-admin.service" /etc/systemd/system/leksso-admin.service
systemctl enable leksso-admin.service >/dev/null 2>&1 || true
if [ -d /run/systemd/system ]; then systemctl daemon-reload; systemctl restart leksso-admin.service || true; fi
# Asistentes de IA: vienen instalados pero INACTIVOS; cada usuario elige cuál activa (leksso-asistente).
# Necesitan conexión: sin red se omiten y se instalan después, al elegirlos.
if apt-get install -y --no-install-recommends nodejs npm; then
  for paquete in @anthropic-ai/claude-code @openai/codex; do
    npm install -g "$paquete" >/dev/null 2>&1 || echo "AVISO: no se pudo instalar $paquete (¿sin conexión?). Se instalará al elegirlo."
  done
else
  echo "AVISO: sin Node (¿sin conexión?): los asistentes de IA se instalarán al elegirlos."
fi
install -m 0644 "$RAIZ/scripts/seccomp-estricta.py" /usr/local/lib/leksso-ia/seccomp-estricta.py
chmod 0755 /usr/local/bin/leksso-ia
U install -d "$HOME_USR/.config/kitty"
U install -m 0644 "$RAIZ/config/kitty/kitty.conf" "$HOME_USR/.config/kitty/kitty.conf"
# Explorador: árbol de carpetas y barra de ruta con botones.
U install -d "$HOME_USR/.config/pcmanfm-qt/default"
U install -m 0644 "$RAIZ/config/pcmanfm-qt/settings.conf" "$HOME_USR/.config/pcmanfm-qt/default/settings.conf"
# Red: NetworkManager gestiona las interfaces (estado y redes disponibles en la barra).
if [ -f /etc/network/interfaces ] && grep -qE '^(allow-hotplug|auto|iface) (e|w)' /etc/network/interfaces; then
  cp -n /etc/network/interfaces /etc/network/interfaces.leksso-antes
  sed -i -E 's/^(allow-hotplug|auto) (e|w)/# /; s/^iface (e|w)/#iface /' /etc/network/interfaces
  systemctl restart NetworkManager || true
fi

# Lanzador de aplicaciones con la paleta de LeksSO y sin entradas técnicas.
U install -d "$HOME_USR/.config/fuzzel" "$HOME_USR/.local/share/applications"
U install -m 0644 "$RAIZ/config/fuzzel/fuzzel.ini" "$HOME_USR/.config/fuzzel/fuzzel.ini"
U install -m 0644 "$RAIZ"/config/applications-ocultas/*.desktop "$HOME_USR/.local/share/applications/"

# Notificaciones y pantalla de bloqueo con la paleta de LeksSO.
install -d /usr/share/leksso
python3 "$RAIZ/scripts/generar-pantalla-bloqueo.py" /usr/share/leksso/bloqueo.png || true
U install -d "$HOME_USR/.config/mako" "$HOME_USR/.config/swaylock"
U install -m 0644 "$RAIZ/config/mako/config" "$HOME_USR/.config/mako/config"
U install -m 0644 "$RAIZ/config/swaylock/config" "$HOME_USR/.config/swaylock/config"

# Versión y actualizaciones: la versión instalada, la clave con la que se comprueban las versiones nuevas
# y la comprobación diaria. La clave instalada solo cambia con una versión ya firmada por la anterior.
install -m 0755 "$RAIZ/scripts/leksso-actualizar.py" /usr/local/bin/leksso-actualizar
install -d -m 0755 /etc/leksso /var/lib/leksso /etc/issue.d
install -m 0644 "$RAIZ/config/allowed_signers" /etc/leksso/allowed_signers
install -m 0644 "$RAIZ/VERSION" /etc/leksso-release
echo "LeksSO $(leksso-actualizar version | sed 's/^LeksSO //')" > /etc/issue.d/20-leksso.issue
install -m 0644 "$RAIZ"/config/systemd/leksso-actualizar.service "$RAIZ"/config/systemd/leksso-actualizar.timer /etc/systemd/user/
systemctl --global enable leksso-actualizar.timer >/dev/null 2>&1 || true

# Controladores y firmware: a los 3 minutos de arrancar y una vez al día, el sistema (como root) actualiza solo
# el microcódigo y el firmware de Debian y avisa del resto (NVIDIA, firmware de dispositivos), que se instalan
# con un clic en Ajustes → Actualizaciones. Ver scripts/leksso_hardware.py.
install -d -m 0755 /usr/local/lib/leksso
install -m 0644 "$RAIZ/scripts/leksso_hardware.py" /usr/local/lib/leksso/leksso_hardware.py
install -m 0644 "$RAIZ/scripts/generar-pantalla-bloqueo.py" /usr/local/lib/leksso/generar-pantalla-bloqueo.py   # la usa leksso-tema
install -m 0644 "$RAIZ"/config/systemd/leksso-hardware.service "$RAIZ"/config/systemd/leksso-hardware.timer /etc/systemd/system/
systemctl daemon-reload >/dev/null 2>&1 || true
systemctl enable leksso-hardware.timer >/dev/null 2>&1 || true

# Copias de seguridad (restic): el programa, el servicio y el temporizador del sistema. Quedan DESACTIVADAS hasta que el
# usuario las active en Ajustes, Copias; esta instalación nunca toca el horario ni la clave que él eligió (viven en
# /var/lib/leksso, /etc/leksso y leksso-copias.timer.d, que aquí no se escriben).
install -m 0755 "$RAIZ/scripts/leksso-copias.py" /usr/local/bin/leksso-copias
install -m 0644 "$RAIZ/config/systemd/leksso-copias.service" "$RAIZ/config/systemd/leksso-copias.timer" /etc/systemd/system/
systemctl daemon-reload >/dev/null 2>&1 || true

# Stream Deck: se inicia al conectarlo (el acceso a USB lo da la regla del paquete).
install -m 0644 "$RAIZ/config/systemd/leksso-streamdeck.service" "$RAIZ/config/systemd/leksso-permisor.service" /etc/systemd/user/
install -m 0644 "$RAIZ/config/udev/70-leksso-streamdeck.rules" /etc/udev/rules.d/
install -m 0644 "$RAIZ/config/udev/70-leksso-brillo.rules" /etc/udev/rules.d/      # brillo cambiable por el grupo video (teclas de brillo)
# fluidsynth (sintetizador MIDI que traen Lutris y otros) abre la tarjeta de sonido directamente y deja a PipeWire sin audio:
# su servicio de usuario se enmascara (no se usa en LeksSO).
ln -sf /dev/null /etc/systemd/user/fluidsynth.service
udevadm control --reload 2>/dev/null || true
udevadm trigger --subsystem-match=backlight --action=add 2>/dev/null || true

# Firmware y microcódigo según el hardware real (Wi-Fi, sonido, gráficos...). En una máquina virtual no hace falta
# (LEKSSO_HARDWARE=1 lo fuerza). isenkram detecta qué dispositivos hay y qué paquete de firmware necesitan.
if [ "$(systemd-detect-virt 2>/dev/null || echo none)" = "none" ] || [ "${LEKSSO_HARDWARE:-}" = "1" ]; then
  apt-get install -y --no-install-recommends isenkram-cli || true
  isenkram-autoinstall-firmware || true
  case "$(sed -n 's/^vendor_id[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo | head -1)" in
    GenuineIntel)   # portátiles Intel: Wi-Fi, sonido (SOF), gráficos, microcódigo y control térmico
      apt-get install -y --no-install-recommends intel-microcode thermald firmware-iwlwifi firmware-sof-signed         firmware-intel-misc firmware-intel-graphics || true ;;
    AuthenticAMD)
      apt-get install -y --no-install-recommends amd64-microcode firmware-amd-graphics || true ;;
  esac
fi

# Zonas del escritorio (sway) y alternativa labwc: ventanas con título y botones, barra de tareas en la barra superior.
U install -d "$HOME_USR/.config/labwc" "$HOME_USR/.local/share/themes"
U install -m 0644 "$RAIZ/config/labwc/rc.xml" "$RAIZ/config/labwc/menu.xml" "$HOME_USR/.config/labwc/"
U install -m 0755 "$RAIZ/config/labwc/autostart" "$HOME_USR/.config/labwc/autostart"
U cp -r "$RAIZ/config/labwc/tema/LeksSO" "$HOME_USR/.local/share/themes/"
install -m 0755 "$RAIZ/config/sway/zonas.sh" /usr/local/bin/leksso-zonas
U install -m 0644 "$RAIZ/config/bash_profile" "$HOME_USR/.bash_profile"
# Escritorio con iconos: carpeta Escritorio y accesos.
U install -m 0644 "$RAIZ/config/user-dirs.dirs" "$HOME_USR/.config/user-dirs.dirs"
U install -d "$HOME_USR/Escritorio" "$HOME_USR/Descargas" "$HOME_USR/Documentos" \
  "$HOME_USR/Imágenes" "$HOME_USR/Vídeos" "$HOME_USR/Música"   # las de «Lugares» en Archivos (solo salen las que existen)
U install -m 0755 "$RAIZ"/config/escritorio/*.desktop "$HOME_USR/Escritorio/"

# Programas predeterminados por tipo de archivo (no pisa lo que el usuario ya haya elegido).
install -m 0755 "$RAIZ/config/bin/leksso-info" "$RAIZ/config/bin/leksso-wine" "$RAIZ/config/bin/leksso-menu" "$RAIZ/config/bin/leksso-energia" "$RAIZ/config/bin/leksso-flotantes" "$RAIZ/config/bin/leksso-term" "$RAIZ/config/bin/leksso-medios" "$RAIZ/config/bin/leksso-captura" "$RAIZ/config/bin/leksso-reposo" "$RAIZ/config/bin/leksso-portapapeles" "$RAIZ/config/bin/leksso-ajustes" "$RAIZ/config/bin/leksso-redes" "$RAIZ/config/bin/leksso-actualizaciones" "$RAIZ/config/bin/leksso-panel-ia" "$RAIZ/config/bin/leksso-acceso-remoto" "$RAIZ/config/bin/leksso-instalador" "$RAIZ/config/bin/leksso-barra" "$RAIZ/config/bin/leksso-disco" "$RAIZ/config/bin/leksso-ts3" "$RAIZ/config/bin/leksso-hora" "$RAIZ/config/bin/leksso-reiniciar-en" "$RAIZ/config/bin/leksso-reparar" "$RAIZ/config/bin/leksso-archivos" "$RAIZ/config/bin/leksso-juego" "$RAIZ/config/bin/leksso-office-web" "$RAIZ/config/bin/leksso-secureboot" /usr/local/bin/
# Apagar y reiniciar no se quedan esperando a un servicio que no responde (por defecto serían hasta 2 minutos).
install -d /etc/systemd/system.conf.d /etc/systemd/user.conf.d /etc/systemd/system/user@.service.d /etc/systemd/user/mpris-proxy.service.d
printf '[Manager]
DefaultTimeoutStopSec=15s
' > /etc/systemd/system.conf.d/leksso-apagado.conf
printf '[Manager]
DefaultTimeoutStopSec=10s
' > /etc/systemd/user.conf.d/leksso-apagado.conf
printf '[Service]
TimeoutStopSec=20s
' > /etc/systemd/system/user@.service.d/leksso-apagado.conf
printf '[Service]
TimeoutStopSec=3s
' > /etc/systemd/user/mpris-proxy.service.d/leksso-apagado.conf
# Modo juego: perfiles de energía, GameMode y la parte de administrador (un solo ajuste, sin contraseña)
apt-get install -y --no-install-recommends power-profiles-daemon gamemode || echo "AVISO: sin power-profiles-daemon o gamemode (¿sin conexión?)"

# Firmware de las tarjetas de red inalámbricas (Intel, Realtek, Atheros, MediaTek, Broadcom y el general). Se instala SIEMPRE y desde el
# repositorio local durante la instalación: después, sin red, ya no habría forma de conseguirlo. Cada paquete por separado, para que un
# fallo no detenga la instalación.
for p in firmware-iwlwifi firmware-realtek firmware-atheros firmware-mediatek firmware-misc-nonfree firmware-brcm80211; do
  apt-get install -y --no-install-recommends "$p" || echo "AVISO: sin $p (¿sin conexión?); se instala después con red."
done

# Administración de discos (agente de permisos, GParted, Discos de GNOME, SMART, ampliar en caliente): OPCIONAL. Cada paquete por
# separado y sin que un fallo detenga la instalación: en una instalación sin red no están en el repositorio local y antes eso
# hacía caer todo («código 100»). Se instalan después con red (Aplicaciones, Utilidades) o con `sudo leksso-disco ampliar`.
for p in lxqt-policykit cloud-guest-utils parted smartmontools gparted gnome-disk-utility; do
  apt-get install -y --no-install-recommends "$p" || echo "AVISO: sin $p (¿sin conexión?); se instala después desde Aplicaciones."
done
install -m 0755 "$RAIZ/scripts/leksso-juego-raiz.sh" /usr/local/sbin/leksso-juego-raiz
printf '%%sudo ALL=(root) NOPASSWD: /usr/local/sbin/leksso-juego-raiz on, /usr/local/sbin/leksso-juego-raiz off
' > /etc/sudoers.d/leksso-juego
chmod 0440 /etc/sudoers.d/leksso-juego
visudo -cf /etc/sudoers.d/leksso-juego >/dev/null || rm -f /etc/sudoers.d/leksso-juego
install -d /usr/local/lib/leksso-ui
install -m 0644 "$RAIZ/config/ui/leksso_ui.py" "$RAIZ/config/ui/leksso_conexiones_ui.py" /usr/local/lib/leksso-ui/
install -m 0644 "$RAIZ"/config/applications/*.desktop /usr/share/applications/
install -m 0755 "$RAIZ/scripts/asociar-archivos.py" /usr/local/bin/leksso-asociar
install -m 0755 "$RAIZ/scripts/leksso-apps.py" /usr/local/bin/leksso-apps
install -m 0755 "$RAIZ/scripts/leksso-ts3-instalar.sh" /usr/local/bin/leksso-ts3-instalar
sudo -u "$USUARIO" leksso-asociar

# Temas de color: los archivos de colores por papel, el comando que los aplica y la ventana de Apariencia.
# La configuración base se acaba de copiar con los colores de Marea; si el usuario eligió otro tema, se vuelve a poner.
install -d -m 0755 /usr/local/share/leksso/temas
install -m 0644 "$RAIZ"/config/tema/*.json /usr/local/share/leksso/temas/
install -m 0755 "$RAIZ/scripts/leksso-tema.py" /usr/local/bin/leksso-tema
install -m 0755 "$RAIZ/config/bin/leksso-apariencia" /usr/local/bin/leksso-apariencia
install -m 0755 "$RAIZ/config/bin/leksso-copias-ui" /usr/local/bin/leksso-copias-ui
install -m 0755 "$RAIZ/config/bin/leksso-barra-bateria" "$RAIZ/config/bin/leksso-barra-perfil" /usr/local/bin/
sudo -u "$USUARIO" leksso-tema reaplicar || true
# La sesión abierta sigue con la configuración vieja (barra, atajos): se le pide que lea la nueva sin cerrar sesión.
sudo -u "$USUARIO" leksso-tema recargar || true

echo
# (Nada de «chown -R» sobre la carpeta personal: todo se creó ya COMO el usuario, ver U más arriba.)

# Teclado de la sesión según el del sistema (por defecto, español).
DISTRIB="$(. /etc/default/keyboard 2>/dev/null && echo "${XKBLAYOUT%%,*}")"
LOCAL="$HOME_USR/.config/sway/local.conf"
# Se reescribe COMO el usuario (sin seguir enlaces como root): se lee el archivo actual y se escribe uno nuevo suyo.
U bash -c 'LOCAL="$1"; D="$2"; tmp="$(mktemp "$LOCAL.XXXXXX")" || exit 1
  { grep -sv "xkb_layout" "$LOCAL" || true; echo "input type:keyboard xkb_layout ${D:-es}"; } > "$tmp"
  mv -f "$tmp" "$LOCAL"' _ "$LOCAL" "${DISTRIB:-es}"

# Cortafuegos, actualizaciones de seguridad y ajustes del núcleo (en Hyper-V deja el SSH abierto).
if [ "$(systemd-detect-virt 2>/dev/null || true)" = "microsoft" ]; then
  bash "$RAIZ/scripts/endurecer.sh" --ssh
else
  bash "$RAIZ/scripts/endurecer.sh"
fi

# Libera la caché de paquetes descargados (cientos de MB que no hacen falta).
updatedb >/dev/null 2>&1 || true   # primer índice de la búsqueda de archivos (menos de un segundo); luego lo renueva el temporizador de plocate
apt-get clean

echo "Listo. Reinicia: al iniciar sesión en la primera consola arranca el escritorio de LeksSO."

# Registro de instalaciones: temporizador de lo que aparece fuera de apt y primera foto (la línea base).
install -m 0644 "$RAIZ/config/systemd/leksso-auditoria-foto.service" "$RAIZ/config/systemd/leksso-auditoria-foto.timer" /etc/systemd/system/
install -m 0755 "$RAIZ/config/bin/leksso-seguridad" /usr/local/bin/leksso-seguridad
systemctl daemon-reload >/dev/null 2>&1 || true
systemctl enable --now leksso-auditoria-foto.timer >/dev/null 2>&1 || true
/usr/local/bin/leksso-auditoria foto >/dev/null 2>&1 || true

# Monitor de conexiones: sin procesos residentes (un temporizador cada minuto), con la lista de confianza de fábrica aparte
# de la del usuario (/var/lib/leksso-conexiones, que esta instalación nunca toca) y los bloqueos recargados al arrancar.
install -m 0755 "$RAIZ/scripts/leksso-conexiones.py" /usr/local/bin/leksso-conexiones
install -d /usr/local/share/leksso
install -m 0644 "$RAIZ/config/conexiones/confiables-de-fabrica.json" /usr/local/share/leksso/confiables-de-fabrica.json
install -m 0644 "$RAIZ/config/systemd/leksso-conexiones-foto.service" "$RAIZ/config/systemd/leksso-conexiones-foto.timer" \
  "$RAIZ/config/systemd/leksso-bloqueos.service" /etc/systemd/system/
systemctl daemon-reload >/dev/null 2>&1 || true
systemctl enable --now leksso-conexiones-foto.timer >/dev/null 2>&1 || true
systemctl enable --now leksso-bloqueos.service >/dev/null 2>&1 || true
/usr/local/bin/leksso-conexiones foto >/dev/null 2>&1 || true

# Ya instalado lo nuevo: borrar lo que quedó con el nombre antiguo
bash "$(dirname "${BASH_SOURCE[0]}")/migrar-nombre.sh" "$USUARIO" limpiar || true
