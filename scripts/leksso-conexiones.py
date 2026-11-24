#!/usr/bin/env python3
"""Monitor de conexiones de LeksSO: quién habla con quién, si lo reconocemos y qué se puede hacer con ello.

Se instala como /usr/local/bin/leksso-conexiones. Un temporizador de systemd lo ejecuta cada minuto (no hay ningún proceso
residente) y la ventana Seguridad de Ajustes lo maneja con sudo.

Qué hace
  - Foto de las conexiones (ss) con el programa dueño de cada una, clasificada en: escuchando, entrantes, salientes a Internet,
    red local y solo en este equipo.
  - «Validada» o «sin validar»: validada es lo que el usuario confió (o viene de fábrica); nunca se dice «segura».
    Un programa se identifica por su paquete de Debian (o, si no viene de uno, por su ruta y su huella); lo que lance un
    programa en el que confías (los juegos de Steam, por ejemplo) hereda su confianza.
  - Avisa de: una entrada por SSH (al momento), programas nuevos sin validar (el icono de la barra) y programas que envían
    mucho más de lo habitual. Durante la primera semana solo aprende, sin avisar.
  - Acciones: confiar, parar ahora (puede volver) y bloquear un destino (permanente hasta que el usuario lo quite).

Qué NO garantiza (y la ventana lo dice)
  - Bloquear corta el destino (IP y puerto), no al programa: si el servidor cambia de dirección, el programa puede seguir.
  - Una foto cada minuto no ve las conexiones más cortas; UDP no lleva contador de bytes.
  - Un destino en el que ya confías puede usarse para sacar datos. Y quien tenga permisos de administrador puede apagarlo.

Uso (root salvo estado y barra)
  leksso-conexiones foto                 hace la foto y avisa de lo nuevo (lo llama el temporizador)
  leksso-conexiones listar               conexiones, bloqueos y confianzas en JSON (hace una foto fresca)
  leksso-conexiones confiar IDENT        confiar en un programa
  leksso-conexiones dejar-de-confiar IDENT
  leksso-conexiones parar IDENT PID EXE  parar ahora (se comprueba que el proceso sigue siendo ese)
  leksso-conexiones bloquear DESTINO [PUERTO] [--proto tcp|udp] [--origen TEXTO]
  leksso-conexiones desbloquear ID
  leksso-conexiones aplicar-bloqueos     vuelve a cargar los bloqueos (al arrancar o si se reinicia el cortafuegos)
  leksso-conexiones vistas               marca las novedades como vistas (apaga el aviso)
  leksso-conexiones borrar-historial     borra el historial de eventos
  leksso-conexiones estado | barra       resumen público (no hace falta ser root)
"""
import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import pwd
import re
import signal
import socket
import stat
import subprocess
import sys
import time

VERSION = 1
PRUEBAS = os.geteuid() != 0
RAIZ = os.environ.get("LEKSSO_CONEXIONES_RAIZ", "") if PRUEBAS else ""
DIR = RAIZ + "/var/lib/leksso-conexiones"
CONOCIDAS = DIR + "/conocidas.json"
PREVIAS = DIR + "/previas.json"
CONFIABLES = DIR + "/confiables.json"
BLOQUEOS = DIR + "/bloqueos.json"
EVENTOS = DIR + "/eventos.jsonl"
PUBLICO = RAIZ + "/var/lib/leksso/conexiones-estado.json"
DE_FABRICA = [RAIZ + "/usr/local/share/leksso/confiables-de-fabrica.json",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "conexiones", "confiables-de-fabrica.json")]
TABLA = "leksso_usuario"
SEMANA = 7 * 24 * 3600
RETENCION_EVENTOS = 30 * 24 * 3600
UMBRAL_ENVIO = 100 * 1024 * 1024          # un programa no se considera «enviando mucho» por debajo de 100 MB al día
FACTOR_ENVIO = 4                           # ni por debajo de 4 veces su media diaria

