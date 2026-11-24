#!/usr/bin/env python3
"""Servicio de administración de LeksSO: ejecuta como administrador las órdenes que le pasa el permisor.

Corre como root. Solo atiende si se cumplen las tres cosas:
  1. quien llama es el servicio del permisor de ese usuario (se comprueba el grupo de control y el programa);
  2. ese usuario tiene algún asistente activo con permiso de administración en /etc/leksso/asistentes.json;
  3. el mensaje es una orden de texto de tamaño razonable.
Quién puede pedir qué (qué asistente, si hay que preguntar) lo decide el permisor; esto es la última puerta.
Límite conocido: un programa que ya controla la cuenta del usuario puede suplantar al permisor. Por eso la
administración está apagada salvo que el usuario la encienda con su contraseña.
"""
import json
import os
import pwd
import socket
import socketserver
import struct
import subprocess
import sys

# Se arranca con «python3 -I»: se añade solo la carpeta del script (de root).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asistentes

RUTA = "/run/leksso-admin.sock"
MAX_LINEA = 64 * 1024
MAX_SALIDA = 400_000


SCRIPT_PERMISOR = b"/usr/local/lib/leksso-ia/permisor.py"


def parece_el_permisor(grupos, programa, orden, claves_entorno, uid):
    """Qué debe cumplir el proceso que llama. Todo se compara exacto, no por «contiene»:
    - su grupo de control es la unidad leksso-permisor.service del gestor de ESTE usuario (mientras la unidad
      verdadera corre, otra con el mismo nombre no puede existir);
    - el programa es python3 del sistema y la orden es exactamente «python3 -I permisor.py» (sin -c, sin módulos).
      El -I importa: con él Python no carga los paquetes del usuario (~/.local, archivos .pth) ni la carpeta
      actual, que es por donde un proceso del usuario podía meter código dentro del permisor verdadero;
    - no lleva variables que cambian lo que Python o el cargador importan (PYTHON*, LD_*)."""
    ruta = None
    for linea in grupos.splitlines():
        if linea.startswith("0::"):
            ruta = linea[3:]
    if not ruta:
        return False
    partes = [x for x in ruta.split("/") if x]
    if not partes or partes[-1] != "leksso-permisor.service" or f"user@{uid}.service" not in partes:
        return False
    if not (os.path.basename(programa).startswith("python3") and programa.startswith("/usr/bin/")):
        return False
    if len(orden) != 3 or not orden[0] or os.path.basename(orden[0].decode("utf-8", "replace")) not in (
            "python3", os.path.basename(programa)) or orden[1] != b"-I" or orden[2] != SCRIPT_PERMISOR:
        return False
    return not any(k.startswith(b"PYTHON") or k.startswith(b"LD_") for k in claves_entorno)


def _es_el_permisor(pid, uid):
    try:
        with open(f"/proc/{pid}/cgroup", encoding="utf-8") as f:
            grupos = f.read()
        programa = os.path.realpath(f"/proc/{pid}/exe")
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            orden = f.read().rstrip(b"\0").split(b"\0")
        with open(f"/proc/{pid}/environ", "rb") as f:
            claves = [x.split(b"=", 1)[0] for x in f.read().split(b"\0") if x]
    except OSError:
        return False
    return parece_el_permisor(grupos, programa, orden, claves, uid)


def ejecutar(orden, espera, casa):
    entorno = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root",
               "LANG": os.environ.get("LANG", "C.UTF-8"), "DEBIAN_FRONTEND": "noninteractive", "TERM": "dumb"}
    codigo, salida, vencio = asistentes.correr_acotado(
        ["/bin/bash", "-c", orden], espera, MAX_SALIDA, cwd=casa if os.path.isdir(casa) else "/", env=entorno)
    texto = salida.decode("utf-8", "replace")[-MAX_SALIDA:]
    if vencio:
        texto += f"\n[se cortó a los {espera} s]"
    return {"ok": True, "codigo": codigo, "salida": texto}


class H(socketserver.StreamRequestHandler):
    def handle(self):
        pid, uid, _ = struct.unpack("3i", self.request.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        try:
            r = self._atender(pid, uid)
        except Exception as e:      # nunca tumbar el servicio por una petición
            r = {"ok": False, "error": f"error interno: {type(e).__name__}"}
        try:
            self.wfile.write((json.dumps(r, ensure_ascii=False) + "\n").encode())
        except OSError:
            pass

    def _atender(self, pid, uid):
        if uid < 1000 or not _es_el_permisor(pid, uid):
            return {"ok": False, "error": "solo atiende al permisor de LeksSO"}
        usuario = pwd.getpwuid(uid)
        if not asistentes.alguno_administra(usuario.pw_name):
            return {"ok": False, "error": "ningún asistente tiene permiso de administración"}
        self.request.settimeout(30)
        linea = self.rfile.readline(MAX_LINEA + 1)
        if not linea or len(linea) > MAX_LINEA:
            return {"ok": False, "error": "mensaje no válido"}
        m = json.loads(linea)
        orden, espera = m.get("orden"), m.get("espera", 120)
        if not isinstance(orden, str) or not 0 < len(orden) <= 8000 or "\0" in orden:
            return {"ok": False, "error": "orden no válida"}
        if asistentes.toca_auditoria(orden) and not asistentes.lee_auditoria(orden):      # última puerta, ya como root
            return {"ok": False, "error": "el registro de seguridad no se puede tocar desde la IA"}
        if asistentes.toca_copias(orden):      # última puerta, ya como root
            return {"ok": False, "error": "las copias de seguridad no se pueden tocar desde la IA"}
        if isinstance(espera, bool) or not isinstance(espera, int):
            espera = 120
        self.request.settimeout(None)
        return ejecutar(orden, min(max(espera, 1), 1800), usuario.pw_dir)


def main():
    if os.path.exists(RUTA):
        os.unlink(RUTA)
    s = socketserver.ThreadingUnixStreamServer(RUTA, H)
    os.chmod(RUTA, 0o666)        # cualquiera puede llamar; quién es se comprueba en cada conexión
    s.daemon_threads = True
    s.serve_forever()


if __name__ == "__main__":
    main()
