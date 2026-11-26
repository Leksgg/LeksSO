"""Piezas comunes de las ventanas propias de LeksSO (menú de aplicaciones, energía...)."""
import json
import os
import re

# ---- tema de color ----------------------------------------------------------------------------
# Los colores de abajo son los del tema BASE (Grafito, el de serie). Si el usuario eligió otro (leksso-tema), cada color
# se cambia por el del mismo papel en el tema activo, al abrir la ventana.
BASE = "grafito"
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
    """Colores de un tema por papel ({'bg': '15171a', ...}) o {} si no existe."""
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
QWidget { background: #15171a; color: #eaebed; font-size: 14px; font-family: "Montserrat", "DejaVu Sans"; }   /* Qt no respeta la restricción de Raxtor a cifras: el cuerpo no la usa */
QLabel#titulo { font-family: "Raxtor Titulos", "Montserrat", "DejaVu Sans"; font-size: 17px; font-weight: bold; color: #79b1e0; }   /* títulos en MAYÚSCULAS */
QLabel#nota { color: #9d9ea1; font-size: 12px; }
QLineEdit { background: #27292c; border: 1px solid #3e4145; padding: 8px 10px; color: #eaebed; }
QLineEdit:focus { border: 1px solid #79b1e0; }
QPushButton#cerrar { background: transparent; color: #9d9ea1; border: none; font-size: 20px; padding: 2px 12px; }
QPushButton#cerrar:hover { background: #3f1a13; color: #ff735a; }
QPushButton#accion { background: #27292c; border: 1px solid #3e4145; padding: 12px 14px; text-align: left; }
QPushButton#accion:hover { background: #143c5b; border: 1px solid #79b1e0; }
QPushButton#accion:disabled { color: #808285; background: #1a1c1f; }
QPushButton#activo { background: #143c5b; border: 1px solid #79b1e0; padding: 12px 14px; text-align: left; }
QPushButton:focus { border: 1px solid #79b1e0; }
QPushButton#cerrar:focus { border: 1px solid #79b1e0; }
QPushButton:disabled { color: #808285; border: 1px dashed #3e4145; }
QPushButton#principal { background: #79b1e0; color: #15171a; border: 1px solid #79b1e0; padding: 10px 18px; font-weight: bold; }
QPushButton#principal:hover { background: #143c5b; color: #eaebed; }
QPushButton#principal:focus { border: 2px solid #eaebed; }
QPushButton#principal:disabled { background: #1a1c1f; color: #808285; border: 1px dashed #3e4145; }
QPushButton#peligro { background: #27292c; border: 1px solid #3e4145; padding: 12px 14px; text-align: left; }
QPushButton#peligro:hover { background: #3f1a13; border: 1px solid #ff735a; }
QListWidget { background: #15171a; border: none; outline: none; }
QListWidget::item { padding: 8px 10px; border: none; }
QListWidget::item:hover { background: #27292c; }
QListWidget::item:selected { background: #143c5b; color: #eaebed; }
QMessageBox { background: #15171a; }
"""
ESTILO_BASE = ESTILO  # sin recolorear: para volver a pintar una ventana abierta al cambiar de tema
ESTILO = pintar(ESTILO)


_VIVOS = []      # (ventana, hoja de estilo base) de las ventanas que siguen el tema
_VIGILANTE = []  # el observador de ~/.config/leksso, creado la primera vez


class _TitulosEnMayusculas:
    """Filtro de eventos: cada QLabel con nombre «titulo» se muestra en MAYÚSCULAS (Raxtor Titulos solo trae capitales)."""
    _filtro = None

    @classmethod
    def instalar(cls):
        if cls._filtro is not None:
            return
        from PySide6 import QtCore, QtWidgets

        class Filtro(QtCore.QObject):
            def eventFilter(self, obj, ev):
                if ev.type() in (QtCore.QEvent.Show, QtCore.QEvent.Polish) and isinstance(obj, QtWidgets.QLabel)                         and obj.objectName() == "titulo" and obj.text() != obj.text().upper():
                    obj.setText(obj.text().upper())
                return False
        app = QtWidgets.QApplication.instance()
        if app is not None:
            cls._filtro = Filtro(app)
            app.installEventFilter(cls._filtro)


def titulos_en_mayusculas():
    _TitulosEnMayusculas.instalar()


def estilo(widget, base):
    """Pone a `widget` la hoja de estilo `base` (escrita con los colores base) con los colores del tema activo y la
    repinta sola cuando se cambia de tema (leksso-tema), sin cerrar ni abrir la ventana."""
    import weakref
    widget.setStyleSheet(pintar(base))
    titulos_en_mayusculas()
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


def confirmar(padre, titulo, texto, si, no="Cancelar", peligro=False):
    """Pregunta de confirmación cuyo botón dice lo que va a pasar («Borrar el historial», no «Sí»). Devuelve True si se
    acepta. Por defecto y con Esc se cancela. `peligro` pinta el botón como acción destructiva."""
    from PySide6 import QtWidgets
    m = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question, titulo, texto, QtWidgets.QMessageBox.NoButton, padre)
    b_si = m.addButton(si, QtWidgets.QMessageBox.AcceptRole)
    b_si.setObjectName("peligro" if peligro else "principal")
    b_no = m.addButton(no, QtWidgets.QMessageBox.RejectRole)
    m.setDefaultButton(b_no)
    m.setEscapeButton(b_no)
    m.exec()
    return m.clickedButton() is b_si


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
        # Sin entrada que pasar, el programa recibe una entrada vacía en vez de heredar la de quien lanzó la ventana: heredada y
        # abierta, cualquier orden que la lea se quedaba esperando hasta agotar el tiempo (visto como fallo intermitente de test_sudo).
        entrada_ = {"input": entrada} if entrada is not None else {"stdin": subprocess.DEVNULL}
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=espera, **entrada_)
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