CATEGORIAS = ("entrante", "internet", "red_local", "escuchando", "local")
CERRANDO = {"TIME-WAIT", "FIN-WAIT-1", "FIN-WAIT-2", "CLOSING", "LAST-ACK", "SYN-RECV", "CLOSE"}
# Programas y servicios que no se pueden parar ni bloquear desde aquí: sin ellos el equipo pierde red, hora, sesión o actualizaciones.
NO_TOCAR_COMM = {"systemd", "systemd-resolve", "systemd-resolved", "systemd-timesyn", "systemd-timesyncd", "NetworkManager",
                 "wpa_supplicant", "dhclient", "dbus-daemon", "polkitd", "sway", "udevd", "systemd-udevd", "chronyd", "init"}
NO_TOCAR_RUTAS = ("/usr/lib/apt/methods/", "/usr/bin/apt", "/usr/bin/dpkg", "/usr/local/bin/leksso-", "/usr/local/lib/leksso-",
                  "/usr/lib/systemd/", "/lib/systemd/")
PUERTOS_VITALES = {53: "DNS", 67: "DHCP", 68: "DHCP", 123: "hora (NTP)", 853: "DNS cifrado"}


class Error(Exception):
    """Un fallo que se le cuenta al usuario tal cual."""


# ---------- utilidades ----------
def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, datos, modo=0o600):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".nuevo"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.chmod(tmp, modo)
    os.replace(tmp, ruta)


def ahora():
    return int(time.time())


def iso(t=None):
    return dt.datetime.fromtimestamp(t or ahora()).astimezone().isoformat(timespec="seconds")


