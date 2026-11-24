#!/usr/bin/env python3
"""Copias de seguridad de LeksSO: restic, un repositorio cifrado de root y un temporizador de systemd.

Se instala como /usr/local/bin/leksso-copias. Lo ejecutan, como root, el servicio leksso-copias.service (a la hora que
eligió el usuario) y la ventana de Copias de Ajustes (con sudo). La IA no puede tocarlo: el permisor y el servicio de
administración rechazan cualquier orden que lo nombre, y el repositorio y la clave son de root con permisos 0700/0400.

Qué hace
  - Copia las carpetas personales (/home/<usuario>) sin cachés ni papelera.
  - Guarda como máximo 5 copias: tras cada copia comprueba el repositorio y solo si está sano borra las que sobran,
    empezando por la más antigua.
  - Nunca restaura encima de lo que ya hay: lo recuperado va a ~/Recuperado/<fecha>/.

Uso
  leksso-copias estado                 resumen en JSON (no hace falta ser root)
  leksso-copias barra                  texto para la barra: vacío si todo va bien (no hace falta ser root)
  leksso-copias activar                activa las copias (JSON por la entrada estándar, o pregunta en el terminal)
  leksso-copias configurar             cambia frecuencia y hora
  leksso-copias desactivar             las deja de hacer; las copias hechas se conservan
  leksso-copias ejecutar [--ahora]     hace una copia (lo llama el temporizador; --ahora ignora el aviso de batería)
  leksso-copias listar [ID [RUTA]]     copias disponibles, o el contenido de una carpeta de una copia (JSON)
  leksso-copias restaurar ID RUTA      recupera esa ruta en ~/Recuperado/
"""
import argparse
import datetime as dt
import fcntl
import getpass
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

MAX_COPIAS = 5
VERSION_CONFIG = 1
FRECUENCIAS = {"diaria": "*-*-*", "semanal": "Mon *-*-*", "mensual": "*-*-01"}
DIAS = {"diaria": 1, "semanal": 7, "mensual": 31}
EXCLUIR_NOMBRES = (".cache", "Recuperado", "snap")      # carpetas con este nombre, a cualquier profundidad
EXCLUIR_RUTAS = ("/home/*/.local/share/Trash", "/home/*/.local/share/Steam/steamapps", "/home/*/.var/app/*/cache")

# Las rutas cuelgan de RAIZ para poder probarlo sin tocar el sistema. Esos cambios solo valen si NO eres root: así nadie
# puede desviar la copia de root con variables de entorno.
PRUEBAS = os.geteuid() != 0
RAIZ = os.environ.get("LEKSSO_COPIAS_RAIZ", "") if PRUEBAS else ""
CONFIG = RAIZ + "/var/lib/leksso/copias.json"
ESTADO = RAIZ + "/var/lib/leksso/copias-estado.json"
REPO = RAIZ + "/var/lib/leksso-copias"
CLAVE = RAIZ + "/etc/leksso/copias.key"
HORARIO = RAIZ + "/etc/systemd/system/leksso-copias.timer.d/horario.conf"
CERROJO = RAIZ + "/run/leksso-copias.lock"
RESTIC = os.environ.get("LEKSSO_RESTIC", "restic") if PRUEBAS else "restic"
SIN_SYSTEMD = PRUEBAS and os.environ.get("LEKSSO_COPIAS_SIN_SYSTEMD") == "1"


class Error(Exception):
    """Un fallo que se le cuenta al usuario tal cual."""


# ---------- datos puros (se prueban sin restic) ----------
def calendario(frecuencia, hora):
    """OnCalendar de systemd para esa frecuencia y hora."""
    if frecuencia not in FRECUENCIAS:
        raise Error("La frecuencia debe ser diaria, semanal o mensual.")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora or ""):
        raise Error("La hora debe ser como 03:30.")
    return f"{FRECUENCIAS[frecuencia]} {hora}:00"


MIN_CLAVE = 10          # antes 4: la clave se guarda junto al repositorio, y solo protege si el repositorio sale del equipo


def validar_clave(clave):
    if not isinstance(clave, str) or not MIN_CLAVE <= len(clave) <= 200 or "\n" in clave or "\0" in clave:
        raise Error(f"La clave debe tener entre {MIN_CLAVE} y 200 caracteres y una sola línea (una frase larga vale).")
    return clave


