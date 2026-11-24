#!/usr/bin/env python3
"""Solicitud de conexión: pedir acceso por SSH a un equipo con LeksSO de la red local, y aprobarlo en su pantalla.

  En el equipo que quiere entrar (LeksSO, Windows, cualquiera con Python y ssh):
    leksso-solicitud pedir DIRECCIÓN [--clave ~/.ssh/id_ed25519.pub] [--nombre NOMBRE]
        envía la solicitud, enseña el código de cuatro palabras y espera a que la aprueben.

  En el equipo que recibe (lo lanza el sistema; no hace falta teclear nada):
    leksso-solicitud recibir     atiende UNA conexión (lo arranca systemd por cada solicitud que llega)
    leksso-solicitud vigilar     espera solicitudes y abre la ventana (lo arranca el escritorio al iniciar sesión)
    leksso-solicitud ventana     enseña la solicitud pendiente: Permitir o No permitir

Reglas:
  - Solo existe mientras el acceso remoto está encendido en modo «solo red local» (Ajustes, Acceso remoto). Apagado o en
    modo público, no se escucha nada.
  - Solo desde la red local, y solo si hay alguien con la sesión abierta para contestar.
  - El código de cuatro palabras (unos 352 millones de combinaciones) sale en los dos equipos y debe ser el mismo. Se calcula con la clave del que
    pide, la identidad del equipo que recibe y DOS números aleatorios: uno de cada equipo. Para que un intermediario en la
    red no pueda buscar un número que haga coincidir los dos códigos, el que pide se COMPROMETE con el suyo antes de ver
    nada del otro (manda su huella) y lo REVELA después, cuando ya tiene el del equipo que recibe:
        1. pide:  LEKSSO-SOLICITUD 2 nombre clave HUELLA      (HUELLA = sha256 de su número, que aún no enseña)
        2. recibe: PENDIENTE 2 su-número usuario identidad    (el número del equipo que recibe, elegido ya con la huella delante)
        3. pide:  LEKSSO-REVELAR 2 su-número                  (el que recibe comprueba que cuadra con la huella)
    Quien se interpone tiene que fijar su número antes de saber el del otro lado: acierta una vez de cada 352 millones
    (con dos palabras y sin compromiso, una de cada 18 769 y buscándolo a fuerza bruta). El código solo se enseña al
    permitir cuando el número ya se ha revelado; una solicitud sin revelar se descarta a los 30 segundos.
    Una versión anterior (la 1) no es compatible: el equipo que pide y el que recibe tienen que actualizarse.
  - Al permitir, la clave se guarda para entrar SOLO desde la red local (from="..." en authorized_keys).
  - Como mucho 3 solicitudes pendientes y 1 por equipo; caducan a los 5 minutos; tras 2 «No permitir» al mismo equipo,
    se le ignora 10 minutos.
"""
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time

PUERTO = 22222
VERSION = "2"
MAX_LINEA = 2048
CADUCA = 300              # segundos que vive una solicitud
ESPERA_REVELAR = 30       # segundos que se espera a que quien pide revele su número; si no, se descarta
N_PALABRAS = 4            # palabras del código: len(PALABRAS) ** 4 combinaciones (unos 352 millones, 28 bits y medio)
MAX_PENDIENTES = 3
RECHAZOS_PARA_SILENCIO = 2
SILENCIO = 600            # segundos que se ignora a un equipo tras rechazarlo dos veces
TIPOS = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
         "sk-ssh-ed25519@openssh.com")
REDES_LOCALES = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
HOSTKEY = "/etc/ssh/ssh_host_ed25519_key.pub"

