#!/usr/bin/env python3
"""Ver la pantalla de otro equipo con LeksSO, para ayudar a distancia. Siempre con permiso, cada vez.

  En el equipo que ayuda (LeksSO, o Windows con Python, ssh y un visor VNC como TigerVNC):
    leksso-pantalla pedir USUARIO@DIRECCIÓN [--clave ~/.ssh/mi_clave]
        pide permiso, y si lo dan abre la pantalla del otro equipo en una ventana.

  En el equipo que recibe la ayuda (lo lanza el sistema):
    leksso-pantalla solicitar NOMBRE   lo ejecuta «pedir» por SSH: deja la petición y espera la respuesta
    leksso-pantalla vigilar            en la sesión: abre la ventana de permiso, vigila el tiempo y el bloqueo
    leksso-pantalla cortar             deja de compartir ahora mismo (botón PARAR, aviso de la barra, Súper+Esc)
    leksso-pantalla barra              el aviso de la barra (rojo mientras se comparte)

Cómo funciona y qué garantiza:
  - Usa wayvnc, que escucha SOLO en un archivo de tu sesión (/run/user/…): no abre ningún puerto. Quien ayuda llega por
    dentro del SSH que ya tiene autorizado.
  - En tu pantalla sale «X quiere ver tu pantalla». «No, ahora no» es el botón por defecto. Puedes dejar solo mirar, o
    mirar y manejar.
  - Mientras dura hay un aviso rojo en la barra y un botón PARAR siempre encima. El aviso sale de comprobar que el
    programa está en marcha, no de que se dio permiso: si alguien lo arranca a mano, también se ve.
  - Dura 30 minutos (avisa 2 minutos antes), se corta al bloquear la pantalla, y no se puede pedir con ella bloqueada.
  - Lo que NO garantiza: quien ya tiene acceso total a tu cuenta (tu clave SSH) podría mirar por otros medios sin que
    salga esta ventana. Por eso Acceso remoto enseña quién tiene acceso y deja quitarlo.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

DURACION = 30 * 60            # segundos que dura una sesión
AVISO = 2 * 60                # cuánto antes del final se pregunta «¿seguimos?»
ESPERA_PERMISO = 120          # segundos que espera quien pide a que contesten
PAUSA_TRAS_NO = 60            # tras un «no», segundos sin admitir otra petición
MODOS = ("ver", "manejar")


# ---------- lógica común (sin red ni ventana, para poder probarla) ----------
def carpeta():
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}", "leksso-pantalla")


def ruta(nombre, base=None):
    return os.path.join(base or carpeta(), nombre)


def nombre_limpio(nombre):
    n = re.sub(r"[^A-Za-z0-9._-]", "", nombre or "")[:40]
    return n or "equipo-sin-nombre"


def leer_json(r):
    try:
        with open(r, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def escribir_json(r, d):
    with open(r + ".nuevo", "w", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)) as f:
        json.dump(d, f)
    os.replace(r + ".nuevo", r)


def borrar(r):
    try:
        os.unlink(r)
    except OSError:
        pass


def solicitud_viva(base=None, ahora=None):
    """La petición pendiente, si la hay y no ha caducado."""
    s = leer_json(ruta("solicitud.json", base))
    if not s or not isinstance(s.get("hora"), (int, float)) or (ahora or time.time()) - s["hora"] > ESPERA_PERMISO:
        return None
    return s


def sesion_viva(base=None, ahora=None):
    """La sesión permitida, si no ha caducado."""
    s = leer_json(ruta("sesion.json", base))
    if not s or s.get("modo") not in MODOS or not isinstance(s.get("fin"), (int, float)) or (ahora or time.time()) >= s["fin"]:
        return None
    return s


def motivo_no(base, bloqueado, hay_wayvnc, ahora=None):
    """¿Por qué no se admite ahora una petición? '' si se admite."""
    ahora = ahora or time.time()
    if not os.path.isdir(base):
        return "no hay nadie con la sesion abierta en ese equipo"
    if not hay_wayvnc:
        return "a ese equipo le falta el programa para compartir pantalla (wayvnc)"
    if bloqueado:
        return "ese equipo tiene la pantalla bloqueada"
    if sesion_viva(base, ahora):
        return "ya se esta compartiendo la pantalla de ese equipo"
    if solicitud_viva(base, ahora):
        return "ya hay una peticion esperando respuesta"
    d = leer_json(ruta("denegado.json", base))
    if d and isinstance(d.get("hora"), (int, float)) and ahora - d["hora"] < PAUSA_TRAS_NO:
        return "han dicho que no; espera un minuto antes de volver a pedirlo"
    return ""


def orden_wayvnc(modo, sock, control):
    """wayvnc escuchando en un archivo de la sesión (sin puerto). «ver» no deja usar ratón ni teclado."""
    o = ["wayvnc", "--unix-socket", "--max-fps=15", "--render-cursor", f"--socket={control}"]
    if modo != "manejar":
        o.append("--disable-input")
    return o + [sock]


def que_hacer(sesion, wayvnc_vivo, bloqueado, ahora=None):
    """Decisión del vigilante: 'nada', 'cortar' (y por qué) o 'avisar' (quedan 2 minutos)."""
    ahora = ahora or time.time()
    if not wayvnc_vivo:
        # una sesión sin programa detrás se retira, pero no en sus primeros segundos (está arrancando)
        return ("limpiar", "") if sesion and ahora - sesion.get("inicio", 0) > 10 else ("nada", "")
    if not sesion:
        return "cortar", "sin permiso vigente"
    if bloqueado:
        return "cortar", "pantalla bloqueada"
    if sesion["fin"] - ahora <= AVISO and not sesion.get("avisado"):
        return "avisar", ""
    return "nada", ""


def estado_barra(wayvnc_vivo, sesion):
    """(texto con marcado, clase, ayuda) del aviso de la barra. Sale del programa en marcha, no del permiso."""
    if not wayvnc_vivo:
        return "", "", ""
    quien = f" con {sesion['nombre']}" if sesion and sesion.get("nombre") else ""
    return ('<span color="#ff735a">●  Compartiendo pantalla</span>', "compartiendo",
            f"Se está compartiendo tu pantalla{quien}.\nClic para PARAR (o Súper+Esc).")


def leer_resultado(linea):
    """Lo que contesta «solicitar» -> ('PERMITIDO', modo, socket) o ('DENEGADO', motivo) o None."""
    p = (linea or "").strip().split(" ")
    if p[:1] == ["DENEGADO"]:
        return "DENEGADO", " ".join(p[1:]) or "sin motivo"
    if len(p) == 3 and p[0] == "PERMITIDO" and p[1] in MODOS and re.fullmatch(r"/run/user/\d+/leksso-pantalla/vnc\.sock", p[2]):
        return "PERMITIDO", p[1], p[2]
    return None


def visores():
    """Dónde puede estar el visor VNC en este equipo."""
    c = [shutil.which("vncviewer"), shutil.which("xtigervncviewer"), shutil.which("wlvncc")]
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                c += [os.path.join(base, "TigerVNC", "vncviewer.exe"), os.path.join(base, "TigerVNC 64-bit", "vncviewer.exe")]
    return [x for x in c if x and os.path.isfile(x)]


# ---------- el equipo que recibe la ayuda ----------
def corriendo(programa):
    try:
        return subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", programa], capture_output=True).returncode == 0
    except OSError:
        return False


def bloqueado():
    return corriendo("gtklock") or corriendo("swaylock")


def avisar_barra():
    subprocess.run(["pkill", "-RTMIN+14", "waybar"], capture_output=True)


def notificar(texto):
    try:
        subprocess.run(["notify-send", "-a", "leksso-pantalla", "-t", "8000", "Pantalla compartida", texto], timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def cortar(silencio=False):
    """Deja de compartir ahora. Devuelve True si se estaba compartiendo."""
    base = carpeta()
    habia = corriendo("wayvnc")
    if habia:
        subprocess.run(["wayvncctl", f"--socket={ruta('control.sock', base)}", "wayvnc-exit"], capture_output=True, timeout=5)
        time.sleep(0.4)
        subprocess.run(["pkill", "-u", str(os.getuid()), "-x", "wayvnc"], capture_output=True)
    for n in ("sesion.json", "vnc.sock", "control.sock"):
        borrar(ruta(n, base))
    avisar_barra()
    if habia and not silencio:
        notificar("Listo. Ya nadie ve tu pantalla.")
    return habia


def solicitar(nombre):
    """Lo ejecuta quien pide, por SSH. Deja la petición, espera la respuesta y la imprime en una línea."""
    base = carpeta()
    motivo = motivo_no(base, bloqueado(), shutil.which("wayvnc") is not None)
    if motivo:
        print("DENEGADO " + motivo)
        return 1
    ident = f"{int(time.time() * 1000)}"
    ip = (os.environ.get("SSH_CONNECTION") or "").split(" ")[0] or "este mismo equipo"
    escribir_json(ruta("solicitud.json", base), {"id": ident, "nombre": nombre_limpio(nombre), "ip": ip, "hora": time.time()})
    fin = time.time() + ESPERA_PERMISO
    resp = ruta(f"respuesta-{ident}.json", base)
    while time.time() < fin:
        r = leer_json(resp)
        if r:
            borrar(resp)
            if r.get("decision") in MODOS and os.path.exists(ruta("vnc.sock", base)):
                print(f"PERMITIDO {r['decision']} {ruta('vnc.sock', base)}")
                return 0
            print("DENEGADO " + ("han dicho que no" if r.get("decision") == "no" else "no se pudo empezar a compartir"))
            return 1
        time.sleep(0.5)
    borrar(ruta("solicitud.json", base))
    print("DENEGADO nadie ha contestado a tiempo")
    return 1


def empezar(sol, modo, base=None):
    """Arranca wayvnc para esta petición. True si quedó escuchando."""
    base = base or carpeta()
    sock, control = ruta("vnc.sock", base), ruta("control.sock", base)
    for r in (sock, control):
        borrar(r)
    ahora = time.time()
    escribir_json(ruta("sesion.json", base), {"id": sol["id"], "nombre": sol["nombre"], "ip": sol["ip"], "modo": modo,
                                               "inicio": ahora, "fin": ahora + DURACION, "avisado": False})
    try:
        subprocess.Popen(orden_wayvnc(modo, sock, control), start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        borrar(ruta("sesion.json", base))
        return False
    for _ in range(40):
        if os.path.exists(sock):
            avisar_barra()
            return True
        time.sleep(0.1)
    cortar(silencio=True)
    return False


def responder(sol, decision, base=None):
    base = base or carpeta()
    if decision == "no":
        escribir_json(ruta("denegado.json", base), {"hora": time.time()})
    escribir_json(ruta(f"respuesta-{sol['id']}.json", base), {"decision": decision})
    borrar(ruta("solicitud.json", base))


def vigilar():
    """En la sesión: abre la ventana de permiso, mantiene el botón PARAR y corta cuando toca."""
    base = carpeta()
    os.makedirs(base, mode=0o700, exist_ok=True)
    yo = [sys.executable, os.path.abspath(sys.argv[0])]
    permiso = parar = None
    antes = None
    while True:
        vivo = corriendo("wayvnc")
        if vivo != antes:
            avisar_barra()
            antes = vivo
        sol = solicitud_viva(base)
        if sol and (permiso is None or permiso.poll() is not None) and not vivo:
            permiso = subprocess.Popen(yo + ["ventana"])
        accion, motivo = que_hacer(sesion_viva(base), vivo, bloqueado())
        if accion == "cortar":
            cortar(silencio=(motivo == "pantalla bloqueada"))
            if motivo == "pantalla bloqueada":
                notificar("Se ha dejado de compartir porque la pantalla se bloqueó.")
        elif accion == "limpiar":
            cortar(silencio=True)
        elif accion == "avisar":
            s = sesion_viva(base)
            s["avisado"] = True
            escribir_json(ruta("sesion.json", base), s)
            subprocess.Popen(yo + ["aviso"])
        if vivo and (parar is None or parar.poll() is not None):
            parar = subprocess.Popen(yo + ["parar"])
        elif not vivo and parar is not None and parar.poll() is None:
            parar.terminate()
        time.sleep(1)


def barra():
    texto, clase, ayuda = estado_barra(corriendo("wayvnc"), sesion_viva())
    print(json.dumps({"text": texto, "class": clase, "tooltip": ayuda}))
    return 0


# ---------- ventanas ----------
def _qt():
    for r in ("/usr/local/lib/leksso-ui", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "ui")):
        if r not in sys.path:
            sys.path.insert(0, r)
    from PySide6 import QtCore, QtWidgets
    from leksso_ui import ESTILO_BASE, estilo, pintar
    return QtCore, QtWidgets, ESTILO_BASE, estilo, pintar


def _cabecera(QtWidgets, ventana, raiz, titulo, al_cerrar):
    cab = QtWidgets.QHBoxLayout()
    t = QtWidgets.QLabel(titulo)
    t.setObjectName("titulo")
    t.setWordWrap(True)
    cab.addWidget(t, 1)
    x = QtWidgets.QPushButton("✕")
    x.setObjectName("cerrar")
    x.setToolTip("Cerrar (Esc)")
    x.setAutoDefault(False)
    x.clicked.connect(al_cerrar)
    cab.addWidget(x)
    raiz.addLayout(cab)


def ventana(captura=None, ejemplo=None):
    """«X quiere ver tu pantalla»: No (por defecto), mirar, o mirar y manejar."""
    QtCore, QtWidgets, ESTILO_BASE, estilo, pintar = _qt()
    sol = ejemplo or solicitud_viva()
    if not sol:
        return 0

    class Permiso(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Ver tu pantalla")
            estilo(self, ESTILO_BASE)
            self.hecho = False
            raiz = QtWidgets.QVBoxLayout(self)
            raiz.setContentsMargins(20, 14, 20, 18)
            raiz.setSpacing(12)
            _cabecera(QtWidgets, self, raiz, f"{sol['nombre']} quiere ver tu pantalla", lambda: self.decidir("no"))
            for texto, tam in (("Podrá ver lo que haces ahora. Tú puedes parar cuando quieras.", 17),
                               (f"Viene de {sol['ip']}. Dura 30 minutos como mucho.", 14),
                               ("Si tienes la banca o contraseñas abiertas, ciérralas antes.", 14)):
                e = QtWidgets.QLabel(texto)
                e.setWordWrap(True)
                e.setStyleSheet(f"font-size: {tam}px;" + ("" if tam > 14 else pintar(" color: #94a1a3;")))
                raiz.addWidget(e)
            raiz.addStretch()
            self.no = QtWidgets.QPushButton("No, ahora no")
            self.no.setObjectName("accion")
            self.no.setDefault(True)
            self.no.clicked.connect(lambda: self.decidir("no"))
            raiz.addWidget(self.no)
            for texto, modo in (("Sí, que mire", "ver"), ("Sí, que mire y me ayude a manejar", "manejar")):
                b = QtWidgets.QPushButton(texto)
                b.setObjectName("accion")
                b.setAutoDefault(False)            # Intro nunca permite: hay que pulsarlo con el ratón
                b.setFocusPolicy(QtCore.Qt.NoFocus)
                b.clicked.connect(lambda _=False, m=modo: self.decidir(m))
                raiz.addWidget(b)
            self.no.setFocus()
            self.reloj = QtCore.QTimer(self)
            self.reloj.timeout.connect(self.caduca)
            self.reloj.start(1500)

        def caduca(self):
            if ejemplo is None and not solicitud_viva():
                self.hecho = True
                self.close()

        def decidir(self, decision):
            if self.hecho:
                return
            self.hecho = True
            if ejemplo is None:
                if decision in MODOS and not (bloqueado() or not empezar(sol, decision)):
                    responder(sol, decision)
                else:
                    responder(sol, "no" if decision == "no" else "fallo")
            self.close()

        def closeEvent(self, ev):
            self.decidir("no")
            super().closeEvent(ev)

        def keyPressEvent(self, ev):
            if ev.key() in (QtCore.Qt.Key_Escape, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self.decidir("no")
            else:
                super().keyPressEvent(ev)

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setDesktopFileName("leksso-pantalla")
    w = Permiso()
    w.resize(520, 400)
    w.show()
    if captura:
        app.processEvents()
        w.grab().save(captura)
        return 0
    return app.exec()


def ventana_parar(captura=None):
    """Botón PARAR, pequeño y siempre encima mientras se comparte."""
    QtCore, QtWidgets, ESTILO_BASE, estilo, pintar = _qt()
    s = sesion_viva() or {}

    class Parar(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Compartiendo pantalla")
            estilo(self, ESTILO_BASE)
            raiz = QtWidgets.QVBoxLayout(self)
            raiz.setContentsMargins(12, 10, 12, 12)
            raiz.setSpacing(8)
            quien = f" con {s['nombre']}" if s.get("nombre") else ""
            modo = "Puede manejar tu equipo." if s.get("modo") == "manejar" else "Solo puede mirar."
            e = QtWidgets.QLabel(f"Compartes tu pantalla{quien}.\n{modo}")
            e.setWordWrap(True)
            raiz.addWidget(e)
            b = QtWidgets.QPushButton("PARAR")
            b.setStyleSheet(pintar("QPushButton { background: #ff735a; color: #021012; font-size: 20px; font-weight: bold; "
                                   "border: none; padding: 12px; } QPushButton:hover { background: #e3edef; }"))
            b.clicked.connect(self.parar)
            raiz.addWidget(b)
            pie = QtWidgets.QLabel("También con Súper+Esc.")
            pie.setObjectName("nota")
            raiz.addWidget(pie)

        def parar(self):
            if captura is None:
                cortar()
            self.close()

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setDesktopFileName("leksso-pantalla-parar")
    w = Parar()
    w.resize(280, 170)
    w.show()
    if captura:
        app.processEvents()
        w.grab().save(captura)
        return 0
    return app.exec()


def ventana_aviso():
    """Quedan 2 minutos: ¿seguimos?"""
    QtCore, QtWidgets, ESTILO_BASE, estilo, pintar = _qt()

    class Aviso(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Pantalla compartida")
            estilo(self, ESTILO_BASE)
            raiz = QtWidgets.QVBoxLayout(self)
            raiz.setContentsMargins(20, 14, 20, 18)
            raiz.setSpacing(12)
            _cabecera(QtWidgets, self, raiz, "Se acaba en dos minutos", self.close)
            e = QtWidgets.QLabel("Dejarás de compartir la pantalla. ¿Seguimos media hora más?")
            e.setWordWrap(True)
            raiz.addWidget(e)
            raiz.addStretch()
            fila = QtWidgets.QHBoxLayout()
            no = QtWidgets.QPushButton("No, que se acabe")
            no.setObjectName("accion")
            no.setDefault(True)
            no.clicked.connect(self.close)
            fila.addWidget(no)
            si = QtWidgets.QPushButton("Seguir")
            si.setObjectName("accion")
            si.setAutoDefault(False)
            si.clicked.connect(self.seguir)
            fila.addWidget(si)
            raiz.addLayout(fila)
            QtCore.QTimer.singleShot(AVISO * 1000, self.close)

        def seguir(self):
            s = sesion_viva()
            if s and corriendo("wayvnc"):
                s["fin"] = time.time() + DURACION
                s["avisado"] = False
                escribir_json(ruta("sesion.json"), s)
            self.close()

        def keyPressEvent(self, ev):
            if ev.key() == QtCore.Qt.Key_Escape:
                self.close()
            else:
                super().keyPressEvent(ev)

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setDesktopFileName("leksso-pantalla")
    w = Aviso()
    w.resize(460, 220)
    w.show()
    return app.exec()


# ---------- el equipo que ayuda ----------
def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pedir(destino, clave=None, nombre=None, salida=print):
    if not re.fullmatch(r"([A-Za-z0-9_][A-Za-z0-9._-]*@)?[A-Za-z0-9][A-Za-z0-9.:_-]*", destino or ""):
        salida("Escribe el equipo como usuario@dirección (por ejemplo ana@192.168.1.40).")
        return 2
    base = ["ssh"] + (["-i", clave, "-o", "IdentitiesOnly=yes"] if clave else []) + ["-o", "ConnectTimeout=8"]
    nombre = nombre_limpio(nombre or socket.gethostname())
    salida(f"Pidiendo permiso en {destino}… (mira su pantalla: tiene que pulsar «Sí»)")
    try:
        r = subprocess.run(base + ["-o", "BatchMode=yes", destino, "leksso-pantalla", "solicitar", nombre],
                           capture_output=True, text=True, timeout=ESPERA_PERMISO + 30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        salida("No he podido conectar por SSH con ese equipo.")
        return 1
    res = leer_resultado((r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else "")
    if res is None:
        salida("No he podido pedirlo. ¿Tienes acceso por SSH a ese equipo y está en una versión reciente de LeksSO?")
        if (r.stderr or "").strip():
            salida("  " + r.stderr.strip().splitlines()[-1][:160])
        return 1
    if res[0] == "DENEGADO":
        salida("No se ha permitido: " + res[1] + ".")
        return 1
    _, modo, sock = res
    puerto = puerto_libre()
    tunel = subprocess.Popen(base + ["-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                                     "-L", f"127.0.0.1:{puerto}:{sock}", destino], stdin=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", puerto), timeout=0.5).close()
                break
            except OSError:
                if tunel.poll() is not None:
                    salida("No se pudo abrir el camino hasta ese equipo.")
                    return 1
                time.sleep(0.2)
        salida("Permitido: " + ("puedes mirar y manejar." if modo == "manejar" else "solo puedes mirar."))
        v = visores()
        if v:
            subprocess.run([v[0], f"127.0.0.1::{puerto}"])
        else:
            salida(f"No encuentro un visor VNC. Instala TigerVNC y abre:  127.0.0.1::{puerto}")
            salida("Pulsa Intro aquí cuando termines.")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass
    finally:
        tunel.terminate()
    salida("Fin. En el otro equipo pueden pulsar PARAR para cerrar del todo.")
    return 0


def main(a):
    c = a[0] if a else ""
    if c == "solicitar" and len(a) == 2:
        return solicitar(a[1])
    if c == "vigilar":
        return vigilar()
    if c == "cortar":
        cortar(silencio="--silencio" in a)
        return 0
    if c == "barra":
        return barra()
    if c == "ventana":
        if a[1:2] == ["--captura"] and len(a) == 3:
            return ventana(a[2], {"id": "0", "nombre": "PORTATIL-DE-CASA", "ip": "192.168.1.20", "hora": time.time()})
        return ventana()
    if c == "parar":
        return ventana_parar(a[2] if a[1:2] == ["--captura"] and len(a) == 3 else None)
    if c == "aviso":
        return ventana_aviso()
    if c == "pedir" and len(a) >= 2:
        resto, clave, nombre = a[2:], None, None
        while resto:
            if resto[0] == "--clave" and len(resto) > 1:
                clave, resto = resto[1], resto[2:]
            elif resto[0] == "--nombre" and len(resto) > 1:
                nombre, resto = resto[1], resto[2:]
            else:
                print(__doc__)
                return 2
        return pedir(a[1], clave, nombre)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
