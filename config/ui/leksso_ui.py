"""Piezas comunes de las ventanas propias de LeksSO (menú de aplicaciones, energía...)."""
import json
import os
import re

# ---- tema de color ----------------------------------------------------------------------------
# Los colores de abajo son los del tema BASE (Marea). Si el usuario eligió otro (leksso-tema), cada color
# se cambia por el del mismo papel en el tema activo, al abrir la ventana.
BASE = "marea"
_AQUI = os.path.dirname(os.path.abspath(__file__))
_CARPETAS = ("/usr/local/share/leksso/temas", os.path.join(_AQUI, "..", "tema"))
_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{6,8}(?![0-9A-Za-z])")


def tema_activo():
    try:
        nombre = open(os.path.expanduser("~/.config/leksso/tema"), encoding="utf-8").read().strip()
    except OSError:
        return BASE
    return nombre if nombre.isalnum() else BASE


def tokens(nombre):
    """Colores de un tema por papel ({'bg': '021012', ...}) o {} si no existe."""
    for carpeta in _CARPETAS:
        try:
            datos = json.load(open(os.path.join(carpeta, nombre + ".json"), encoding="utf-8"))
            return {k: v.lstrip("#").lower() for k, v in datos["colores"].items()}
        except (OSError, ValueError, KeyError):
            continue
    return {}


def es_claro(nombre):
    """True si el tema es claro (campo «modo» de su archivo de colores)."""
    for carpeta in _CARPETAS:
        try:
            return json.load(open(os.path.join(carpeta, nombre + ".json"), encoding="utf-8")).get("modo") == "claro"
        except (OSError, ValueError):
            continue
    return False


def mapa_de_colores(desde, hasta):
    a, b = tokens(desde), tokens(hasta)
    return {a[k]: b[k] for k in a if k in b}


def recolorear(texto, mapa):
    """Cambia cada color de `texto` según `mapa` (hex sin # → hex sin #). Vale con o sin almohadilla y en
    formato de 8 cifras: ARGB de Qt (ffRRGGBB) o RGBA con el alfa al final (RRGGBBaa)."""
    def cambia(m):
        s, minus = m.group(0), m.group(0).lower()
        if len(s) == 6:
            return mapa.get(minus, s)
        if len(s) == 8:
            if minus[:2] == "ff" and minus[2:] in mapa:
                return "ff" + mapa[minus[2:]]
            if minus[:6] in mapa:
                return mapa[minus[:6]] + minus[6:]
        return s
    return _HEX.sub(cambia, texto)


def pintar(texto):
    """Pasa una hoja de estilo escrita con los colores base a los del tema activo."""
    activo = tema_activo()
    if activo == BASE:
        return texto
    return recolorear(texto, mapa_de_colores(BASE, activo))


ESTILO = """
QWidget { background: #021012; color: #e3edef; font-size: 14px; font-family: "Raxtor", "DejaVu Sans"; }   /* Raxtor solo dibuja cifras */
QLabel#titulo { font-size: 16px; font-weight: bold; color: #00c4bf; }
QLabel#nota { color: #94a1a3; font-size: 12px; }
QLineEdit { background: #112123; border: 1px solid #25393c; padding: 8px 10px; color: #e3edef; }
QLineEdit:focus { border: 1px solid #00c4bf; }
QPushButton#cerrar { background: transparent; color: #94a1a3; border: none; font-size: 20px; padding: 2px 12px; }
QPushButton#cerrar:hover { background: #3f1a13; color: #ff735a; }
QPushButton#accion { background: #112123; border: 1px solid #25393c; padding: 12px 14px; text-align: left; }
QPushButton#accion:hover { background: #003635; border: 1px solid #00c4bf; }
QPushButton#accion:disabled { color: #667576; background: #051416; }
QPushButton#peligro { background: #112123; border: 1px solid #25393c; padding: 12px 14px; text-align: left; }
QPushButton#peligro:hover { background: #3f1a13; border: 1px solid #ff735a; }
QListWidget { background: #021012; border: none; outline: none; }
QListWidget::item { padding: 8px 10px; border: none; }
QListWidget::item:hover { background: #112123; }
QListWidget::item:selected { background: #003635; color: #e3edef; }
QMessageBox { background: #021012; }
"""
ESTILO_BASE = ESTILO  # sin recolorear: para volver a pintar una ventana abierta al cambiar de tema
ESTILO = pintar(ESTILO)


_VIVOS = []      # (ventana, hoja de estilo base) de las ventanas que siguen el tema
_VIGILANTE = []  # el observador de ~/.config/leksso, creado la primera vez