# Palabras cortas, sin tildes ni eñes, fáciles de leer y de comparar (137 hoy). Cuatro palabras = el código.
PALABRAS = """agua aire alba arco arena atun avion barco bici bolsa bosque brazo brisa burro cable cafe caja calle cama
campo canto carta casa cebra cesta cielo cine clavo coche cola copa corona cubo cuerda dado dedo delfin disco dulce
duna faro feria flor foca fresa fuego gafas gallo gato globo goma gorra grano grillo hada hielo hilo hoja horno hueso
isla jarra jaula jirafa koala lago lapiz lata leon libro lima lince llave lobo luna luz mango mano mapa mar mesa metro
miel mono moto mundo nave nido nieve noche nube nuez oca ola olivo oso pala palma pan pato pera perro pez piano piedra
pino playa pluma puente queso radio rama rana rayo reloj rio roca rosa rueda sal sapo seta silla sol sopa tambor taza
tigre toro torre tren trigo uva vaca vela viento zorro""".split()


# ---------- lógica común (sin red ni ventana, para poder probarla) ----------
def partir_clave(texto):
    """'tipo base64 [comentario]' -> (tipo, base64) o None si no tiene pinta de clave pública SSH."""
    p = (texto or "").strip().split()
    if len(p) < 2 or p[0] not in TIPOS or not re.fullmatch(r"[A-Za-z0-9+/]{40,1400}={0,2}", p[1]):
        return None
    try:
        base64.b64decode(p[1], validate=True)
    except ValueError:
        return None
    return p[0], p[1]


def nombre_limpio(nombre):
    """El nombre del equipo que pide: solo letras, cifras, punto, guion y guion bajo; 40 como mucho."""
    n = re.sub(r"[^A-Za-z0-9._-]", "", nombre or "")[:40]
    return n or "equipo-sin-nombre"


def compromiso(secreto):
    """La huella con la que quien pide se compromete con su número antes de ver el del otro equipo."""
    return hashlib.sha256(secreto.encode("ascii")).hexdigest()


def codigo(clave, hostkey, nonce, secreto):
    """El código de cuatro palabras. clave y hostkey son (tipo, base64); nonce lo elige quien recibe y secreto quien pide."""
    h = hashlib.sha256(f"{clave[0]} {clave[1]}\n{hostkey[0]} {hostkey[1]}\n{nonce}\n{secreto}".encode()).digest()
    # Cada palabra sale de 4 bytes del resumen: con un solo byte y una lista que no mide 256 / n, las primeras palabras
    # saldrían más a menudo que las últimas. Con 4 bytes el sesgo es de una parte entre 30 millones.
    return "-".join(PALABRAS[int.from_bytes(h[4 * i:4 * i + 4], "big") % len(PALABRAS)] for i in range(N_PALABRAS))


def es_local(ip):
    """¿La dirección es de una red privada (o este mismo equipo)?"""
    try:
        d = ipaddress.ip_address((ip or "").split("%")[0])
    except ValueError:
        return False
    if d.version == 6 and d.ipv4_mapped:
        d = d.ipv4_mapped
    if d.is_loopback:
        return True
    return d.version == 4 and any(d in ipaddress.ip_network(r) for r in REDES_LOCALES.split(","))


def linea_solicitud(nombre, clave, huella):
    return f"LEKSSO-SOLICITUD {VERSION} {nombre_limpio(nombre)} {clave[0]} {clave[1]} {huella}\n"


def leer_solicitud(linea):
    """La línea que manda quien pide -> (nombre, (tipo, base64), huella) o None."""
    p = (linea or "").strip().split(" ")
    if len(p) != 6 or p[0] != "LEKSSO-SOLICITUD" or p[1] != VERSION or not re.fullmatch(r"[0-9a-f]{64}", p[5]):
        return None
    clave = partir_clave(p[3] + " " + p[4])
    if clave is None or p[2] != nombre_limpio(p[2]):
        return None
    return p[2], clave, p[5]


def linea_revelacion(secreto):
    return f"LEKSSO-REVELAR {VERSION} {secreto}\n"


