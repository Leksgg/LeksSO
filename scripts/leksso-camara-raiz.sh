#!/bin/sh
# Parte de administrador del bloqueo de la cámara. Solo acepta «on», «off» o «estado».
#
#   on      bloquea la cámara: quita el controlador (uvcvideo) y lo deja sin poder cargarse, también tras reiniciar.
#           Se permite SIN contraseña (ver /etc/sudoers.d/leksso-camara): bloquear es el lado seguro.
#   off     vuelve a permitirla. Pide contraseña (no está en sudoers): así un programa que corra con tu usuario no puede destaparla.
#   estado  imprime «bloqueada» o «permitida».
#
# Es un interruptor de verdad, como la tapa de una cámara: mientras está bloqueada, ningún programa puede usarla.
# Solo sirve para cámaras que usan el controlador estándar de Linux (uvcvideo), que son casi todas las del portátil.
CONF=/etc/modprobe.d/leksso-camara-bloqueada.conf
# Solo para las pruebas: una ruta distinta, y únicamente cuando NO se ejecuta como administrador (con sudo se ignora).
[ "$(id -u)" -ne 0 ] && [ -n "${LEKSSO_CAMARA_CONF:-}" ] && CONF="$LEKSSO_CAMARA_CONF"
case "${1:-}" in
  on)
    printf '# LeksSO: camara bloqueada (Camara y microfono, en la barra lateral). Para permitirla de nuevo: sudo leksso-camara-raiz off\ninstall uvcvideo /bin/false\n' > "$CONF.nuevo" || exit 1
    chmod 0644 "$CONF.nuevo"
    mv -f "$CONF.nuevo" "$CONF"
    if [ -d /sys/module/uvcvideo ]; then
      if ! modprobe -r uvcvideo 2>/dev/null; then
        rm -f "$CONF"      # no se pudo quitar: no se deja a medias
        echo "La cámara está en uso: ciérrala (o cierra el programa que la usa) y vuelve a intentarlo." >&2
        exit 3
      fi
    fi
    ;;
  off)
    rm -f "$CONF" "$CONF.nuevo"
    modprobe uvcvideo 2>/dev/null || true
    ;;
  estado)
    if [ -e "$CONF" ]; then echo bloqueada; else echo permitida; fi
    ;;
  *)
    echo "Uso: leksso-camara-raiz on|off|estado" >&2
    exit 2
    ;;
esac
