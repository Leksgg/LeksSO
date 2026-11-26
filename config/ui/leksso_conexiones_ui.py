"""Pestañas de Conexiones, Bloqueos e Historial de la ventana Seguridad (el monitor de conexiones).

Los datos los da `leksso-conexiones` (como administrador, con sudo): esta parte solo los muestra y manda las acciones.
Textos de las acciones (dicen lo que hacen, sin prometer de más):
  Confiar en esto            el programa pasa a «validada»; lo que él lance hereda la confianza
  Parar ahora (puede volver) lo detiene; si algo lo vuelve a lanzar, volverá a conectarse
  Bloquear este destino      corta esa dirección y puerto para todo el equipo hasta que lo quites; NO bloquea al programa
  Abrir su carpeta           muestra dónde está el programa
"""
import datetime as dt
import json
import subprocess

from PySide6 import QtCore, QtGui, QtWidgets

from leksso_ui import confirmar, pedir_permiso, pintar, sudo_cmd

CATEGORIAS = [("entrante", "Entra desde fuera"), ("internet", "Sale a Internet"), ("red_local", "Red local"), ("escuchando", "Escuchando (servicios)")]
COLOR = {"validada": "#85ce6c", "sin validar": "#f4c855", "bloqueada": "#ff735a"}
LIMITES = ("Lo que ves es una foto cada minuto: las conexiones más cortas no salen y UDP no cuenta bytes. «Validada» no es «segura»: "
           "un destino en el que confías puede usarse para sacar datos. Bloquear corta el destino (IP y puerto), no al programa. "
           "Quien tenga permisos de administrador puede apagar este monitor.")


def tamano(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}".replace(".", ",")
        n /= 1024


def cuando(iso_o_ts):
    try:
        f = dt.datetime.fromisoformat(iso_o_ts) if isinstance(iso_o_ts, str) else dt.datetime.fromtimestamp(iso_o_ts)
    except (TypeError, ValueError, OSError):
        return "—"
    return f"{f.day}/{f.month} {f:%H:%M}"


def orden(*args, espera=60):
    return sudo_cmd(["leksso-conexiones", *args], espera=espera)


def error_de(salida, err):
    try:
        return json.loads(salida).get("error", "") or err.strip()
    except ValueError:
        return (err or salida).strip()[-250:]


class Datos(QtCore.QObject):
    """Una sola lectura compartida por las tres pestañas."""
    cambiado = QtCore.Signal()

    def __init__(self, padre):
        super().__init__()
        self.padre = padre
        self.d = {"conexiones": [], "bloqueos": [], "confiables": {}, "eventos": [], "aprende_hasta": None}
        self.error = ""

    def cargar(self):
        if not pedir_permiso(self.padre, "El monitor de conexiones lo maneja el administrador del sistema: hace falta tu permiso."):
            self.error = "Sin el permiso de administrador no se puede leer. Pulsa Actualizar para volver a intentarlo."
        else:
            rc, out, err = orden("listar")
            if rc != 0:
                self.error = "No se pudo leer: " + (error_de(out, err) or "sin respuesta")
            else:
                self.d, self.error = json.loads(out), ""
        self.cambiado.emit()

    def accion(self, *args):
        rc, out, err = orden(*args)
        ok = rc == 0 and (not out.strip().startswith("{") or json.loads(out).get("ok", True))
        return ok, ("" if ok else error_de(out, err))