def estilo(widget, base):
    """Pone a `widget` la hoja de estilo `base` (escrita con los colores base) con los colores del tema activo y la
    repinta sola cuando se cambia de tema (leksso-tema), sin cerrar ni abrir la ventana."""
    import weakref
    widget.setStyleSheet(pintar(base))
    _VIVOS.append((weakref.ref(widget), base))
    if not _VIGILANTE:
        from PySide6 import QtCore
        ruta = os.path.expanduser("~/.config/leksso/tema")
        carpeta = os.path.dirname(ruta)
        os.makedirs(carpeta, exist_ok=True)
        # se vigilan la carpeta (el archivo se reemplaza) y el archivo (por si se escribe en el sitio)
        v = QtCore.QFileSystemWatcher([carpeta] + ([ruta] if os.path.exists(ruta) else []))
        ultimo = [tema_activo()]

        def cambio(_):
            if os.path.exists(ruta) and ruta not in v.files():
                v.addPath(ruta)  # tras reemplazarlo, el archivo es otro: hay que volver a vigilarlo
            if tema_activo() == ultimo[0]:
                return
            ultimo[0] = tema_activo()
            for ref, b in list(_VIVOS):
                w = ref()
                if w is None:
                    _VIVOS.remove((ref, b))
                else:
                    w.setStyleSheet(pintar(b))
        v.directoryChanged.connect(cambio)
        v.fileChanged.connect(cambio)
        _VIGILANTE.append(v)


def alternar(nombre):
    """Si ya hay una ventana abierta de este programa, la cierra (el botón actúa de interruptor)
    y devuelve True. Si no, se registra y devuelve False."""
    ruta = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), f"{nombre}.pid")
    try:
        pid = int(open(ruta).read())
        os.kill(pid, 0)
        if nombre in open(f"/proc/{pid}/cmdline").read():
            os.kill(pid, 15)
            return True
    except (OSError, ValueError):
        pass
    with open(ruta, "w") as f:
        f.write(str(os.getpid()))
    return False


# ---- permiso de administrador para las ventanas ------------------------------------------------------------------
# Una ventana gráfica no tiene terminal: `sudo -n` solo funciona si sudo no pide contraseña. Hay tres casos y se detecta
# cuál es el de este equipo: sudo sin contraseña (-n), sudo que no la pide por PAM (-S la deja pasar sin leer nada) o
# sudo con contraseña (se pide en un diálogo y se recuerda solo en memoria mientras la ventana siga abierta).
_SUDO = {"modo": None, "clave": None}


def _sudo_correr(cmd, entrada=None, espera=60):
    import subprocess
    try:
        r = subprocess.run(cmd, input=entrada, capture_output=True, text=True, timeout=espera)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)


def sudo_modo():
    """'n' (sin contraseña), 'S' (PAM no la pide) o 'clave' (hay que pedirla)."""
    if _SUDO["modo"]:
        return _SUDO["modo"]
    if _sudo_correr(["sudo", "-n", "true"], espera=15)[0] == 0:
        _SUDO["modo"] = "n"
    elif _sudo_correr(["sudo", "-S", "-p", "", "true"], entrada="", espera=15)[0] == 0:
        _SUDO["modo"] = "S"
    else:
        _SUDO["modo"] = "clave"
    return _SUDO["modo"]


def olvidar_clave():
    _SUDO["clave"] = None


def pedir_permiso(padre, motivo):
    """Deja listo el permiso de administrador (hilo principal). True si ya se puede usar sudo_cmd."""
    if sudo_modo() != "clave" or _SUDO["clave"]:
        return True
    from PySide6 import QtWidgets
    for intento in range(3):
        texto, ok = QtWidgets.QInputDialog.getText(
            padre, "Permiso de administrador", motivo + "\n\nEscribe tu contraseña (solo se recuerda mientras esta ventana siga abierta):",
            QtWidgets.QLineEdit.Password)
        if not ok:
            return False
        if _sudo_correr(["sudo", "-S", "-p", "", "-v"], entrada=texto + "\n", espera=30)[0] == 0:
            _SUDO["clave"] = texto
            return True
    return False


def sudo_cmd(args, entrada=None, espera=3600):
    """Ejecuta `sudo ARGS` según el modo detectado. Devuelve (código, salida, error). Seguro para hilos; la contraseña, si
    hace falta, hay que pedirla antes con pedir_permiso()."""
    modo = sudo_modo()
    if modo == "n":
        return _sudo_correr(["sudo", "-n", *args], entrada, espera)
    if modo == "S":
        return _sudo_correr(["sudo", "-S", "-p", "", *args], entrada, espera)
    if not _SUDO["clave"]:
        return 1, "", "sudo: a password is required"
    rc, out, err = _sudo_correr(["sudo", "-S", "-p", "", *args], _SUDO["clave"] + "\n" + (entrada or ""), espera)
    if rc != 0 and "try again" in err.lower():     # la contraseña ya no vale
        _SUDO["clave"] = None
    return rc, out, err