def leer_revelacion(linea):
    """La línea con la que quien pide revela su número -> el número, o None."""
    p = (linea or "").strip().split(" ")
    if len(p) == 3 and p[0] == "LEKSSO-REVELAR" and p[1] == VERSION and re.fullmatch(r"[0-9a-f]{32}", p[2]):
        return p[2]
    return None


def leer_respuesta(linea):
    """La respuesta del equipo -> ('PENDIENTE', nonce, usuario, (tipo, b64)) o ('RECHAZADA', motivo) o None."""
    p = (linea or "").strip().split(" ")
    if p[:1] == ["RECHAZADA"]:
        return "RECHAZADA", " ".join(p[1:]) or "sin motivo"
    if len(p) == 6 and p[0] == "PENDIENTE" and p[1] == VERSION and re.fullmatch(r"[0-9a-f]{16}", p[2]) \
            and re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", p[3]):
        hk = partir_clave(p[4] + " " + p[5])
        if hk:
            return "PENDIENTE", p[2], p[3], hk
    return None


def linea_autorizada(sol, ahora=None):
    """La línea que se añade a authorized_keys al permitir: solo vale desde la red local."""
    fecha = time.strftime("%Y-%m-%d", time.localtime(ahora or time.time()))
    return f'from="{REDES_LOCALES}" {sol["clave"][0]} {sol["clave"][1]} solicitud:{nombre_limpio(sol["nombre"])}:{fecha}'


def pendientes(carpeta, ahora=None, solo_listas=True):
    """Las solicitudes vivas de la cola, la más antigua primero. Borra de paso las caducadas y las ilegibles.
    solo_listas: solo las que ya tienen código (el número de quien pide ya se reveló); las demás se están esperando y
    se descartan a los ESPERA_REVELAR segundos."""
    ahora = ahora or time.time()
    res = []
    try:
        nombres = sorted(n for n in os.listdir(carpeta) if n.endswith(".json") and not n.startswith("."))
    except OSError:
        return res
    for n in nombres:
        ruta = os.path.join(carpeta, n)
        try:
            with open(ruta, encoding="utf-8") as f:
                s = json.load(f)
            s["clave"] = tuple(s["clave"])
            if ahora - float(s["hora"]) > CADUCA or partir_clave(" ".join(s["clave"])) is None:
                raise ValueError
            if "codigo" not in s and ahora - float(s["hora"]) > ESPERA_REVELAR:
                raise ValueError              # nunca reveló su número
            s["ruta"] = ruta
            if "codigo" in s or not solo_listas:
                res.append(s)
        except (OSError, ValueError, KeyError, TypeError):
            try:
                os.unlink(ruta)
            except OSError:
                pass
    return sorted(res, key=lambda s: s["hora"])