def evento(tipo, texto, **extra):
    os.makedirs(DIR, mode=0o700, exist_ok=True)
    with open(EVENTOS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": iso(), "ts": ahora(), "tipo": tipo, "texto": texto, **extra}, ensure_ascii=False) + "\n")
    os.chmod(EVENTOS, 0o600)


def podar_eventos():
    try:
        lineas = open(EVENTOS, encoding="utf-8").read().splitlines()
    except OSError:
        return
    corte = ahora() - RETENCION_EVENTOS
    vivas = [l for l in lineas if (json.loads(l).get("ts", 0) if l.startswith("{") else 0) >= corte]
    if len(vivas) != len(lineas):
        with open(EVENTOS + ".nuevo", "w", encoding="utf-8") as f:
            f.write("\n".join(vivas) + ("\n" if vivas else ""))
        os.chmod(EVENTOS + ".nuevo", 0o600)
        os.replace(EVENTOS + ".nuevo", EVENTOS)


def notificar(titulo, texto, critico=False):
    """Avisa en la pantalla de quien tenga sesión; si no se puede, no pasa nada (queda el icono y el historial)."""
    if PRUEBAS:
        return
    try:
        for d in os.listdir("/run/user"):
            if d.isdigit() and os.path.exists(f"/run/user/{d}/bus"):
                u = pwd.getpwuid(int(d)).pw_name
                subprocess.run(["runuser", "-u", u, "--", "env", f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{d}/bus",
                                "notify-send", "-a", "leksso-conexiones", "-u", "critical" if critico else "normal",
                                "-t", "0" if critico else "15000", titulo, texto], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError, KeyError):
        pass


# ---------- leer lo que hay ----------
def a_ip(texto):
    texto = texto.strip("[]")
    if "%" in texto:
        texto = texto.split("%")[0]
    try:
        return ipaddress.ip_address(texto)
    except ValueError:
        return None


def partir(dirpuerto):
    """'[::1]:631' → ('::1', 631); '*:22' → ('*', 22); '0.0.0.0:*' → ('0.0.0.0', 0)."""
    ip, _, puerto = dirpuerto.rpartition(":")
    return ip.strip("[]"), (int(puerto) if puerto.isdigit() else 0)


LINEA_SS = re.compile(r"^(tcp|udp)\s+(\S+)\s+\d+\s+\d+\s+(\S+)\s+(\S+)\s*(.*)$")


def parsear_ss(texto):
    """Conexiones de la salida de `ss -H -tuanpiO`."""
    conexiones = []
    for linea in texto.splitlines():
        m = LINEA_SS.match(linea.strip())
        if not m:
            continue
        proto, estado, local, peer, resto = m.groups()
        lip, lpuerto = partir(local)
        pip, ppuerto = partir(peer)
        usuario = re.search(r'users:\(\("([^"]*)",pid=(\d+)', resto)
        enviados = re.search(r"bytes_sent:(\d+)", resto)
        recibidos = re.search(r"bytes_received:(\d+)", resto)
        conexiones.append({"proto": proto, "estado": estado, "local_ip": lip, "local_puerto": lpuerto, "peer_ip": pip,
                           "peer_puerto": ppuerto, "comm": usuario.group(1) if usuario else "", "pid": int(usuario.group(2)) if usuario else 0,
                           "enviados": int(enviados.group(1)) if enviados else 0, "recibidos": int(recibidos.group(1)) if recibidos else 0})
    return conexiones


def es_privada(ip):
    return ip is not None and (ip.is_private or ip.is_link_local) and not ip.is_loopback


def categoria(c, puertos_escucha):
    escucha = c["estado"] in ("LISTEN", "UNCONN") and c["peer_puerto"] == 0
    local, peer = a_ip(c["local_ip"]) if c["local_ip"] != "*" else None, a_ip(c["peer_ip"]) if c["peer_ip"] != "*" else None
    if escucha:
        return "escuchando"
    if (peer and peer.is_loopback) or (local and local.is_loopback and not peer):
        return "local"
    if c["estado"] == "ESTAB" and c["local_puerto"] in puertos_escucha:
        return "entrante"
    if es_privada(peer):
        return "red_local"
    if peer is None:
        return "local"
    return "internet"


def leer_ss():
    r = subprocess.run(["ss", "-H", "-tuanpiO"], capture_output=True, text=True, timeout=20)
    return r.stdout


def info_proceso(pid):
    """Datos de un proceso; None si ya no existe."""
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None
    try:
        stat = open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace").read()
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        cg = (open(f"/proc/{pid}/cgroup", encoding="utf-8", errors="replace").read().splitlines() or [""])[0]
        uid = os.stat(f"/proc/{pid}").st_uid
    except OSError:
        return None                        # el proceso terminó mientras se leía
    m = re.match(r"\d+ \((.*)\) \S (\d+)", stat)
    resto = stat[stat.rindex(")") + 2:].split()
    unidad = (re.findall(r"([^/]+\.(?:service|scope))", cg) or [""])[-1]
    return {"pid": pid, "ppid": int(m.group(2)) if m else 0, "comm": m.group(1) if m else "", "exe": exe.replace(" (deleted)", ""),
            "borrado": exe.endswith(" (deleted)"), "cmd": cmd[:300], "unidad": unidad, "uid": uid, "inicio": int(resto[19]) if len(resto) > 19 else 0}


_PAQUETES = {}
_HUELLAS = {}
_PAQ_DISCO = {}
PAQUETES = DIR + "/paquetes.json"


def dueno_paquete(ruta):
    """Paquete de Debian dueño del archivo, o '' si no viene de uno. Se guarda en disco por ruta y fecha del archivo: dpkg -S
    es lento y esto corre cada minuto."""
    if ruta in _PAQUETES:
        return _PAQUETES[ruta]
    if not _PAQ_DISCO:
        _PAQ_DISCO.update(leer_json(PAQUETES, {}))
    try:
        mtime = int(os.stat(ruta).st_mtime)
    except OSError:
        mtime = 0
    if ruta in _PAQ_DISCO and _PAQ_DISCO[ruta][0] == mtime:
        _PAQUETES[ruta] = _PAQ_DISCO[ruta][1]
        return _PAQUETES[ruta]
    pkg = ""
    for candidata in dict.fromkeys([ruta, os.path.realpath(ruta), ruta.replace("/usr/bin/", "/bin/", 1), ruta.replace("/usr/sbin/", "/sbin/", 1)]):
        r = subprocess.run(["dpkg", "-S", candidata], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout:
            pkg = r.stdout.split(":")[0].split(",")[0].strip()
            break
    _PAQUETES[ruta] = pkg
    _PAQ_DISCO[ruta] = [mtime, pkg]
    try:
        escribir_json(PAQUETES, _PAQ_DISCO)
    except OSError:
        pass
    return pkg


def leer_normal(ruta, n):
    """Lee hasta n bytes de un ARCHIVO NORMAL sin poder quedarse colgado: se abre sin bloquear y se comprueba, ya
    abierto, que no es una tubería, un dispositivo o similar (estos programas corren como root sobre rutas que
    el usuario puede cambiar). Devuelve (tipo_de_stat, datos)."""
    fd = os.open(ruta, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("no es un archivo normal")
        return st, os.read(fd, n)
    finally:
        os.close(fd)


def huella(ruta):
    try:
        st = os.stat(ruta)
        clave = (ruta, st.st_mtime_ns, st.st_size)
        if clave not in _HUELLAS:
            _HUELLAS[clave] = hashlib.sha256(leer_normal(ruta, 4_000_000)[1]).hexdigest()[:16]
        return _HUELLAS[clave]
    except OSError:
        return ""


def identidad(p):
    """Cómo se reconoce un programa: su paquete de Debian, o su ruta con su huella (si cambia, hay que volver a confiar)."""
    if not p:
        return "desconocido:?"
    pkg = dueno_paquete(p["exe"])
    if pkg:
        return "pkg:" + pkg
    h = huella(p["exe"])
    return f"bin:{p['exe']}#{h}" if h else f"desconocido:{p.get('comm', '?')}"


def ancestros(pid, limite=8):
    cadena, p = [], info_proceso(pid)
    while p and len(cadena) < limite:
        cadena.append(p)
        if p["ppid"] <= 1:
            break
        p = info_proceso(p["ppid"])
    return cadena


def confiables_de_fabrica():
    for ruta in DE_FABRICA:
        datos = leer_json(ruta, None)
        if datos:
            return set(datos.get("identidades", []))
    return set()


def confianza(ident, cadena_identidades, usuario, fabrica):
    """(estado, motivo): 'validada' si el programa o alguno de sus padres está en la lista de confianza."""
    for etiqueta, lista in (("tú", usuario), ("de fábrica", fabrica)):
        if ident in lista:
            return "validada", etiqueta
        for padre in cadena_identidades:
            if padre in lista:
                return "validada", f"hereda de {padre.split(':', 1)[1].split('#')[0]}"
    return "sin validar", ""


def puerto_nombre(puerto, proto):
    try:
        return socket.getservbyport(puerto, proto)
    except OSError:
        return ""


# ---------- la foto ----------
def hacer_foto():
    """Lee las conexiones, las clasifica y actualiza lo conocido. Devuelve (lista, novedades)."""
    texto = leer_ss()
    conexiones = parsear_ss(texto)
    puertos_escucha = {c["local_puerto"] for c in conexiones if c["estado"] in ("LISTEN", "UNCONN") and c["peer_puerto"] == 0 and c["local_puerto"]}
    usuario = set(leer_json(CONFIABLES, {}).get("identidades", {}))
    fabrica = confiables_de_fabrica()
    conocidas = leer_json(CONOCIDAS, {"_meta": {"aprende_hasta": ahora() + SEMANA}})
    meta = conocidas.setdefault("_meta", {"aprende_hasta": ahora() + SEMANA})
    aprendiendo = ahora() < meta.get("aprende_hasta", 0)
    previas = leer_json(PREVIAS, {})
    nuevas_previas = {}
    bloqueos = leer_json(BLOQUEOS, [])
    lista, novedades, entradas = [], [], []
    hoy = dt.date.today().isoformat()
    cache_proc = {}

    for c in conexiones:
        cat = categoria(c, puertos_escucha)
        if cat == "local":
            continue
        pid = c["pid"]
        if not pid and c["estado"] in CERRANDO:
            continue                                  # restos de una conexión que ya se cerró: el núcleo los guarda un rato sin dueño
        if pid not in cache_proc:
            cadena = ancestros(pid) if pid else []
            cache_proc[pid] = (cadena[0] if cadena else None, [identidad(p) for p in cadena[1:]] if cadena else [])
        p, padres = cache_proc[pid]
        ident = identidad(p) if p else f"desconocido:{c['comm'] or '?'}"
        estado, motivo = confianza(ident, padres, usuario, fabrica)
        clave = f"{c['proto']}|{c['local_ip']}:{c['local_puerto']}|{c['peer_ip']}:{c['peer_puerto']}|{pid}"
        nuevas_previas[clave] = c["enviados"]
        delta = max(0, c["enviados"] - previas[clave]) if clave in previas else c["enviados"]
        registro = {"ident": ident, "nombre": (p or {}).get("comm") or c["comm"] or "(sin proceso)", "paquete": ident[4:] if ident.startswith("pkg:") else "",
                    "exe": (p or {}).get("exe", ""), "unidad": (p or {}).get("unidad", ""), "pid": pid, "inicio": (p or {}).get("inicio", 0),
                    "uid": (p or {}).get("uid", -1), "cmd": (p or {}).get("cmd", ""), "categoria": cat, "proto": c["proto"], "estado_ss": c["estado"],
                    "local": f"{c['local_ip']}:{c['local_puerto']}", "destino": c["peer_ip"], "puerto": c["peer_puerto"] or c["local_puerto"],
                    "servicio": puerto_nombre(c["peer_puerto"] or c["local_puerto"], c["proto"]), "enviados": c["enviados"], "recibidos": c["recibidos"],
                    "confianza": estado, "por_que": motivo, "bloqueada": any(b["destino"] == c["peer_ip"] and b.get("puerto") in (0, None, c["peer_puerto"]) for b in bloqueos)}
        lista.append(registro)
        if cat == "escuchando" and (a_ip(c["local_ip"]) is None or a_ip(c["local_ip"]).is_loopback):
            continue                                  # solo cuenta lo que escucha hacia fuera del equipo
        k = conocidas.get(ident)
        if k is None:
            k = conocidas[ident] = {"primera": ahora(), "nueva": False, "visto": aprendiendo, "dias": {}, "nombre": registro["nombre"]}
            if estado == "sin validar" and not aprendiendo:
                k["nueva"] = True
                novedades.append(ident)
                evento("programa_nuevo", (f"{registro['nombre']} empieza a escuchar en el puerto {c['local_puerto']}" if cat == "escuchando" else
                                          f"{registro['nombre']} conecta por primera vez ({cat}, {c['peer_ip']}:{registro['puerto']})"), ident=ident)
        k["ultima"] = ahora()
        k["dias"][hoy] = k["dias"].get(hoy, 0) + delta
        k["dias"] = dict(sorted(k["dias"].items())[-14:])
        if cat == "entrante" and clave not in previas:
            entradas.append(registro)
            evento("entrada", f"Conexión entrante a {registro['nombre']} desde {c['peer_ip']}", ident=ident, origen=c["peer_ip"])

    for r in entradas:
        if r["nombre"].startswith("sshd"):
            notificar("Alguien ha entrado por SSH", f"Conexión desde {r['destino']} a {r['nombre']}. Si no eres tú, ciérrala en Ajustes, Seguridad.", critico=True)
    for ident, k in conocidas.items():
        if ident == "_meta" or aprendiendo or k.get("avisado") == hoy:
            continue
        previos = [v for d, v in k["dias"].items() if d != hoy]
        media = sum(previos) / len(previos) if len(previos) >= 3 else None
        hoy_enviado = k["dias"].get(hoy, 0)
        if media is not None and hoy_enviado > max(UMBRAL_ENVIO, FACTOR_ENVIO * media):
            k["avisado"] = hoy
            evento("envio_alto", f"{k.get('nombre', ident)} ha enviado {hoy_enviado // 1048576} MB hoy (lo habitual: {int(media) // 1048576} MB)", ident=ident)
            notificar("Un programa envía más de lo habitual", f"{k.get('nombre', ident)}: {hoy_enviado // 1048576} MB hoy (lo habitual: {int(media) // 1048576} MB).")
    escribir_json(CONOCIDAS, conocidas)
    escribir_json(PREVIAS, nuevas_previas)
    publicar(lista, conocidas, bloqueos, aprendiendo)
    podar_eventos()
    return lista, novedades


def publicar(lista, conocidas, bloqueos, aprendiendo):
    sin_ver = [i for i, k in conocidas.items() if i != "_meta" and k.get("nueva") and not k.get("visto")]
    envios = [e for e in recientes_eventos(86400) if e["tipo"] == "envio_alto"]
    datos = {"version": VERSION, "novedades": len(sin_ver), "envios_altos": len(envios), "bloqueos": len(bloqueos), "aprendiendo": aprendiendo,
             "internet": sum(1 for r in lista if r["categoria"] == "internet"), "entrantes": sum(1 for r in lista if r["categoria"] == "entrante"),
             "actualizado": iso()}
    try:
        escribir_json(PUBLICO, datos, 0o644)
    except OSError:
        pass


def recientes_eventos(segundos):
    corte = ahora() - segundos
    out = []
    try:
        for l in open(EVENTOS, encoding="utf-8").read().splitlines():
            e = json.loads(l)
            if e.get("ts", 0) >= corte:
                out.append(e)
    except (OSError, ValueError):
        pass
    return out


# ---------- confianza ----------
def validar_ident(ident):
    if not isinstance(ident, str) or not re.fullmatch(r"(pkg:[a-z0-9][a-z0-9+.\-]+|bin:/[^\0\n]{1,300}#[0-9a-f]{16}|desconocido:[^\0\n]{1,60})", ident):
        raise Error("Programa no válido.")
    return ident


def confiar(ident):
    validar_ident(ident)
    c = leer_json(CONFIABLES, {"identidades": {}})
    c["identidades"][ident] = {"desde": iso()}
    escribir_json(CONFIABLES, c)
    conocidas = leer_json(CONOCIDAS, {})
    if ident in conocidas:
        conocidas[ident]["visto"], conocidas[ident]["nueva"] = True, False
        escribir_json(CONOCIDAS, conocidas)
    evento("confianza", f"Confías en {ident}", ident=ident)


def dejar_de_confiar(ident):
    validar_ident(ident)
    c = leer_json(CONFIABLES, {"identidades": {}})
    c["identidades"].pop(ident, None)
    escribir_json(CONFIABLES, c)
    evento("confianza", f"Dejas de confiar en {ident}", ident=ident)


def vistas():
    conocidas = leer_json(CONOCIDAS, {})
    for k in conocidas.values():
        if isinstance(k, dict) and k.get("nueva"):
            k["visto"] = True
    escribir_json(CONOCIDAS, conocidas)
    d = leer_json(PUBLICO, {})
    d["novedades"] = 0
    try:
        escribir_json(PUBLICO, d, 0o644)
    except OSError:
        pass


# ---------- parar ----------
def intocable(p):
    if p["pid"] <= 1 or p["comm"] in NO_TOCAR_COMM or p["unidad"].startswith("systemd-") or p["unidad"] in ("NetworkManager.service", "dbus.service"):
        return True
    return any(p["exe"].startswith(r) for r in NO_TOCAR_RUTAS)


def parar(pid, exe, inicio):
    """Para un proceso (SIGTERM y, si sigue vivo, SIGKILL). Se comprueba que sigue siendo el mismo: ruta y momento de inicio."""
    p = info_proceso(int(pid))
    if not p:
        raise Error("Ese programa ya no está en marcha.")
    if p["exe"] != exe or (inicio and p["inicio"] != int(inicio)):
        raise Error("El programa ha cambiado desde que lo viste: vuelve a actualizar la lista.")
    if intocable(p):
        raise Error(f"{p['comm']} es necesario para que el equipo funcione (red, hora, sesión o actualizaciones): no se puede parar desde aquí.")
    unidad = p["unidad"] if p["unidad"].endswith(".service") else ""
    if unidad:
        subprocess.run(["systemctl", "stop", unidad], capture_output=True, timeout=60)
    else:
        os.kill(p["pid"], signal.SIGTERM)
    for _ in range(25):
        if not info_proceso(p["pid"]) or info_proceso(p["pid"])["inicio"] != p["inicio"]:
            break
        time.sleep(0.2)
    else:
        os.kill(p["pid"], signal.SIGKILL)
    evento("parado", f"Has parado {p['comm']} ({p['exe']})", ident=identidad(p))


# ---------- bloquear ----------
def nft(*args, entrada=None):
    return subprocess.run(["nft", *args], capture_output=True, text=True, input=entrada, timeout=30)


def resolutores():
    ips = set()
    for ruta in (RAIZ + "/etc/resolv.conf", RAIZ + "/run/systemd/resolve/resolv.conf"):
        try:
            ips |= {l.split()[1] for l in open(ruta).read().splitlines() if l.startswith("nameserver") and len(l.split()) > 1}
        except OSError:
            pass
    return ips


def puerta_de_enlace():
    try:
        r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=10)
        return set(re.findall(r"via (\S+)", r.stdout))
    except (OSError, subprocess.SubprocessError):
        return set()


def comprobar_bloqueable(destino, puerto, vitales_extra=()):
    """Lanza Error si bloquear ese destino dejaría al equipo sin red, nombres, hora o actualizaciones."""
    ip = a_ip(destino)
    if ip is None:
        raise Error("El destino debe ser una dirección IP.")
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
        raise Error("No se bloquea el propio equipo ni las direcciones especiales.")
    if es_privada(ip):
        raise Error("Eso es tu red local (el router, otros equipos): bloquearlo puede dejarte sin conexión. No se hace desde aquí.")
    if str(ip) in resolutores() or str(ip) in puerta_de_enlace() or str(ip) in set(vitales_extra):
        raise Error("Es el servidor de nombres o la puerta de salida de tu red: sin él no hay Internet. No se bloquea.")
    if puerto in PUERTOS_VITALES:
        raise Error(f"El puerto {puerto} es {PUERTOS_VITALES[puerto]}: sin él falla la red. No se bloquea.")
    return ip


def regla(b):
    puerto = f" {b['proto']} dport {b['puerto']}" if b.get("puerto") else f" meta l4proto {b['proto']}"
    familia = "ip6" if ":" in b["destino"] else "ip"
    return f'{familia} daddr {b["destino"]}{puerto} counter drop comment "leksso-bloqueo-{b["id"]}"'


def guion_de_bloqueos(bloqueos):
    """Todo lo necesario en un solo guion de nft: tabla propia (la de endurecer.sh no se toca), cadena de salida y una regla por bloqueo."""
    lineas = [f"add table inet {TABLA}",
              f"add chain inet {TABLA} salida {{ type filter hook output priority -10 ; policy accept ; }}",
              f"flush chain inet {TABLA} salida"]
    lineas += [f"add rule inet {TABLA} salida {regla(b)}" for b in bloqueos]
    return "\n".join(lineas) + "\n"


def aplicar_bloqueos():
    """Carga (o recarga) todos los bloqueos guardados: se llama al arrancar y cada vez que se reinicia el cortafuegos."""
    r = nft("-f", "-", entrada=guion_de_bloqueos(leer_json(BLOQUEOS, [])))
    if r.returncode != 0:
        raise Error("No se pudieron cargar los bloqueos en el cortafuegos: " + (r.stderr.strip()[-200:] or "sin respuesta"))


def bloquear(destino, puerto=0, proto="tcp", origen=""):
    ip = comprobar_bloqueable(destino, puerto)
    if proto not in ("tcp", "udp"):
        raise Error("Protocolo no válido.")
    bloqueos = leer_json(BLOQUEOS, [])
    if any(b["destino"] == str(ip) and b.get("puerto", 0) == puerto and b.get("proto") == proto for b in bloqueos):
        raise Error("Ese destino ya está bloqueado.")
    b = {"id": hashlib.sha256(f"{ip}{puerto}{proto}{ahora()}".encode()).hexdigest()[:8], "destino": str(ip), "puerto": puerto, "proto": proto,
         "desde": iso(), "origen": origen[:120]}
    bloqueos.append(b)
    escribir_json(BLOQUEOS, bloqueos)
    aplicar_bloqueos()
    # las conexiones que ya estaban abiertas se cortan (si el núcleo lo permite)
    subprocess.run(["ss", "-K", "dst", str(ip)] + (["dport", "=", f":{puerto}"] if puerto else []), capture_output=True, timeout=15)
    evento("bloqueo", f"Bloqueado {ip}{(':' + str(puerto)) if puerto else ''}/{proto}" + (f" (lo usaba {origen})" if origen else ""), id=b["id"])
    return b


def desbloquear(id_):
    bloqueos = leer_json(BLOQUEOS, [])
    quedan = [b for b in bloqueos if b["id"] != id_]
    if len(quedan) == len(bloqueos):
        raise Error("Ese bloqueo no existe.")
    escribir_json(BLOQUEOS, quedan)
    aplicar_bloqueos()
    evento("bloqueo", f"Quitado el bloqueo {id_}", id=id_)


# ---------- órdenes ----------
def exige_root():
    if not PRUEBAS and os.geteuid() != 0:
        sys.exit(json.dumps({"ok": False, "error": "Hace falta ser administrador (sudo)."}))


def agrupar(lista):
    """Una fila por (programa, categoría, destino, puerto, protocolo) con cuántas conexiones son y cuánto han enviado en total."""
    grupos = {}
    for r in lista:
        k = (r["ident"], r["categoria"], r["destino"], r["puerto"], r["proto"])
        g = grupos.get(k)
        if g is None:
            grupos[k] = dict(r, conexiones=1)
        else:
            g["conexiones"] += 1
            g["enviados"] += r["enviados"]
            g["recibidos"] += r["recibidos"]
    return list(grupos.values())


def listar():
    lista, _ = hacer_foto()
    lista = agrupar(lista)
    conocidas = leer_json(CONOCIDAS, {})
    for r in lista:
        k = conocidas.get(r["ident"], {})
        r["primera"] = k.get("primera"); r["nueva"] = bool(k.get("nueva") and not k.get("visto"))
    meta = conocidas.get("_meta", {})
    print(json.dumps({"conexiones": lista, "bloqueos": leer_json(BLOQUEOS, []),
                      "confiables": leer_json(CONFIABLES, {"identidades": {}})["identidades"],
                      "eventos": recientes_eventos(7 * 86400)[-60:][::-1],
                      "aprende_hasta": meta.get("aprende_hasta") if ahora() < meta.get("aprende_hasta", 0) else None},
                     ensure_ascii=False))


def estado():
    try:
        print(open(PUBLICO, encoding="utf-8").read())
    except OSError:
        print(json.dumps({"version": VERSION, "novedades": 0, "envios_altos": 0, "bloqueos": 0, "aprendiendo": True, "internet": 0, "entrantes": 0}))


def barra():
    d = leer_json(PUBLICO, {})
    avisos = []
    if d.get("novedades"):
        avisos.append(f"{d['novedades']} programa(s) nuevo(s) conectando sin validar")
    if d.get("envios_altos"):
        avisos.append(f"{d['envios_altos']} programa(s) enviando más de lo habitual")
    print(json.dumps({"text": "▲ Conexiones" if avisos else "", "tooltip": "\n".join(avisos), "class": "novedad" if avisos else ""}, ensure_ascii=False))


def main(a):
    p = argparse.ArgumentParser(prog="leksso-conexiones", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="orden", required=True)
    for n in ("foto", "listar", "aplicar-bloqueos", "vistas", "borrar-historial", "estado", "barra"):
        s.add_parser(n)
    for n in ("confiar", "dejar-de-confiar"):
        x = s.add_parser(n); x.add_argument("ident")
    x = s.add_parser("parar"); x.add_argument("ident"); x.add_argument("pid"); x.add_argument("exe"); x.add_argument("inicio", nargs="?", default=0)
    x = s.add_parser("bloquear"); x.add_argument("destino"); x.add_argument("puerto", nargs="?", type=int, default=0)
    x.add_argument("--proto", default="tcp"); x.add_argument("--origen", default="")
    x = s.add_parser("desbloquear"); x.add_argument("id")
    o = p.parse_args(a)
    if o.orden == "estado": estado(); return 0
    if o.orden == "barra": barra(); return 0
    exige_root()
    try:
        if o.orden == "foto": hacer_foto()
        elif o.orden == "listar": listar(); return 0
        elif o.orden == "confiar": confiar(o.ident)
        elif o.orden == "dejar-de-confiar": dejar_de_confiar(o.ident)
        elif o.orden == "parar": parar(o.pid, o.exe, o.inicio)
        elif o.orden == "bloquear": print(json.dumps({"ok": True, "bloqueo": bloquear(o.destino, o.puerto, o.proto, o.origen)})); return 0
        elif o.orden == "desbloquear": desbloquear(o.id)
        elif o.orden == "aplicar-bloqueos": aplicar_bloqueos()
        elif o.orden == "vistas": vistas()
        elif o.orden == "borrar-historial":
            if os.path.exists(EVENTOS):
                open(EVENTOS, "w").close()
        print(json.dumps({"ok": True}))
    except Error as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
