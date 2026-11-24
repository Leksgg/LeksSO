"""Núcleo del permisor de IA de LeksSO. Solo biblioteca estándar, solo Linux.

La IA nunca toca el disco: pide acciones y este módulo las ejecuta dentro del
alcance concedido. Cada ruta se recorre con openat y O_NOFOLLOW desde un
descriptor de la carpeta concedida, así que un enlace simbólico no puede sacar
la acción del alcance ni siquiera si cambia entre la comprobación y el uso.
"""
import ctypes
import errno
import functools
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import threading
import time
import unicodedata
import uuid
from pathlib import Path

try:                                   # el diario del sistema: solo en Linux
    import syslog
except ImportError:                    # pragma: no cover
    syslog = None

GENESIS = "0" * 64                     # la «cabeza» de un registro vacío
SELLO_CADA = 5                         # segundos como mucho entre un sello y el siguiente (las órdenes sellan siempre)

MAX_LEER = 2 * 1024 * 1024
PROHIBIDAS = {"/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot",
              "/sys", "/proc", "/dev", "/var", "/root", "/run"}
FLAGS_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def renombrar_sin_pisar(origen, destino, src_fd, dst_fd):
    """rename que falla con FileExistsError si el destino existe, en un solo paso del núcleo (renameat2 con
    RENAME_NOREPLACE): sin el hueco entre «mirar si existe» y «renombrar» por el que se colaría otro archivo."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        r = libc.renameat2(src_fd, os.fsencode(origen), dst_fd, os.fsencode(destino), 1)
    except (OSError, AttributeError):
        r, err = -1, errno.ENOSYS
    else:
        err = ctypes.get_errno()
    if r == 0:
        return
    if err == errno.EEXIST:
        raise FileExistsError(err, os.strerror(err), destino)
    if err in (errno.ENOSYS, errno.EINVAL):           # sistema de archivos sin soporte: se vuelve a lo de siempre
        try:
            os.stat(destino, dir_fd=dst_fd, follow_symlinks=False)
        except FileNotFoundError:
            os.rename(origen, destino, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
            return
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), destino)
    raise OSError(err, os.strerror(err), destino)


def _identidad(st):
    """Con qué se reconoce «lo mismo» al deshacer: [dispositivo, inodo] y, si no es una carpeta, también tamaño y fecha de
    modificación. El inodo solo no basta: ext4 reutiliza el número en cuanto queda libre, así que un archivo nuevo puede
    heredar el de uno borrado. Renombrar no cambia ni el tamaño ni la fecha, por eso estos datos sobreviven a mover y a
    la papelera. En las carpetas solo se usa el inodo: su fecha cambia cada vez que se toca algo dentro."""
    base = [st.st_dev, st.st_ino]
    if stat.S_ISDIR(st.st_mode):
        return base
    return base + [st.st_size, st.st_mtime_ns]


def _es_el_mismo(actual, guardado):
    """Compara lo que hay ahora con lo anotado. Las acciones anotadas por versiones antiguas solo llevan
    [dispositivo, inodo]: con esas se compara solo eso."""
    guardado, actual = list(guardado), list(actual)
    if len(guardado) == 2:          # carpeta, o anotada por una versión antigua: solo dispositivo e inodo
        return actual[:2] == guardado
    return actual == guardado


def _objeto(fd, nombre):
    """Identidad de lo que hay con ese nombre, sin seguir enlaces."""
    return _identidad(os.stat(nombre, dir_fd=fd, follow_symlinks=False))


class Denegado(Exception):
    """La acción queda fuera del alcance o no es segura."""


def _sha(fd):
    h = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        bloque = os.read(fd, 1 << 20)
        if not bloque:
            return h.hexdigest()
        h.update(bloque)

def _limpio(x):
    """Un nombre de archivo o de carpeta suelto: nunca vacío, '.', '..' ni con barras."""
    return isinstance(x, str) and x not in ("", ".", "..") and "/" not in x and "\x00" not in x


# Caracteres invisibles: sirven para esconder instrucciones dentro de un archivo que la IA lee.
_OCULTOS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
_SOSPECHAS = [
    (re.compile(r"(?i)\b(ignore|disregard|forget|olvida|ignora)\b.{0,60}\b(previous|prior|above|instructions|anteriores|instrucciones)"),
     "dice a la IA que ignore sus instrucciones"),
    (re.compile(r"(?i)(system prompt|developer message|<\|im_start\|>|\[INST\]|mensaje del sistema)"),
     "imita mensajes del sistema"),
    (re.compile(r"(?i)(curl|wget)[^\n|]{0,200}\|\s*(ba|z)?sh"), "descarga y ejecuta un script"),
    (re.compile(r"(?i)(rm\s+-rf|chmod\s+\+x|authorized_keys|id_rsa|\.ssh/|\.bashrc)"),
     "menciona comandos o archivos sensibles"),
    (re.compile(r"[A-Za-z0-9+/]{400,}={0,2}"), "contiene un bloque largo en base64"),
]
MAX_LISTA = 5000


def limpiar_contenido(texto):
    """Devuelve (texto sin caracteres invisibles, avisos). El contenido de un archivo son DATOS,
    nunca instrucciones: esto no lo garantiza, pero lo marca para que se vea."""
    avisos = []
    limpio, n = _OCULTOS.subn("", texto)
    if n:
        avisos.append(f"tenía {n} caracteres invisibles (se han quitado)")
    for patron, msg in _SOSPECHAS:
        if patron.search(limpio):
            avisos.append(msg)
    return limpio, avisos


def imprimible(s):
    """Sin códigos de control, invisibles ni de dirección: nada que falsee la pantalla de aprobación."""
    return isinstance(s, str) and all(unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn") for c in s)


def _serializado(f):
    """Las operaciones que cambian archivos van de una en una: así la cadena de versiones
    y el orden del registro coinciden siempre con lo que pasó en el disco."""
    @functools.wraps(f)
    def envuelta(self, *a, **k):
        with self._cerrojo:
            return f(self, *a, **k)
    return envuelta

class Nucleo:
    def __init__(self, casa):
        self.casa = Path(os.path.realpath(casa))
        self.datos = self.casa / ".leksso"
        self.versiones = self.datos / "versiones"
        self.registro = self.datos / "registro.jsonl"
        self.papelera = self.casa / ".local" / "share" / "Trash"
        for d in (self.versiones, self.papelera / "files", self.papelera / "info"):
            d.mkdir(parents=True, exist_ok=True)
        os.chmod(self.datos, 0o700)
        self.tareas = {}
        self.acciones = {}
        self.invalidas = 0                 # líneas del registro con firma falsa o ausente
        self.cortes = 0                    # veces que la cadena no enlaza: líneas borradas, cambiadas de sitio o metidas a mano
        self._cabeza = GENESIS             # firma de la última línea válida: la siguiente línea la cita
        self._validas = 0
        self._ultimo_sello = 0.0
        self._cerrojo = threading.RLock()
        self._clave = self._leer_clave()
        self._cargar()

    def _leer_clave(self):
        """Clave que firma cada línea del registro: quien edite el registro a mano no puede
        hacer que 'deshacer' toque rutas elegidas por él."""
        ruta = self.datos / "clave"
        if not ruta.exists():
            fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(os.urandom(32))
        return ruta.read_bytes()

    def _firma(self, r):
        cuerpo = {k: v for k, v in r.items() if k not in ("firma", "deshecha")}
        return hmac.new(self._clave, json.dumps(cuerpo, sort_keys=True, ensure_ascii=False).encode(),
                        "sha256").hexdigest()

    # ---------- registro ----------
    # Cada línea lleva la firma de la anterior («prev») dentro de lo que firma: quitar una línea, cambiarlas de sitio o
    # meter una a mano rompe el enlace con la siguiente y queda contado en «cortes», para siempre. La cadena sola NO
    # frena a quien lea la clave (es del mismo usuario): por eso la cabeza se sella además en el diario del sistema
    # (_sellar), que el usuario no puede reescribir, y `verificar` compara las dos cosas.
    def _revisar(self, r, est):
        """Comprueba una línea ya leída contra el estado de la cadena. True si la firma vale (la línea cuenta)."""
        if not isinstance(r, dict) or not hmac.compare_digest(str(r.get("firma", "")), self._firma(r)):
            est["invalidas"] += 1
            return False
        if "prev" in r:
            est["encadenado"] = True
            if r["prev"] != est["esperado"]:
                est["cortes"] += 1
        elif est["encadenado"]:                # una línea sin «prev» DESPUÉS de empezar la cadena no puede ser de este programa
            est["cortes"] += 1
        est["esperado"] = r["firma"]
        est["validas"] += 1
        est["firmas"].add(r["firma"])
        return True

    def _estado_cadena(self):
        return {"esperado": GENESIS, "encadenado": False, "cortes": 0, "invalidas": 0, "validas": 0, "firmas": set()}

    def verificar(self, sello_externo=None):
        """Recorre el registro entero. sello_externo: la última cabeza que quedó en el diario del sistema (si se pudo leer):
        si no aparece entre las líneas del registro, faltan líneas (por ejemplo, las últimas)."""
        est = self._estado_cadena()
        if self.registro.exists():
            for linea in self.registro.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(linea)
                except ValueError:
                    continue
                self._revisar(r, est)
        sello = None
        if sello_externo:
            sello = sello_externo in est["firmas"] or sello_externo == GENESIS
        ok = est["cortes"] == 0 and est["invalidas"] == 0 and sello is not False
        return {"ok": ok, "lineas": est["validas"], "cortes": est["cortes"], "invalidas": est["invalidas"],
                "cabeza": est["esperado"], "sello_del_sistema": sello}

    def _sellar(self, r):
        """Deja la cabeza de la cadena en el diario del sistema (si el servicio lo pide con LEKSSO_SELLO=syslog). Es lo que
        el usuario no puede reescribir. Como mucho cada SELLO_CADA segundos, y siempre que se ejecuta una orden."""
        if syslog is None or os.environ.get("LEKSSO_SELLO") != "syslog":
            return
        ahora = time.monotonic()
        if r.get("accion") not in ("orden", "orden_admin") and ahora - self._ultimo_sello < SELLO_CADA:
            return
        self._ultimo_sello = ahora
        try:
            syslog.openlog("leksso-permisor", 0, syslog.LOG_AUTH)
            syslog.syslog(syslog.LOG_INFO, f"sello n={self._validas} cabeza={self._cabeza}")
        except OSError:
            pass

    def _cargar(self):
        if not self.registro.exists():
            return
        with open(self.registro, "rb+") as f:      # tras un corte, la última línea puede estar a medias
            f.seek(0, os.SEEK_END)
            if f.tell():
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
        est = self._estado_cadena()
        for linea in self.registro.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(linea)
            except ValueError:
                continue
            if not self._revisar(r, est):
                continue
            if "deshace" in r:
                if r["deshace"] in self.acciones:
                    self.acciones[r["deshace"]]["deshecha"] = True
            elif "id" in r and r.get("ok"):
                r["deshecha"] = False
                self.acciones[r["id"]] = r
        self.cortes, self.invalidas = est["cortes"], est["invalidas"]
        self._cabeza, self._validas = est["esperado"], est["validas"]

    def _anotar(self, r):
        with self._cerrojo:
            r["t"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            r["prev"] = self._cabeza               # el enlace con la línea anterior va dentro de lo que se firma
            r["firma"] = self._firma(r)
            with open(self.registro, "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._cabeza = r["firma"]
            self._validas += 1
            if r.get("ok") and "id" in r:
                r["deshecha"] = False
                self.acciones[r["id"]] = r
            self._sellar(r)

    def anotar_consulta(self, accion, detalle="", **extra):
        """Deja constancia de una consulta de solo lectura que no toca archivos (por ejemplo, medir el equipo).
        extra: datos firmados que acompañan a la línea (por ejemplo, la huella completa de una orden)."""
        self._anotar({"tarea": None, "accion": accion, "ruta": detalle, "ok": True, **extra})

    def _nuevo_id(self):
        return "a" + uuid.uuid4().hex[:8]

    def _denegar(self, tarea, accion, ruta, motivo):
        self._anotar({"tarea": tarea.id if tarea else None, "accion": accion,
                      "ruta": ruta, "ok": False, "motivo": motivo})
        raise Denegado(motivo)

    # ---------- tareas ----------
    def comprobar_carpetas(self, carpetas):
        """Valida y normaliza {ruta: permisos}. Las rutas salen ya resueltas (sin enlaces), para que
        quien aprueba vea la carpeta real y no un nombre que apunta a otro sitio."""
        raices = {}
        for ruta, perms in carpetas.items():
            real = os.path.realpath(ruta)
            nueva = False
            if not os.path.lexists(real) and os.path.isabs(ruta):
                # Carpeta que aún no existe: se crea al aprobar, un solo nivel y dentro de una carpeta que sí existe.
                nombre = os.path.basename(os.path.normpath(ruta))
                padre = os.path.realpath(os.path.dirname(os.path.normpath(ruta)))
                if (not _limpio(nombre) or nombre.startswith(".") or "/" in nombre or ".." in Path(ruta).parts
                        or len(nombre) > 200 or not os.path.isdir(padre) or padre in PROHIBIDAS):
                    raise Denegado(f"no se puede crear esa carpeta nueva: {ruta}")
                if "w" not in set(perms):
                    raise Denegado("para crear una carpeta nueva hace falta permiso de escritura")
                real = os.path.join(padre, nombre)
                nueva = True
            if real in PROHIBIDAS or real == str(self.casa):
                raise Denegado(f"carpeta demasiado amplia: {ruta}")
            if self.datos == Path(real) or str(self.datos).startswith(real + "/") \
                    or real.startswith(str(self.datos) + "/"):
                raise Denegado("la carpeta incluye datos internos de LeksSO")
            if not nueva and not os.path.isdir(real):
                raise Denegado(f"no es una carpeta: {ruta}")
            if not set(perms) <= set("rwd") or not perms:
                raise Denegado(f"permisos no válidos: {perms}")
            if nueva:
                raices[real] = {"perms": set(perms), "id": None, "nueva": True}
                continue
            st = os.stat(real)
            previo = raices.get(real, {"perms": set()})["perms"]
            raices[real] = {"perms": previo | set(perms), "id": (st.st_dev, st.st_ino)}
        return raices

    def _crear_nuevas(self, raices, tid):
        """Crea las carpetas nuevas aprobadas (un nivel, sin seguir enlaces) y anota cada creación para poder deshacerla."""
        for real, info in raices.items():
            if not info.get("nueva"):
                continue
            padre, nombre = os.path.split(real)
            fd = os.open(padre, FLAGS_DIR)
            try:
                try:
                    os.mkdir(nombre, 0o755, dir_fd=fd)
                    creada = True
                except FileExistsError:
                    creada = False
                d = os.open(nombre, FLAGS_DIR, dir_fd=fd)       # si ahora es un enlace o un archivo, falla aquí
                try:
                    st = os.fstat(d)
                finally:
                    os.close(d)
            except OSError as e:
                raise Denegado(f"no se pudo crear la carpeta {real}: {e.strerror}")
            finally:
                os.close(fd)
            info["id"] = (st.st_dev, st.st_ino)
            info.pop("nueva", None)
            if creada:
                self._anotar({"id": self._nuevo_id(), "tarea": tid, "accion": "crear_carpeta", "ok": True,
                              "ruta": real, "raiz": padre, "padre": [], "nombre": nombre})

    def conceder(self, titulo, carpetas, destino="local", ttl=3600, canal=None, ids=None):
        """carpetas: {ruta: 'rwd'}. Devuelve el id de la tarea. «ids» son las identidades (dispositivo, inodo) que
        tenían las carpetas cuando se pidió el permiso: si alguna carpeta es otra al aprobar, no se concede."""
        raices = self.comprobar_carpetas(carpetas)
        for ruta, visto in (ids or {}).items():
            ahora = raices.get(ruta, {}).get("id")
            if visto is not None and ahora is not None and list(ahora) != list(visto):
                raise Denegado(f"la carpeta {ruta} ya no es la misma que cuando se pidió el permiso: pídelo otra vez")
        tid = "t" + uuid.uuid4().hex[:16]
        self._crear_nuevas(raices, tid)
        t = type("Tarea", (), {})()
        t.id, t.titulo, t.destino, t.canal = tid, titulo, destino, canal
        t.raices, t.expira, t.cerrada = raices, time.time() + ttl, False
        self.tareas[tid] = t
        self._anotar({"tarea": tid, "accion": "conceder", "ok": True, "id": self._nuevo_id(),
                      "titulo": titulo, "destino": destino,
                      "carpetas": {k: "".join(sorted(v["perms"])) for k, v in raices.items()}})
        return tid

    def limpiar_tareas(self):
        """Quita las tareas cerradas o caducadas, para que la memoria no crezca sin límite."""
        ahora = time.time()
        for tid in [k for k, t in self.tareas.items() if t.cerrada or ahora > t.expira]:
            del self.tareas[tid]

    def cerrar(self, tid):
        if tid in self.tareas:
            self.tareas[tid].cerrada = True

    def _tarea(self, tid):
        t = self.tareas.get(tid)
        if not t:
            raise Denegado("tarea desconocida")
        if t.cerrada or time.time() > t.expira:
            raise Denegado("tarea cerrada o caducada")
        return t

    # ---------- rutas ----------
    def _abrir_dir(self, raiz, partes, crear=False, id_raiz=None):
        fd = os.open(raiz, FLAGS_DIR)
        try:
            st = os.fstat(fd)
            if id_raiz and (st.st_dev, st.st_ino) != id_raiz:
                raise Denegado("la carpeta concedida cambió")
            for p in partes:
                try:
                    nuevo = os.open(p, FLAGS_DIR, dir_fd=fd)
                except FileNotFoundError:
                    if not crear:
                        raise
                    os.mkdir(p, 0o755, dir_fd=fd)
                    nuevo = os.open(p, FLAGS_DIR, dir_fd=fd)
                except OSError as e:
                    if e.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise Denegado(f"enlace o no-carpeta en la ruta: {p}")
                    raise
                os.close(fd)
                fd = nuevo
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _resolver(self, t, accion, ruta, perm, crear=False):
        """Devuelve (fd_carpeta_padre, nombre, raiz, partes_padre)."""
        if not os.path.isabs(ruta) or ".." in Path(ruta).parts:
            self._denegar(t, accion, ruta, "ruta no absoluta o con ..")
        p = os.path.normpath(ruta)
        for raiz, info in t.raices.items():
            if p == raiz or p.startswith(raiz + "/"):
                break
        else:
            self._denegar(t, accion, ruta, "fuera del alcance")
        if perm not in info["perms"]:
            self._denegar(t, accion, ruta, f"sin permiso '{perm}' en {raiz}")
        partes = [x for x in p[len(raiz):].split("/") if x]
        if any(x.startswith(".") for x in partes):
            self._denegar(t, accion, ruta, "archivos ocultos denegados por defecto")
        if not partes:
            return None, None, raiz, []
        try:
            fd = self._abrir_dir(raiz, partes[:-1], crear, info["id"])
        except Denegado as e:
            self._denegar(t, accion, ruta, str(e))
        return fd, partes[-1], raiz, partes[:-1]

    # ---------- acciones ----------
    def listar(self, tid, ruta):
        t = self._tarea(tid)
        fd, nombre, raiz, _ = self._resolver(t, "listar", ruta, "r")
        try:
            dirfd = os.open(nombre, FLAGS_DIR, dir_fd=fd) if nombre else \
                self._abrir_dir(raiz, [], False, t.raices[raiz]["id"])
        except OSError:
            self._denegar(t, "listar", ruta, "no es una carpeta accesible")
        finally:
            if fd is not None:
                os.close(fd)
        try:
            salida = []
            for n in sorted(os.listdir(dirfd))[:MAX_LISTA]:
                if n.startswith("."):
                    continue
                st = os.stat(n, dir_fd=dirfd, follow_symlinks=False)
                tipo = "enlace" if os.path.islink(f"/proc/self/fd/{dirfd}/{n}") else \
                    ("carpeta" if os.path.isdir(f"/proc/self/fd/{dirfd}/{n}") else "archivo")
                salida.append({"nombre": n, "tipo": tipo, "bytes": st.st_size})
        finally:
            os.close(dirfd)
        self._anotar({"tarea": tid, "accion": "listar", "ruta": ruta, "ok": True})
        return salida

    def leer_con_avisos(self, tid, ruta):
        t = self._tarea(tid)
        fd, nombre, _, _ = self._resolver(t, "leer", ruta, "r")
        if nombre is None:
            self._denegar(t, "leer", ruta, "es una carpeta")
        try:
            f = os.open(nombre, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except OSError:
            self._denegar(t, "leer", ruta, "no se puede abrir (¿enlace?)")
        finally:
            os.close(fd)
        try:
            st = os.fstat(f)
            if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_LEER:
                self._denegar(t, "leer", ruta, "no es archivo normal o supera 2 MB")
            datos = os.read(f, MAX_LEER + 1)
        finally:
            os.close(f)
        texto, avisos = limpiar_contenido(datos.decode("utf-8", errors="replace"))
        self._anotar({"tarea": tid, "accion": "leer", "ruta": ruta, "ok": True,
                      "destino": t.destino, "bytes": len(datos), "avisos": avisos})
        return texto, avisos

    def leer(self, tid, ruta):
        return self.leer_con_avisos(tid, ruta)[0]

    @_serializado
    def escribir(self, tid, ruta, texto):
        t = self._tarea(tid)
        fd, nombre, raiz, padre = self._resolver(t, "escribir", ruta, "w", crear=True)
        if nombre is None:
            self._denegar(t, "escribir", ruta, "es una carpeta")
        aid = self._nuevo_id()
        previo = None
        try:
            try:
                st = os.stat(nombre, dir_fd=fd, follow_symlinks=False)
                existia = True
            except FileNotFoundError:
                existia, st = False, None
            if existia and not stat.S_ISREG(st.st_mode):
                self._denegar(t, "escribir", ruta, "el destino no es un archivo normal")
            if existia:
                f = os.open(nombre, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    carpeta = self.versiones / t.id
                    carpeta.mkdir(parents=True, exist_ok=True)
                    previo = str(carpeta / f"{aid}-{nombre}")
                    os.lseek(f, 0, os.SEEK_SET)
                    with open(previo, "wb") as out, os.fdopen(os.dup(f), "rb") as src:
                        shutil.copyfileobj(src, out)
                finally:
                    os.close(f)
            tmp = f".leksso-tmp-{uuid.uuid4().hex[:8]}"
            modo = (st.st_mode & 0o777) if existia else 0o644
            w = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, modo, dir_fd=fd)
            try:
                os.write(w, texto.encode("utf-8"))
                os.fsync(w)
            finally:
                os.close(w)
            os.rename(tmp, nombre, src_dir_fd=fd, dst_dir_fd=fd)
            r = os.open(nombre, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                sha = _sha(r)
            finally:
                os.close(r)
        finally:
            os.close(fd)
        self._anotar({"id": aid, "tarea": tid, "accion": "escribir", "ruta": ruta, "ok": True,
                      "raiz": raiz, "padre": padre, "nombre": nombre, "existia": existia,
                      "previo": previo, "sha": sha, "destino": t.destino})
        return aid

    def _a_papelera(self, fd, nombre, ruta_original):
        base = nombre
        destino = self.papelera / "files" / base
        n = 1
        while destino.exists() or os.path.lexists(destino):
            n += 1
            destino = self.papelera / "files" / f"{base}.{n}"
        origen = f"/proc/self/fd/{fd}/{nombre}"
        try:
            os.rename(nombre, destino, src_dir_fd=fd)
        except OSError as e:
            if e.errno != errno.EXDEV:
                raise
            shutil.move(origen, str(destino))
        info = self.papelera / "info" / (destino.name + ".trashinfo")
        info.write_text("[Trash Info]\nPath=" + ruta_original + "\nDeletionDate=" +
                        time.strftime("%Y-%m-%dT%H:%M:%S") + "\n", encoding="utf-8")
        return destino.name

    @_serializado
    def borrar(self, tid, ruta):
        """Borrar = mover a la papelera estándar. No existe el borrado definitivo."""
        t = self._tarea(tid)
        fd, nombre, raiz, padre = self._resolver(t, "borrar", ruta, "d")
        if nombre is None:
            self._denegar(t, "borrar", ruta, "no se borra la carpeta concedida")
        aid = self._nuevo_id()
        try:
            os.stat(nombre, dir_fd=fd, follow_symlinks=False)
            en_papelera = self._a_papelera(fd, nombre, ruta)
            objeto = _identidad(os.lstat(self.papelera / "files" / en_papelera))
        except FileNotFoundError:
            self._denegar(t, "borrar", ruta, "no existe")
        finally:
            os.close(fd)
        self._anotar({"id": aid, "tarea": tid, "accion": "borrar", "ruta": ruta, "ok": True,
                      "raiz": raiz, "padre": padre, "nombre": nombre, "papelera": en_papelera, "obj": objeto})
        return aid

    @_serializado
    def mover(self, tid, origen, destino):
        t = self._tarea(tid)
        # Sacar un archivo de su carpeta es quitarlo de allí: hace falta poder borrar en el origen.
        # Renombrar dentro de la misma carpeta solo pide escribir.
        misma = os.path.dirname(os.path.normpath(origen)) == os.path.dirname(os.path.normpath(destino))
        fo, no, ro, po = self._resolver(t, "mover", origen, "w" if misma else "d")
        try:
            fd, nd, rd, pd = self._resolver(t, "mover", destino, "w", crear=True)
        except BaseException:
            os.close(fo)
            raise
        if no is None or nd is None:
            self._denegar(t, "mover", origen, "no se mueve una carpeta concedida")
        aid = self._nuevo_id()
        try:
            try:
                renombrar_sin_pisar(no, nd, fo, fd)
                objeto = _objeto(fd, nd)
            except FileExistsError:
                self._denegar(t, "mover", destino, "el destino ya existe")
            except OSError as e:
                self._denegar(t, "mover", origen, f"no se pudo mover ({e.strerror})")
        finally:
            os.close(fo)
            os.close(fd)
        self._anotar({"id": aid, "tarea": tid, "accion": "mover", "ruta": origen, "ok": True,
                      "destino_ruta": destino, "raiz": ro, "padre": po, "nombre": no,
                      "raiz2": rd, "padre2": pd, "nombre2": nd, "obj": objeto})
        return aid

    # ---------- deshacer ----------
    def _fd_de(self, raiz, padre):
        t = None
        for tarea in self.tareas.values():
            if raiz in tarea.raices:
                t = tarea
        idr = t.raices[raiz]["id"] if t else None
        return self._abrir_dir(raiz, padre, crear=True, id_raiz=idr)

    def _validar_para_deshacer(self, a):
        """Aunque el registro esté firmado, se revisa cada dato antes de usarlo como ruta."""
        ok = (isinstance(a.get("raiz"), str) and os.path.isabs(a["raiz"])
              and isinstance(a.get("padre"), list) and all(_limpio(p) for p in a["padre"])
              and _limpio(a.get("nombre")))
        if a["accion"] == "mover":
            ok = ok and (isinstance(a.get("raiz2"), str) and os.path.isabs(a["raiz2"])
                         and isinstance(a.get("padre2"), list) and all(_limpio(p) for p in a["padre2"])
                         and _limpio(a.get("nombre2")))
        if a["accion"] == "borrar":
            ok = ok and _limpio(a.get("papelera"))
        if a["accion"] == "escribir" and a.get("previo"):
            ok = ok and os.path.realpath(a["previo"]).startswith(str(self.versiones) + os.sep)
        if not ok:
            raise Denegado("el registro de esta acción no es válido; no se deshace")

    @_serializado
    def deshacer(self, aid, forzar=False):
        with self._cerrojo:
            a = self.acciones.get(aid)
            if not a or a.get("deshecha"):
                raise Denegado("acción desconocida o ya deshecha")
            tipo = a["accion"]
            self._validar_para_deshacer(a)
            if tipo == "escribir":
                fd = self._fd_de(a["raiz"], a["padre"])
                try:
                    if os.path.lexists(f"/proc/self/fd/{fd}/{a['nombre']}"):
                        f = os.open(a["nombre"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                        try:
                            cambio = _sha(f) != a["sha"]
                        finally:
                            os.close(f)
                        if cambio and not forzar:
                            raise Denegado("el archivo cambió después; usa forzar para sobrescribir")
                    if a["existia"]:
                        if not a.get("previo") or not os.path.exists(a["previo"]):
                            raise Denegado("la versión previa ya se purgó; no se puede deshacer")
                        tmp = f".leksso-tmp-{uuid.uuid4().hex[:8]}"
                        shutil.copyfile(a["previo"], f"/proc/self/fd/{fd}/{tmp}")
                        os.rename(tmp, a["nombre"], src_dir_fd=fd, dst_dir_fd=fd)
                    elif os.path.lexists(f"/proc/self/fd/{fd}/{a['nombre']}"):
                        self._a_papelera(fd, a["nombre"], a["ruta"])
                finally:
                    os.close(fd)
            elif tipo == "borrar":
                fd = self._fd_de(a["raiz"], a["padre"])
                try:
                    if os.path.lexists(f"/proc/self/fd/{fd}/{a['nombre']}"):
                        raise Denegado("ya existe un archivo con ese nombre")
                    origen = self.papelera / "files" / a["papelera"]
                    if not os.path.lexists(origen):
                        raise Denegado("ya no está en la papelera")
                    if a.get("obj") and not _es_el_mismo(_identidad(os.lstat(origen)), a["obj"]):
                        raise Denegado("lo que hay ahora en la papelera con ese nombre no es lo que se borró; no se restaura")
                    try:
                        os.rename(origen, a["nombre"], dst_dir_fd=fd)
                    except OSError as e:
                        if e.errno != errno.EXDEV:
                            raise
                        shutil.move(str(origen), f"/proc/self/fd/{fd}/{a['nombre']}")
                    info = self.papelera / "info" / (a["papelera"] + ".trashinfo")
                    if info.exists():
                        info.unlink()
                finally:
                    os.close(fd)
            elif tipo == "crear_carpeta":
                fd = self._fd_de(a["raiz"], a["padre"])
                try:
                    try:
                        os.rmdir(a["nombre"], dir_fd=fd)
                    except FileNotFoundError:
                        raise Denegado("la carpeta ya no existe")
                    except OSError as e:
                        if e.errno in (errno.ENOTEMPTY, errno.EEXIST):
                            raise Denegado("la carpeta ya no está vacía; no se deshace")
                        raise
                finally:
                    os.close(fd)
            elif tipo == "mover":
                f1 = self._fd_de(a["raiz2"], a["padre2"])
                f2 = self._fd_de(a["raiz"], a["padre"])
                try:
                    try:
                        if a.get("obj") and not _es_el_mismo(_objeto(f1, a["nombre2"]), a["obj"]):
                            raise Denegado("lo que hay ahora en el destino no es lo que se movió; no se deshace")
                        renombrar_sin_pisar(a["nombre2"], a["nombre"], f1, f2)
                    except FileExistsError:
                        raise Denegado("el origen original ya está ocupado")
                    except FileNotFoundError:
                        raise Denegado("lo movido ya no está donde se dejó")
                finally:
                    os.close(f1)
                    os.close(f2)
            else:
                raise Denegado("esa acción no se deshace")
            a["deshecha"] = True
            self._anotar({"deshace": aid})

    @_serializado
    def deshacer_tarea(self, tid, forzar=False):
        hechas = [a for a in self.acciones.values()
                  if a.get("tarea") == tid and not a.get("deshecha")
                  and a["accion"] in ("escribir", "borrar", "mover", "crear_carpeta")]
        for a in reversed(hechas):
            self.deshacer(a["id"], forzar)
        return len(hechas)

    @_serializado
    def purgar_versiones(self, max_dias=30, max_bytes=2 * 1024 ** 3):
        """Borra versiones previas viejas y, si aún se pasa del límite, las más antiguas.
        Deshacer una acción cuya versión se purgó avisa con un mensaje claro."""
        ficheros = sorted((p for p in self.versiones.rglob("*") if p.is_file()),
                          key=lambda p: p.stat().st_mtime)
        limite = time.time() - max_dias * 86400
        total = sum(p.stat().st_size for p in ficheros)
        borrados = 0
        for p in ficheros:
            if p.stat().st_mtime < limite or total > max_bytes:
                total -= p.stat().st_size
                p.unlink()
                borrados += 1
        for d in self.versiones.iterdir():
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        return borrados
    def ultimas(self, n=20):
        if not self.registro.exists():
            return []
        with open(self.registro, "rb") as f:      # solo el final: el registro puede ser enorme
            f.seek(0, os.SEEK_END)
            fin, datos = f.tell(), b""
            while fin > 0 and datos.count(b"\n") <= n:
                ini = max(0, fin - 65536)
                f.seek(ini)
                datos = f.read(fin - ini) + datos
                fin = ini
        lineas = datos.decode("utf-8", errors="replace").split("\n")[-(n + 1):]    # solo \n: splitlines() también corta en U+2028…
        salida = []
        for x in lineas:
            if x.strip():
                try:
                    salida.append(json.loads(x))
                except ValueError:
                    continue            # una línea cortada o dañada no impide leer el resto
        return salida[-n:]