def _rechazos(carpeta):
    try:
        with open(os.path.join(carpeta, ".rechazos"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def silenciado(carpeta, ip, ahora=None):
    ahora = ahora or time.time()
    veces = [t for t in _rechazos(carpeta).get(ip, []) if ahora - t < SILENCIO]
    return len(veces) >= RECHAZOS_PARA_SILENCIO


def anotar_rechazo(carpeta, ip, ahora=None):
    ahora = ahora or time.time()
    d = {k: [t for t in v if ahora - t < SILENCIO] for k, v in _rechazos(carpeta).items()}
    d = {k: v for k, v in d.items() if v}
    d.setdefault(ip, []).append(ahora)
    _escribir(os.path.join(carpeta, ".rechazos"), json.dumps(d))


def _escribir(ruta, texto):
    with open(ruta + ".nuevo", "w", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)) as f:
        f.write(texto)
    os.replace(ruta + ".nuevo", ruta)


def motivo_rechazo(carpeta, ip, ahora=None):
    """¿Por qué no se admite ahora una solicitud de esa dirección? '' si se admite."""
    if not es_local(ip):
        return "solo se admite desde la red local"
    if not os.path.isdir(carpeta):
        return "no hay nadie con la sesion abierta en ese equipo"
    if silenciado(carpeta, ip, ahora):
        return "ese equipo ha dicho que no; espera diez minutos"
    vivas = pendientes(carpeta, ahora, solo_listas=False)        # también las que esperan la revelación
    if any(s["ip"] == ip for s in vivas):
        return "ya hay una solicitud tuya esperando respuesta"
    if len(vivas) >= MAX_PENDIENTES:
        return "hay demasiadas solicitudes esperando"
    return ""


def revelar(carpeta, ip, secreto, hostkey, ahora=None):
    """Quien pidió revela su número: se comprueba contra la huella que mandó y, si cuadra, queda calculado el código.
    Devuelve '' si todo bien o el motivo del rechazo. La solicitud se busca por la huella (no se puede fabricar un número
    que cuadre con una huella ajena) y tiene que venir de la misma dirección."""
    ahora = ahora or time.time()
    huella = compromiso(secreto)
    for s in pendientes(carpeta, ahora, solo_listas=False):
        if s.get("compromiso") != huella:
            continue
        if s["ip"] != ip:
            return "esa solicitud no es de esta direccion"
        if "codigo" in s:
            return "esa solicitud ya estaba revelada"
        nuevo = {k: v for k, v in s.items() if k != "ruta"}
        nuevo["codigo"] = codigo(tuple(s["clave"]), hostkey, s["nonce"], secreto)
        nuevo["hora"] = ahora                  # los cinco minutos para decidir empiezan al enseñarse el código
        _escribir(s["ruta"], json.dumps(nuevo))
        return ""
    return "no hay una solicitud con ese compromiso (¿pasaron mas de 30 segundos?)"


def carpeta_cola():
    uid = os.getuid() if hasattr(os, "getuid") else 0          # Windows solo pide, nunca recibe
    return os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}", "leksso-solicitudes")


