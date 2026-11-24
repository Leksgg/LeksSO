#!/bin/sh
# Codex CLI dentro de la caja de IA en la nube, conectado al permisor de LeksSO.
#
# - Corre en `caja --ia-nube --red`: no ve tus archivos; su único camino a ellos es el permisor.
# - Su intérprete de órdenes propio (la herramienta «shell») está APAGADO (--disable shell_tool), igual que Claude Code entra con
#   --tools "": el asistente solo actúa por el servidor MCP del permisor. Antes conservaba un shell con la red de la caja abierta, y
#   un texto malicioso dentro de un archivo leído podía hacerle mandar ese contenido a cualquier servidor (hallazgo 10 de la
#   revisión de la 0.1.52). Con esto, lo único que sale de la caja por la red es la conversación con el servicio del asistente.
#   Su sandbox interno sigue desactivado porque no funciona anidado en la caja. Quien quiera el comportamiento anterior, bajo su
#   responsabilidad: LEKSSO_CODEX_CON_SHELL=1 leksso-codex (avisa en pantalla).
# - Su sesión y ajustes viven en una carpeta aparte (~/.leksso/codex), que es lo único que ve de tu usuario.
# Uso: leksso-codex [argumentos de codex]
if ! command -v codex >/dev/null 2>&1; then
  echo "Codex no está instalado todavía. Se instala ahora (necesita conexión y tu contraseña)."
  leksso-asistente instalar codex || exit 1
fi
CASA="${LEKSSO_CODEX_CASA:-$HOME/.leksso/codex}"
mkdir -p "$CASA" && chmod 700 "$CASA"

# Iniciar sesión: FUERA de la caja. Codex abre el navegador y espera la respuesta en http://localhost:1455; la red de la
# caja no tiene reenvío de puertos (a propósito), así que desde dentro el navegador acaba en «ruta no válida». Fuera de
# la caja solo se hace la autenticación; la sesión queda en la misma carpeta que luego ve la caja.
#   leksso-codex login            abre el navegador
#   leksso-codex login --device-auth   da un código para escribir en https://auth.openai.com/codex/device (sin navegador local)
if [ "${1:-}" = "login" ]; then
  shift
  CODEX_HOME="$CASA" exec codex login "$@"
fi
if ! CODEX_HOME="$CASA" codex login status >/dev/null 2>&1; then
  echo "Todavía no has iniciado sesión en Codex. Se hace ahora, fuera de la caja (solo la autenticación)."
  CODEX_HOME="$CASA" codex login || { echo "No se pudo iniciar sesión. Prueba: leksso-codex login --device-auth" >&2; exit 1; }
fi
NOTA='Estás en LeksSO, dentro de una caja: tu carpeta (/home/caja) NO es la del usuario y no tienes intérprete de órdenes propio. Para tocar archivos o ejecutar órdenes usa solo las herramientas del servidor MCP «leksso», con rutas del equipo real. Cada acción pasa por el permisor, que pide permiso al usuario o aplica el nivel que él eligió.'
# Sin shell propio salvo que el usuario lo pida expresamente (y entonces se le avisa).
SIN_SHELL="--disable shell_tool"
if [ "${LEKSSO_CODEX_CON_SHELL:-}" = 1 ]; then
  SIN_SHELL=""
  echo "AVISO: Codex conserva su intérprete de órdenes con la red de la caja abierta: lo que lea podría salir a cualquier servidor." >&2
fi
exec caja --ia-asistente codex --red --rw "$CASA" \
  --env CODEX_HOME=/home/caja/codex \
  --env LEKSSO_HOME_REAL="$HOME" \
  -- codex --sandbox danger-full-access $SIN_SHELL \
           -c 'mcp_servers.leksso.command="python3"' \
           -c 'mcp_servers.leksso.args=["/usr/local/lib/leksso-ia/mcp_permisor.py"]' \
           -c "developer_instructions='$NOTA'" "$@"