def discos_de(texto_lsblk):
    """Discos físicos de la salida de `lsblk -sno NAME,TYPE <dispositivo>` (las capas de LVM, cifrado y particiones
    se resuelven hasta el disco)."""
    discos = set()
    for linea in texto_lsblk.splitlines():
        partes = linea.split()
        if len(partes) >= 2 and partes[-1] == "disk":
            discos.add(re.sub(r"^[^\w]+", "", partes[0]))
    return discos


def hace_falta_espacio(libre, total):
    """Mínimo libre en el disco del repositorio para empezar una copia: 2 GiB o el 5 % del disco, lo que sea mayor."""
    return max(2 * 1024 ** 3, total // 20)


def vieja(ultima_ok, frecuencia, ahora=None):
    """True si la última copia buena tiene más de dos periodos y un día de antigüedad (o no hay ninguna)."""
    if not ultima_ok:
        return True
    ahora = ahora or dt.datetime.now().astimezone()
    try:
        f = dt.datetime.fromisoformat(ultima_ok)
    except ValueError:
        return True
    return (ahora - f) > dt.timedelta(days=2 * DIAS.get(frecuencia, 1) + 1)


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, datos, modo=0o644):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".nuevo"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, modo)
    os.replace(tmp, ruta)


def configuracion():
    c = leer_json(CONFIG, {})
    return {"version": VERSION_CONFIG, "activa": bool(c.get("activa", False)),
            "frecuencia": c.get("frecuencia", "diaria") if c.get("frecuencia") in FRECUENCIAS else "diaria",
            "hora": c.get("hora", "03:00") if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", c.get("hora", "")) else "03:00"}


# ---------- restic ----------
def restic(*args, entrada=None, comprobar=True):
    env = dict(os.environ, RESTIC_REPOSITORY=REPO, RESTIC_PASSWORD_FILE=CLAVE, RESTIC_CACHE_DIR=RAIZ + "/var/cache/leksso-copias")
    r = subprocess.run([RESTIC, *args], capture_output=True, text=True, env=env, input=entrada)
    if comprobar and r.returncode != 0:
        ultimas = (r.stderr.strip() or r.stdout.strip()).splitlines()[-3:]
        raise Error(" ".join(ultimas)[:300] or f"restic terminó con el código {r.returncode}")
    return r


def repositorio_listo():
    return os.path.exists(os.path.join(REPO, "config")) and os.path.exists(CLAVE)


def copias():
    """Copias guardadas, de la más nueva a la más antigua: [{id, fecha}]."""
    datos = json.loads(restic("snapshots", "--json").stdout or "[]")
    return sorted(({"id": s["short_id"], "fecha": s["time"]} for s in datos), key=lambda s: s["fecha"], reverse=True)


def sobrantes(lista, parciales, maximo):
    """Qué copias borrar al pasar del máximo. None = lo de siempre (quedarse con las `maximo` más nuevas). Si esas
    más nuevas fueran TODAS parciales (con archivos saltados) y hubiera una completa más vieja, se devuelve la lista
    explícita de las que sobran dejando a salvo la completa más reciente: así varias copias parciales seguidas no
    pueden dejarte sin ninguna copia entera."""
    nuevas = sorted(lista, key=lambda s: s["fecha"], reverse=True)
    if len(nuevas) <= maximo:
        return None
    guardadas = nuevas[:maximo]
    if any(s["id"] not in parciales for s in guardadas):
        return None
    completa = next((s for s in nuevas[maximo:] if s["id"] not in parciales), None)
    if not completa:
        return None
    mantener = {s["id"] for s in guardadas[:maximo - 1]} | {completa["id"]}
    return [s["id"] for s in nuevas if s["id"] not in mantener]


def carpetas_personales():
    forzadas = os.environ.get("LEKSSO_COPIAS_HOMES") if PRUEBAS else None
    if forzadas:
        return [h for h in forzadas.split(":") if os.path.isdir(h)]
    return [u.pw_dir for u in pwd.getpwall() if u.pw_uid >= 1000 and u.pw_uid < 60000 and os.path.isdir(u.pw_dir)
            and u.pw_dir.startswith("/home/")]


def mismo_disco():
    """True si el repositorio y las carpetas personales comparten disco físico (o no se sabe: se avisa por si acaso)."""
    def discos(ruta):
        try:
            fuente = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target", ruta], capture_output=True, text=True, timeout=10).stdout.strip()
            return discos_de(subprocess.run(["lsblk", "-sno", "NAME,TYPE", fuente], capture_output=True, text=True, timeout=10).stdout)
        except (OSError, subprocess.SubprocessError):
            return set()
    a = discos(REPO if os.path.isdir(REPO) else os.path.dirname(REPO))
    b = set()
    for h in carpetas_personales() or ["/home"]:
        b |= discos(h)
    return True if not a or not b else bool(a & b)


# ---------- estado ----------
def guardar_estado(resultado, mensaje, inicio=None, **extra):
    e = leer_json(ESTADO, {})
    ahora = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    e["version"] = VERSION_CONFIG
    e["ultima"] = {"fecha": ahora, "resultado": resultado, "mensaje": mensaje,
                   "duracion_s": round((dt.datetime.now().astimezone() - inicio).total_seconds()) if inicio else 0}
    if resultado == "ok":                 # una copia con archivos saltados NO cuenta como copia correcta
        e["ultima_ok"] = ahora
    elif resultado == "aviso":
        e["ultima_aviso"] = ahora
    e.update(extra)
    escribir_json(ESTADO, e)


def notificar(titulo, texto, critico=True):
    """Avisa en la pantalla de quien tenga sesión abierta; si no se puede, no pasa nada (queda el estado y la barra).
    Todos los avisos llevan la misma etiqueta: uno nuevo sustituye al anterior, así «ha vuelto a funcionar» quita el de «ha fallado»."""
    if SIN_SYSTEMD or os.geteuid() != 0:
        return
    try:
        for d in os.listdir("/run/user"):
            if d.isdigit() and os.path.exists(f"/run/user/{d}/bus"):
                u = pwd.getpwuid(int(d)).pw_name
                subprocess.run(["runuser", "-u", u, "--", "env", f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{d}/bus",
                                "notify-send", "-a", "leksso-copias", "-u", "critical" if critico else "normal",
                                "-t", "0" if critico else "8000", "--hint=string:x-canonical-private-synchronous:leksso-copias", titulo, texto],
                               capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError, KeyError):
        pass


def en_bateria():
    try:
        for d in os.listdir("/sys/class/power_supply"):
            base = os.path.join("/sys/class/power_supply", d)
            if open(os.path.join(base, "type")).read().strip() == "Mains":
                return open(os.path.join(base, "online")).read().strip() == "0"
    except OSError:
        pass
    return False


# ---------- órdenes ----------
def sistema(*orden):
    if SIN_SYSTEMD:
        return
    subprocess.run(orden, capture_output=True, timeout=60)


def poner_horario(frecuencia, hora):
    os.makedirs(os.path.dirname(HORARIO), exist_ok=True)
    with open(HORARIO + ".nuevo", "w", encoding="utf-8") as f:
        f.write(f"[Timer]\nOnCalendar=\nOnCalendar={calendario(frecuencia, hora)}\n")
    os.replace(HORARIO + ".nuevo", HORARIO)
    sistema("systemctl", "daemon-reload")


def datos_de_entrada(clave_necesaria):
    """Frecuencia, hora y clave: de un JSON por la entrada estándar o, en un terminal, preguntando."""
    if not sys.stdin.isatty():
        try:
            return json.loads(sys.stdin.read() or "{}")
        except ValueError:
            raise Error("Datos no válidos.")
    cfg = configuracion()
    f = input(f"Frecuencia (diaria, semanal o mensual) [{cfg['frecuencia']}]: ").strip() or cfg["frecuencia"]
    h = input(f"Hora (HH:MM) [{cfg['hora']}]: ").strip() or cfg["hora"]
    datos = {"frecuencia": f, "hora": h}
    if clave_necesaria:
        print("Elige la clave de las copias. Sin ella no se pueden recuperar: guárdala en un sitio seguro.")
        a, b = getpass.getpass("Clave: "), getpass.getpass("Repite la clave: ")
        if a != b:
            raise Error("Las dos claves no coinciden.")
        datos["clave"] = a
    return datos


def activar(solo_horario=False):
    if os.geteuid() != 0 and not RAIZ:
        raise Error("Hace falta ser administrador (sudo).")
    cfg = configuracion()
    nueva_clave = not repositorio_listo()
    d = datos_de_entrada(nueva_clave and not solo_horario)
    frecuencia, hora = d.get("frecuencia", cfg["frecuencia"]), d.get("hora", cfg["hora"])
    calendario(frecuencia, hora)  # valida
    if not solo_horario and nueva_clave:
        validar_clave(d.get("clave"))
        os.makedirs(os.path.dirname(CLAVE), exist_ok=True)
        if os.path.exists(CLAVE):       # sobra de un intento anterior sin repositorio
            os.remove(CLAVE)
        fd = os.open(CLAVE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(fd, "w") as f:
            f.write(d["clave"])
        os.makedirs(REPO, mode=0o700, exist_ok=True)
        os.chmod(REPO, 0o700)
        try:
            restic("init")
        except Error:
            os.remove(CLAVE)  # sin repositorio no hay clave que guardar
            raise
    elif not solo_horario and not repositorio_listo():
        raise Error("Falta el repositorio de copias. Desactívalas y vuelve a activarlas.")
    escribir_json(CONFIG, {"version": VERSION_CONFIG, "activa": cfg["activa"] or not solo_horario, "frecuencia": frecuencia, "hora": hora})
    poner_horario(frecuencia, hora)
    if not solo_horario or cfg["activa"]:
        sistema("systemctl", "enable", "--now", "leksso-copias.timer")
    print(json.dumps({"ok": True}))


def desactivar():
    if os.geteuid() != 0 and not RAIZ:
        raise Error("Hace falta ser administrador (sudo).")
    cfg = configuracion()
    escribir_json(CONFIG, {"version": VERSION_CONFIG, "activa": False, "frecuencia": cfg["frecuencia"], "hora": cfg["hora"]})
    sistema("systemctl", "disable", "--now", "leksso-copias.timer")
    print(json.dumps({"ok": True}))


def ejecutar(ahora=False):
    if os.geteuid() != 0 and not RAIZ:
        raise Error("Hace falta ser administrador (sudo).")
    cfg = configuracion()
    os.makedirs(os.path.dirname(CERROJO), exist_ok=True)
    bloqueo = open(CERROJO, "w")
    try:
        fcntl.flock(bloqueo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Ya hay una copia en marcha."); return 0
    inicio = dt.datetime.now().astimezone()
    e = leer_json(ESTADO, {})
    if not ahora and en_bateria() and not vieja(e.get("ultima_ok"), cfg["frecuencia"]):
        guardar_estado("pospuesta", "Pospuesta: el equipo iba con batería. Se hará en la próxima ocasión.", inicio)
        print("Pospuesta por la batería."); return 0
    try:
        if not repositorio_listo():
            raise Error("Falta el repositorio de copias. Activa las copias en Ajustes.")
        total, _, libre = shutil.disk_usage(REPO)
        if libre < hace_falta_espacio(libre, total):
            raise Error("El disco está casi lleno: no se hace la copia para no llenarlo del todo. Libera espacio.")
        homes = carpetas_personales()
        if not homes:
            raise Error("No hay carpetas personales que copiar.")
        excluir = [x for n in EXCLUIR_NOMBRES for x in ("--exclude", n)] + [x for r in EXCLUIR_RUTAS for x in ("--exclude", r)]
        r = restic("backup", "--tag", "leksso", "--host", "leksso", "--exclude-caches", *excluir, *homes, comprobar=False)
        if r.returncode not in (0, 3):
            ultimas = (r.stderr.strip() or r.stdout.strip()).splitlines()[-3:]
            raise Error("No se pudo hacer la copia: " + " ".join(ultimas)[:260])
        aviso = "Algunos archivos no se pudieron leer y se saltaron." if r.returncode == 3 else ""
        parciales = list(e.get("parciales", []))
        if r.returncode == 3:
            nueva = copias()
            if nueva:
                parciales.append(nueva[0]["id"])
        # solo si el repositorio está sano se borran las copias que sobran
        restic("check", "--read-data-subset=10%")      # estructura y, además, una parte al azar de los datos
        sobran = sobrantes(copias(), parciales, MAX_COPIAS)
        if sobran is None:
            restic("forget", "--group-by", "", "--keep-last", str(MAX_COPIAS), "--prune")
        else:                                           # se conserva la última copia completa aunque sea más vieja
            restic("forget", "--prune", *sobran)
        lista = copias()
        parciales = [p for p in parciales if p in {x["id"] for x in lista}]
        espacio = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(REPO) for f in fs)
        habia_fallado = (e.get("ultima") or {}).get("resultado") == "fallo"
        guardar_estado("aviso" if aviso else "ok", aviso or "Copia hecha y comprobada.", inicio, snapshots=lista, espacio_repo=espacio,
                       parciales=parciales)
        if habia_fallado:
            notificar("Las copias de seguridad vuelven a funcionar", "La última copia se hizo y se comprobó bien.", critico=False)
        print("Copia hecha." + (" " + aviso if aviso else ""))
        return 0
    except Error as err:
        guardar_estado("fallo", str(err), inicio)
        notificar("La copia de seguridad ha fallado", str(err))
        print("FALLO:", err, file=sys.stderr)
        return 1


def listar(copia=None, ruta=None):
    if not copia:
        print(json.dumps(copias(), ensure_ascii=False)); return
    if not re.fullmatch(r"[0-9a-f]{6,64}", copia):
        raise Error("Copia no válida.")
    ruta = ruta or "/"
    if "\0" in ruta or ".." in ruta.split("/"):
        raise Error("Ruta no válida.")
    propio = None
    if os.environ.get("SUDO_USER") or (PRUEBAS and os.environ.get("LEKSSO_COPIAS_USUARIO")):
        propio = usuario_que_pide().pw_dir       # quien llama con sudo solo ve lo suyo, no las carpetas de otros usuarios
    r = restic("ls", "--json", copia, ruta)
    padre = ruta.rstrip("/") or "/"
    hijos = []
    for linea in r.stdout.splitlines():
        try:
            n = json.loads(linea)
        except ValueError:
            continue
        if n.get("struct_type") != "node" or os.path.dirname(n["path"]) != padre:
            continue
        if propio and not (propio == n["path"] or propio.startswith(n["path"] + "/") or n["path"].startswith(propio + "/")):
            continue
        hijos.append({"nombre": n["name"], "ruta": n["path"], "tipo": n["type"], "tamano": n.get("size", 0)})
    print(json.dumps(sorted(hijos, key=lambda h: (h["tipo"] != "dir", h["nombre"].lower())), ensure_ascii=False))


def usuario_que_pide():
    nombre = os.environ.get("SUDO_USER") or (os.environ.get("LEKSSO_COPIAS_USUARIO") if PRUEBAS else None)
    if not nombre or nombre == "root":
        raise Error("Indica de qué usuario es la recuperación (usa sudo desde tu usuario).")
    return pwd.getpwnam(nombre)


COPIAR = ("import os, shutil, sys\n"
          "o, base, nombre = sys.argv[1:]\n"
          "os.makedirs(base, exist_ok=True)\n"
          "for i in range(1, 1000):\n"
          "    d = os.path.join(base, nombre if i == 1 else '%s-%d' % (nombre, i))\n"
          "    try:\n"
          "        os.mkdir(d)\n"
          "        break\n"
          "    except FileExistsError:\n"
          "        continue\n"
          "else:\n"
          "    sys.exit('no hay un destino libre')\n"
          "shutil.copytree(o, d, symlinks=True, dirs_exist_ok=True)\n"
          "print(d)\n")


def literal_para_restic(ruta):
    """restic trata --include como un patrón (* ? [ ] \\): se escapa para que la ruta se tome tal cual."""
    return re.sub(r"([\\*?\[])", lambda m: "\\" + m.group(1), ruta)


def _copiar_como_usuario(u, origen, base, nombre):
    """Copia lo recuperado a una carpeta NUEVA y exclusiva de «base» CON los permisos del usuario (como root solo si
    no hay otro). Cada recuperación tiene su carpeta: nunca mezcla ni pisa una anterior. Devuelve la carpeta."""
    orden = [sys.executable, "-I", "-c", COPIAR, origen, base, nombre]
    if os.geteuid() == 0 and u.pw_uid != 0:
        orden = ["runuser", "-u", u.pw_name, "--"] + orden
    r = subprocess.run(orden, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise Error("No se pudo dejar lo recuperado en tu carpeta: " + (r.stderr.strip().splitlines() or ["error"])[-1][:200])
    return r.stdout.strip().splitlines()[-1]


def restaurar(copia, ruta):
    if not re.fullmatch(r"[0-9a-f]{6,64}", copia):
        raise Error("Copia no válida.")
    u = usuario_que_pide()
    if "\0" in ruta or ".." in ruta.split("/") or not (ruta + "/").startswith(u.pw_dir + "/"):
        raise Error("Solo se pueden recuperar archivos de tu propia carpeta personal.")
    fecha = next((s["fecha"] for s in copias() if s["id"] == copia), None)
    if not fecha:
        raise Error("Esa copia ya no existe.")
    base = os.path.join(u.pw_dir, "Recuperado")
    nombre = dt.datetime.fromisoformat(fecha).strftime("%Y-%m-%d_%H%M")
    # Restic restaura (como root) en una carpeta privada que crea root. Nada de root toca la carpeta del usuario:
    # el paso final lo hace el propio usuario, así un enlace simbólico en «Recuperado» o por encima no puede
    # llevar escrituras ni cambios de propietario a rutas del sistema.
    preparacion = tempfile.mkdtemp(prefix="leksso-recuperar-")
    try:
        restic("restore", copia, "--target", preparacion, "--include", literal_para_restic(ruta))
        # Mientras root recorre el árbol, la carpeta de preparación sigue siendo suya (0700): el usuario no puede
        # tocarla. Primero se cambia el propietario de todo lo de dentro y, al final, el de la carpeta raíz.
        for d, ds, fs in os.walk(preparacion):
            for n in ds + fs:
                try:
                    os.chown(os.path.join(d, n), u.pw_uid, u.pw_gid, follow_symlinks=False)
                except OSError:
                    pass
        os.chown(preparacion, u.pw_uid, u.pw_gid, follow_symlinks=False)
        destino = _copiar_como_usuario(u, preparacion, base, nombre)
    finally:
        shutil.rmtree(preparacion, ignore_errors=True)
    print(json.dumps({"ok": True, "destino": destino + ruta}))


def estado():
    cfg, e = configuracion(), leer_json(ESTADO, {})
    proxima = ""
    if cfg["activa"] and not SIN_SYSTEMD:
        try:
            proxima = subprocess.run(["systemctl", "show", "leksso-copias.timer", "-p", "NextElapseUSecRealtime", "--value"],
                                     capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    snaps = e.get("snapshots", [])
    print(json.dumps({
        **cfg, "proxima": proxima, "ultima": e.get("ultima"), "ultima_ok": e.get("ultima_ok"),
        "copias": snaps, "maximo": MAX_COPIAS, "volver_hasta": snaps[-1]["fecha"] if snaps else None,
        "espacio_repo": e.get("espacio_repo", 0), "mismo_disco": mismo_disco(),
        "atrasada": bool(cfg["activa"] and e.get("ultima_ok") and vieja(e["ultima_ok"], cfg["frecuencia"])),
    }, ensure_ascii=False))


def barra():
    cfg, e = configuracion(), leer_json(ESTADO, {})
    u = e.get("ultima") or {}
    problema = ""
    if cfg["activa"] and u.get("resultado") == "fallo":
        problema = "La última copia de seguridad falló: " + u.get("mensaje", "")
    elif cfg["activa"] and e.get("ultima_ok") and vieja(e["ultima_ok"], cfg["frecuencia"]):
        problema = "Hace tiempo que no se hace una copia de seguridad."
    print(json.dumps({"text": "▲ Copias" if problema else "", "tooltip": problema, "class": "fallo" if problema else ""}, ensure_ascii=False))


def main(a):
    p = argparse.ArgumentParser(prog="leksso-copias", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="orden", required=True)
    for n in ("estado", "barra", "activar", "configurar", "desactivar"):
        s.add_parser(n)
    x = s.add_parser("ejecutar"); x.add_argument("--ahora", action="store_true")
    x = s.add_parser("listar"); x.add_argument("copia", nargs="?"); x.add_argument("ruta", nargs="?")
    x = s.add_parser("restaurar"); x.add_argument("copia"); x.add_argument("ruta")
    o = p.parse_args(a)
    try:
        if o.orden == "estado": estado()
        elif o.orden == "barra": barra()
        elif o.orden == "activar": activar()
        elif o.orden == "configurar": activar(solo_horario=True)
        elif o.orden == "desactivar": desactivar()
        elif o.orden == "ejecutar": return ejecutar(o.ahora)
        elif o.orden == "listar": listar(o.copia, o.ruta)
        elif o.orden == "restaurar": restaurar(o.copia, o.ruta)
    except Error as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