def modo_local():
    """¿Está el acceso remoto encendido en modo «solo red local»?"""
    try:
        r = subprocess.run(["leksso-acceso-remoto", "estado"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.stdout.strip() == "local"


def clave_valida_de_verdad(clave):
    """Además de la forma, que ssh-keygen la acepte."""
    try:
        r = subprocess.run(["ssh-keygen", "-l", "-f", "/dev/stdin"], input=f"{clave[0]} {clave[1]}\n",
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def autorizar(sol, casa=None):
    """Añade la clave a authorized_keys del usuario (si no estaba ya). Devuelve True si quedó autorizada."""
    casa = casa or os.path.expanduser("~")
    d = os.path.join(casa, ".ssh")
    os.makedirs(d, mode=0o700, exist_ok=True)
    ruta = os.path.join(d, "authorized_keys")
    try:
        with open(ruta, encoding="utf-8") as f:
            actual = f.read()
    except OSError:
        actual = ""
    if any(sol["clave"][1] in linea.split() for linea in actual.splitlines()):
        return True
    if actual and not actual.endswith("\n"):
        actual += "\n"
    _escribir(ruta, actual + linea_autorizada(sol) + "\n")
    return True


# ---------- el equipo que recibe ----------
def recibir():
    """Atiende una conexión (systemd la pasa por la entrada y la salida). Contesta una línea y termina."""
    def decir(texto):
        sys.stdout.write(texto + "\n")
        sys.stdout.flush()
        return 0

    ip = os.environ.get("REMOTE_ADDR", "")
    cola = carpeta_cola()
    try:
        import signal
        signal.alarm(10)                    # quien no manda su línea en 10 s, fuera
    except (ImportError, AttributeError, ValueError):
        pass
    dato = sys.stdin.buffer.readline(MAX_LINEA + 1)
    if len(dato) > MAX_LINEA or not dato.endswith(b"\n"):
        return decir("RECHAZADA solicitud mal formada")
    texto = dato.decode("ascii", "replace")
    if texto.startswith("LEKSSO-SOLICITUD 1 "):
        return decir("RECHAZADA el otro equipo usa una version antigua de LeksSO: actualizalo")
    revelado = leer_revelacion(texto)
    sol = None if revelado else leer_solicitud(texto)
    if revelado is None and sol is None:
        return decir("RECHAZADA solicitud mal formada")
    if not modo_local():
        return decir("RECHAZADA el acceso remoto no esta encendido en modo local")
    if not es_local(ip):
        return decir("RECHAZADA solo se admite desde la red local")
    try:
        with open(HOSTKEY, encoding="ascii") as f:
            hk = partir_clave(f.read())
    except OSError:
        hk = None
    if hk is None:
        return decir("RECHAZADA este equipo no tiene identidad SSH")
    if revelado:                                  # segundo paso: quien pidió revela su número
        motivo = revelar(cola, ip, revelado, hk)
        return decir("OK" if not motivo else "RECHAZADA " + motivo)
    motivo = motivo_rechazo(cola, ip)
    if motivo:
        return decir("RECHAZADA " + motivo)
    nombre, clave, huella = sol
    if not clave_valida_de_verdad(clave):
        return decir("RECHAZADA la clave no es valida")
    nonce = secrets.token_hex(8)
    ahora = time.time()
    ident = f"{int(ahora * 1000)}-{secrets.token_hex(4)}"
    # Sin «codigo» todavía: no se enseña hasta que quien pide revele su número (revelar).
    _escribir(os.path.join(cola, ident + ".json"), json.dumps({
        "nombre": nombre, "ip": ip, "clave": list(clave), "nonce": nonce, "compromiso": huella, "hora": ahora}))
    import getpass
    return decir(f"PENDIENTE {VERSION} {nonce} {getpass.getuser()} {hk[0]} {hk[1]}")


def vigilar():
    """Espera solicitudes y abre la ventana. Lo arranca el escritorio; crea la cola (solo existe con la sesión abierta)."""
    cola = carpeta_cola()
    os.makedirs(cola, mode=0o700, exist_ok=True)
    yo = os.path.abspath(sys.argv[0])
    while True:
        if pendientes(cola):
            subprocess.run([sys.executable, yo, "ventana"])
        time.sleep(2)


def ventana(captura=None, ejemplo=None):
    for ruta in ("/usr/local/lib/leksso-ui", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "ui")):
        if ruta not in sys.path:
            sys.path.insert(0, ruta)
    from PySide6 import QtCore, QtWidgets
    from leksso_ui import ESTILO_BASE, estilo, pintar

    cola = carpeta_cola()
    vivas = [ejemplo] if ejemplo else pendientes(cola)
    if not vivas:
        return 0
    sol = vivas[0]

    class Solicitud(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Solicitud de conexión")
            estilo(self, ESTILO_BASE)
            raiz = QtWidgets.QVBoxLayout(self)
            raiz.setContentsMargins(18, 12, 18, 16)
            raiz.setSpacing(10)
            cab = QtWidgets.QHBoxLayout()
            t = QtWidgets.QLabel("Alguien quiere entrar en este equipo")
            t.setObjectName("titulo")
            cab.addWidget(t)
            cab.addStretch()
            x = QtWidgets.QPushButton("✕")
            x.setObjectName("cerrar")
            x.setToolTip("Cerrar sin permitir (Esc)")
            x.setAutoDefault(False)
            x.clicked.connect(lambda: self.terminar(False, contar=False))
            cab.addWidget(x)
            raiz.addLayout(cab)
            raiz.addWidget(QtWidgets.QLabel(f"Equipo:  {sol['nombre']}  ({sol['ip']})"))
            cod = QtWidgets.QLabel(f"Código:  {sol['codigo']}")
            cod.setWordWrap(True)                  # cuatro palabras no caben en una línea con letra grande
            cod.setStyleSheet(pintar("QLabel { font-size: 22px; font-weight: bold; color: #00c4bf; padding: 6px 0; }"))
            raiz.addWidget(cod)
            for texto in ("Las cuatro palabras tienen que ser las mismas en el otro equipo, en el mismo orden.",
                          "Si lo permites, podrá ver y manejar este equipo desde tu red.",
                          "Si no lo esperabas, pulsa «No permitir»."):
                e = QtWidgets.QLabel(texto)
                e.setWordWrap(True)
                raiz.addWidget(e)
            raiz.addStretch()
            fila = QtWidgets.QHBoxLayout()
            self.no = QtWidgets.QPushButton("No permitir")
            self.no.setObjectName("accion")
            self.no.setDefault(True)
            self.no.clicked.connect(lambda: self.terminar(False))
            fila.addWidget(self.no)
            si = QtWidgets.QPushButton("Permitir")
            si.setObjectName("accion")
            si.setAutoDefault(False)            # Intro nunca permite: hay que pulsarlo con el ratón
            si.setFocusPolicy(QtCore.Qt.NoFocus)
            si.clicked.connect(lambda: self.terminar(True))
            fila.addWidget(si)
            raiz.addLayout(fila)
            self.no.setFocus()
            self.reloj = QtCore.QTimer(self)
            self.reloj.timeout.connect(self.caducidad)
            self.reloj.start(2000)

        def caducidad(self):
            if ejemplo is None and (time.time() - sol["hora"] > CADUCA or not os.path.exists(sol["ruta"])):
                self.close()

        def terminar(self, permitir, contar=True):
            if ejemplo is None:
                if permitir and os.path.exists(sol["ruta"]) and modo_local():
                    autorizar(sol)
                elif not permitir and contar:
                    anotar_rechazo(cola, sol["ip"])
                try:
                    os.unlink(sol["ruta"])
                except OSError:
                    pass
            self.close()

        def keyPressEvent(self, ev):
            if ev.key() == QtCore.Qt.Key_Escape:
                self.terminar(False, contar=False)
            elif ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self.terminar(False)
            else:
                super().keyPressEvent(ev)

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setDesktopFileName("leksso-solicitud")
    w = Solicitud()
    w.resize(480, 330)
    w.show()
    if captura:
        app.processEvents()
        w.grab().save(captura)
        return 0
    return app.exec()


# ---------- el equipo que pide ----------
def clave_propia(ruta=None):
    """La clave pública de este equipo: la indicada, o la primera habitual de ~/.ssh. La crea si no hay ninguna."""
    casa = os.path.expanduser("~")
    candidatas = [ruta] if ruta else [os.path.join(casa, ".ssh", n) for n in ("id_ed25519.pub", "id_ecdsa.pub", "id_rsa.pub")]
    for c in candidatas:
        if c and os.path.isfile(c):
            with open(c, encoding="utf-8") as f:
                k = partir_clave(f.read())
            if k:
                return c, k
    if ruta:
        raise RuntimeError(f"No puedo leer una clave pública en {ruta}")
    privada = os.path.join(casa, ".ssh", "id_ed25519")
    os.makedirs(os.path.dirname(privada), mode=0o700, exist_ok=True)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", privada], check=True)
    return clave_propia(privada + ".pub")


def _hablar(direccion, puerto, linea):
    """Manda una línea al otro equipo y devuelve la que contesta (texto). Lanza OSError si no se puede."""
    with socket.create_connection((direccion, puerto), timeout=8) as s:
        s.sendall(linea.encode("ascii"))
        s.settimeout(20)
        dato = b""
        while not dato.endswith(b"\n") and len(dato) < MAX_LINEA:
            trozo = s.recv(1024)
            if not trozo:
                break
            dato += trozo
    return dato.decode("ascii", "replace")


def _decir(texto):
    print(texto, flush=True)          # con la salida redirigida a un archivo, sin esto no se vería nada hasta el final


def pedir(direccion, ruta_clave=None, nombre=None, espera=CADUCA, puerto=PUERTO, salida=_decir):
    ruta, clave = clave_propia(ruta_clave)
    nombre = nombre_limpio(nombre or socket.gethostname())
    secreto = secrets.token_hex(16)               # mi número: no lo enseño hasta ver el del otro equipo
    try:
        respuesta = _hablar(direccion, puerto, linea_solicitud(nombre, clave, compromiso(secreto)))
    except OSError:
        salida(f"{direccion} no acepta solicitudes. En ese equipo: Ajustes, Acceso remoto, «Solo red local».")
        return 1
    r = leer_respuesta(respuesta)
    if r is None:
        salida("Ese equipo ha contestado algo que no entiendo (¿otra versión de LeksSO?).")
        return 1
    if r[0] == "RECHAZADA":
        salida("Solicitud no admitida: " + r[1])
        return 1
    _, nonce, usuario, hk = r
    try:
        confirmacion = _hablar(direccion, puerto, linea_revelacion(secreto)).strip()      # ya tengo su número: revelo el mío
    except OSError:
        salida("No se pudo completar la solicitud (el otro equipo dejó de contestar). Vuelve a pedirlo.")
        return 1
    if confirmacion != "OK":
        salida("No se pudo completar la solicitud: " + (leer_respuesta(confirmacion) or ("", "respuesta rara"))[1])
        return 1
    salida(f"Solicitud enviada a {usuario}@{direccion}.")
    salida(f"CÓDIGO: {codigo(clave, hk, nonce, secreto)}")
    salida("Mira la pantalla de ese equipo: si salen las MISMAS cuatro palabras, en el mismo orden, pulsa «Permitir». "
           "Si es distinto, «No permitir».")
    privada = ruta[:-4] if ruta.endswith(".pub") else ruta
    with tempfile.TemporaryDirectory() as tmp:
        conocidos = os.path.join(tmp, "known_hosts")
        with open(conocidos, "w", encoding="ascii") as f:
            f.write(f"{direccion} {hk[0]} {hk[1]}\n")
        orden = ["ssh", "-i", privada, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
                 "-o", f"UserKnownHostsFile={conocidos}", "-o", "StrictHostKeyChecking=yes",
                 "-o", f"HostKeyAlgorithms={hk[0]}", f"{usuario}@{direccion}", "true"]
        fin = time.time() + espera
        while time.time() < fin:
            if subprocess.run(orden, capture_output=True, stdin=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(4)
        else:
            salida("Nadie lo ha permitido a tiempo (o han dicho que no). Puedes volver a pedirlo.")
            return 1
    # la identidad del equipo, ya comprobada con el código, pasa a la lista de equipos conocidos
    subprocess.run(["ssh-keygen", "-R", direccion], capture_output=True)
    lista = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")
    with open(lista, "a", encoding="ascii") as f:
        f.write(f"{direccion} {hk[0]} {hk[1]}\n")
    salida(f"Permitido. Ya puedes entrar:  ssh -i {privada} {usuario}@{direccion}")
    return 0


def main(a):
    if a[:1] == ["recibir"]:
        return recibir()
    if a[:1] == ["vigilar"]:
        return vigilar()
    if a[:1] == ["ventana"]:
        if a[1:2] == ["--captura"] and len(a) == 3:
            ej = {"nombre": "PORTATIL-DE-CASA", "ip": "192.168.1.20", "codigo": "pera-luna-faro-mar", "hora": time.time(), "ruta": ""}
            return ventana(a[2], ej)
        return ventana()
    if a[:1] == ["pedir"] and len(a) >= 2:
        resto, ruta, nombre = a[2:], None, None
        while resto:
            if resto[0] == "--clave" and len(resto) > 1:
                ruta, resto = resto[1], resto[2:]
            elif resto[0] == "--nombre" and len(resto) > 1:
                nombre, resto = resto[1], resto[2:]
            else:
                print(__doc__)
                return 2
        try:
            return pedir(a[1], ruta, nombre)
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