class Conexiones(QtWidgets.QWidget):
    def __init__(self, datos):
        super().__init__()
        self.datos = datos
        datos.cambiado.connect(self.pintar)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        self.resumen = QtWidgets.QLabel("")
        self.resumen.setWordWrap(True)
        v.addWidget(self.resumen)
        fila = QtWidgets.QHBoxLayout()
        self.cat = QtWidgets.QComboBox()
        self.cat.addItem("Todas las categorías", "")
        for k, t in CATEGORIAS:
            self.cat.addItem(t, k)
        self.cat.currentIndexChanged.connect(self.pintar)
        self.sin = QtWidgets.QCheckBox("Solo sin validar")
        self.sin.toggled.connect(self.pintar)
        self.buscar = QtWidgets.QLineEdit()
        self.buscar.setPlaceholderText("Buscar un programa o un destino…")
        self.buscar.textChanged.connect(self.pintar)
        act = QtWidgets.QPushButton("Actualizar")
        act.setObjectName("accion")
        act.clicked.connect(datos.cargar)
        for w in (self.cat, self.sin):
            fila.addWidget(w)
        fila.addWidget(self.buscar, 1)
        fila.addWidget(act)
        v.addLayout(fila)
        self.arbol = QtWidgets.QTreeWidget()
        self.arbol.setColumnCount(4)
        self.arbol.setHeaderLabels(["Programa", "Destino", "Enviado", "Estado"])
        self.arbol.setUniformRowHeights(True)
        self.arbol.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.arbol.itemSelectionChanged.connect(self.detalle)
        v.addWidget(self.arbol, 1)
        self.det = QtWidgets.QLabel("")
        self.det.setObjectName("dato")
        self.det.setWordWrap(True)
        self.det.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        v.addWidget(self.det)
        b = QtWidgets.QHBoxLayout()
        self.b_confiar = self.boton("Confiar en esto", self.confiar)
        self.b_parar = self.boton("Parar ahora (puede volver)", self.parar)
        self.b_bloquear = self.boton("Bloquear este destino", self.bloquear)
        self.b_carpeta = self.boton("Abrir su carpeta", self.carpeta)
        for x in (self.b_confiar, self.b_parar, self.b_bloquear, self.b_carpeta):
            b.addWidget(x)
        v.addLayout(b)
        self.msg = QtWidgets.QLabel("")
        self.msg.setWordWrap(True)
        v.addWidget(self.msg)
        nota = QtWidgets.QLabel(LIMITES)
        nota.setObjectName("dato")
        nota.setWordWrap(True)
        v.addWidget(nota)

    def boton(self, texto, accion):
        x = QtWidgets.QPushButton(texto)
        x.setObjectName("accion")
        x.clicked.connect(accion)
        return x

    def elegida(self):
        s = self.arbol.selectedItems()
        return s[0].data(0, QtCore.Qt.UserRole) if s else None

    def pintar(self):
        d = self.datos.d
        if self.datos.error:
            self.msg.setText(self.datos.error)
        cs = d["conexiones"]
        fuera = sum(1 for c in cs if c["categoria"] == "internet")
        entran = sum(1 for c in cs if c["categoria"] == "entrante")
        fuera = sum(c.get("conexiones", 1) for c in cs if c["categoria"] == "internet")
        entran = sum(c.get("conexiones", 1) for c in cs if c["categoria"] == "entrante")
        sin = len({c["ident"] for c in cs if c["categoria"] != "escuchando" and c["confianza"] == "sin validar"})
        texto = f"{fuera} conexiones a Internet · {entran} entrantes · {sin} programa(s) sin validar"
        if d.get("aprende_hasta"):
            texto += f"\nAprendiendo: hasta el {cuando(d['aprende_hasta'])} solo se anota lo que conecta, sin avisos."
        self.resumen.setText(texto)
        q = self.buscar.text().strip().lower()
        self.arbol.clear()
        for clave, titulo in CATEGORIAS:
            if self.cat.currentData() and self.cat.currentData() != clave:
                continue
            filas = [c for c in cs if c["categoria"] == clave and (not self.sin.isChecked() or c["confianza"] == "sin validar")
                     and (not q or q in (c["nombre"] + " " + c["destino"] + " " + c.get("paquete", "")).lower())]
            if not filas:
                continue
            filas.sort(key=lambda c: (c["confianza"] != "sin validar", -c["enviados"]))
            raiz = QtWidgets.QTreeWidgetItem([f"{titulo} ({len(filas)})"])
            f = raiz.font(0); f.setBold(True); raiz.setFont(0, f)
            raiz.setFlags(QtCore.Qt.ItemIsEnabled)
            self.arbol.addTopLevelItem(raiz)
            for c in filas:
                estado = "bloqueada" if c.get("bloqueada") else c["confianza"]
                extra = (" · nueva" if c.get("nueva") else "") + (f" · {c['por_que']}" if c.get("por_que") and estado == "validada" else "")
                dest = f"{c['destino']}:{c['puerto']}" + (f" ({c['servicio']})" if c.get("servicio") else "") + (f"  ×{c['conexiones']}" if c.get("conexiones", 1) > 1 else "")
                it = QtWidgets.QTreeWidgetItem([c["nombre"] + (f"  [{c['paquete']}]" if c.get("paquete") else ""), dest, tamano(c["enviados"]), estado + extra])
                it.setForeground(3, QtGui.QBrush(QtGui.QColor(pintar(COLOR.get(estado, "#9d9ea1")))))
                it.setData(0, QtCore.Qt.UserRole, c)
                raiz.addChild(it)
            raiz.setExpanded(clave != "escuchando" or True)
        for col, ancho in ((0, 260), (2, 90), (3, 190)):
            self.arbol.setColumnWidth(col, ancho)
        self.detalle()

    def detalle(self):
        c = self.elegida()
        for x in (self.b_confiar, self.b_parar, self.b_bloquear, self.b_carpeta):
            x.setEnabled(bool(c))
        if not c:
            self.det.setText("Elige una conexión para ver el detalle.")
            return
        mia = c["ident"] in self.datos.d["confiables"]
        self.b_confiar.setText("Dejar de confiar" if mia else "Confiar en esto")
        self.b_confiar.setEnabled(not (c["confianza"] == "validada" and not mia))
        # El bloqueo es de SALIDA (a esa IP y puerto): no impide que otro equipo se conecte hacia aquí, así que
        # no se ofrece para conexiones entrantes (para eso: «Parar ahora», o cerrar el servicio que escucha).
        self.b_bloquear.setEnabled(c["categoria"] == "internet" and not c.get("bloqueada") and c["destino"] not in ("", "*"))
        self.b_bloquear.setToolTip("Bloquea que este equipo se conecte a ese destino." if c["categoria"] == "internet" else
                                   "Solo se bloquean conexiones que salen a Internet. Una conexión entrante no se frena así: usa «Parar ahora» o cierra el servicio que escucha.")
        self.b_carpeta.setEnabled(bool(c.get("exe")))
        self.b_parar.setEnabled(bool(c.get("pid")))
        partes = [f"Programa: {c['nombre']}" + (f" · paquete {c['paquete']}" if c.get("paquete") else " · no viene de un paquete de Debian"),
                  f"Ruta: {c.get('exe') or '—'}", f"Cuenta: {c.get('uid')} · orden: {c.get('cmd') or '—'}"]
        if c.get("unidad"):
            partes.append(f"Servicio de systemd: {c['unidad']}")
        partes.append(f"Confianza: {c['confianza']}" + (f" ({c['por_que']})" if c.get("por_que") else "") + f" · visto por primera vez: {cuando(c.get('primera'))}")
        self.det.setText("\n".join(partes))

    def resultado(self, ok_err, bien):
        ok, err = ok_err
        self.msg.setText(bien if ok else "No se pudo: " + err)
        self.datos.cargar()

    def confiar(self):
        c = self.elegida()
        if not c:
            return
        if c["ident"] in self.datos.d["confiables"]:
            self.resultado(self.datos.accion("dejar-de-confiar", c["ident"]), "Ya no confías en este programa.")
        else:
            self.resultado(self.datos.accion("confiar", c["ident"]), f"Confías en {c['nombre']}: no volverá a aparecer como nuevo, y lo que él lance heredará la confianza.")

    def parar(self):
        c = self.elegida()
        if not c:
            return
        self.resultado(self.datos.accion("parar", c["ident"], str(c["pid"]), c["exe"], str(c.get("inicio") or 0)),
                       f"{c['nombre']} parado. Si algo lo vuelve a lanzar, volverá a conectarse.")

    def bloquear(self):
        c = self.elegida()
        if not c:
            return
        if not confirmar(
            self, "Bloquear este destino",
            f"Se bloqueará {c['destino']}:{c['puerto']} ({c['proto']}) para todo el equipo y seguirá bloqueado hasta que lo quites en la pestaña Bloqueos.\n\n"
            f"Esto bloquea ese destino, no al programa ({c['nombre']}): si su servidor cambia de dirección, el programa podría seguir conectándose.",
            "Bloquear este destino", peligro=True):
            return
        self.resultado(self.datos.accion("bloquear", c["destino"], str(c["puerto"]), "--proto", c["proto"], "--origen", c["nombre"]),
                       f"Bloqueado {c['destino']}:{c['puerto']}. Puedes quitarlo en la pestaña Bloqueos.")

    def carpeta(self):
        c = self.elegida()
        if c and c.get("exe"):
            subprocess.Popen(["xdg-open", c["exe"].rsplit("/", 1)[0] or "/"], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Bloqueos(QtWidgets.QWidget):
    def __init__(self, datos):
        super().__init__()
        self.datos = datos
        datos.cambiado.connect(self.pintar)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        t = QtWidgets.QLabel("Destinos bloqueados. Siguen bloqueados hasta que los quites aquí; se vuelven a cargar solos al arrancar el equipo "
                             "y si se reinicia el cortafuegos.")
        t.setWordWrap(True)
        v.addWidget(t)
        self.lista = QtWidgets.QTreeWidget()
        self.lista.setColumnCount(3)
        self.lista.setHeaderLabels(["Destino", "Desde", "Lo usaba"])
        self.lista.setRootIsDecorated(False)
        self.lista.itemSelectionChanged.connect(lambda: self.quitar.setEnabled(bool(self.lista.selectedItems())))
        v.addWidget(self.lista, 1)
        self.quitar = QtWidgets.QPushButton("Quitar bloqueo")
        self.quitar.setObjectName("accion")
        self.quitar.setEnabled(False)
        self.quitar.clicked.connect(self.hacer)
        v.addWidget(self.quitar)
        self.msg = QtWidgets.QLabel("")
        self.msg.setWordWrap(True)
        v.addWidget(self.msg)

    def pintar(self):
        self.lista.clear()
        for b in self.datos.d["bloqueos"]:
            it = QtWidgets.QTreeWidgetItem([f"{b['destino']}" + (f":{b['puerto']}" if b.get("puerto") else "") + f" ({b.get('proto', 'tcp')})",
                                            cuando(b.get("desde")), b.get("origen") or "—"])
            it.setData(0, QtCore.Qt.UserRole, b["id"])
            self.lista.addTopLevelItem(it)
        if not self.datos.d["bloqueos"]:
            self.msg.setText("No hay ningún destino bloqueado.")
        self.lista.setColumnWidth(0, 260)

    def hacer(self):
        s = self.lista.selectedItems()
        if not s:
            return
        ok, err = self.datos.accion("desbloquear", s[0].data(0, QtCore.Qt.UserRole))
        self.msg.setText("Bloqueo quitado." if ok else "No se pudo: " + err)
        self.datos.cargar()


class Historial(QtWidgets.QWidget):
    def __init__(self, datos):
        super().__init__()
        self.datos = datos
        datos.cambiado.connect(self.pintar)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        t = QtWidgets.QLabel("Lo que ha pasado en los últimos 7 días: entradas por SSH, programas nuevos, envíos altos y lo que tú has hecho. "
                             "Se guardan 30 días, solo con el administrador, sin direcciones web.")
        t.setWordWrap(True)
        v.addWidget(t)
        self.lista = QtWidgets.QTreeWidget()
        self.lista.setColumnCount(2)
        self.lista.setHeaderLabels(["Cuándo", "Qué pasó"])
        self.lista.setRootIsDecorated(False)
        self.lista.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        v.addWidget(self.lista, 1)
        borrar = QtWidgets.QPushButton("Borrar el historial")
        borrar.setObjectName("accion")
        borrar.clicked.connect(self.borrar)
        v.addWidget(borrar)

    def pintar(self):
        self.lista.clear()
        for e in self.datos.d["eventos"]:
            self.lista.addTopLevelItem(QtWidgets.QTreeWidgetItem([cuando(e.get("t")), e.get("texto", "")]))
        self.lista.setColumnWidth(0, 120)

    def borrar(self):
        if confirmar(self, "Borrar el historial", "Se borra el historial de eventos. Los bloqueos y las confianzas no se tocan.",
                     "Borrar el historial", peligro=True):
            self.datos.accion("borrar-historial")
            self.datos.cargar()


def pestanas(padre):
    """(datos, [(widget, título)]) para añadir a la ventana Seguridad."""
    datos = Datos(padre)
    return datos, [(Conexiones(datos), "Conexiones"), (Bloqueos(datos), "Bloqueos"), (Historial(datos), "Historial")]
