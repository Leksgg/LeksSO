#!/usr/bin/env python3
"""Contexto de seguridad de Wayland para las cajas con ventana (leksso-contexto-wayland y caja.sh --gui).
Hallazgo 1 de la revisión de la 0.1.52. Dos partes:
  - un compositor FALSO que comprueba byte a byte lo que manda el ayudante (el formato del protocolo);
  - sway de verdad, sin pantalla, si está instalado (si no, se omite y se dice).
Solo Linux. Uso: python3 scripts/test_contexto_wayland.py"""
import importlib.machinery
import importlib.util
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_AYUDANTE = os.path.join(AQUI, "leksso-contexto-wayland.py")
cargador = importlib.machinery.SourceFileLoader("contexto_wayland", RUTA_AYUDANTE)
cw = importlib.util.module_from_spec(importlib.util.spec_from_loader("contexto_wayland", cargador))
cargador.exec_module(cw)

SOLO_LINUX = unittest.skipIf(os.name == "nt", "usa sockets Unix y descriptores: se prueba en Linux")


class Falso(threading.Thread):
    """Un compositor de mentira: lo justo para que el ayudante crea que habla con sway, y anota lo que le llega."""

    def __init__(self, ruta, globales, rechazar_commit=False):
        super().__init__(daemon=True)
        self.globales, self.rechazar_commit = globales, rechazar_commit
        self.s = socket.socket(socket.AF_UNIX)
        self.s.bind(ruta)
        self.s.listen(4)
        self.peticiones = []       # (objeto, opcode, datos)
        self.fds = []

    def run(self):
        while True:
            try:
                c, _ = self.s.accept()
            except OSError:
                return
            try:
                self.atender(c)
            except OSError:
                pass
            finally:
                c.close()

    def atender(self, c):
        buf, registro, manager, ctx, ya_error = b"", None, None, None, False
        while True:
            datos, fds, _, _ = socket.recv_fds(c, 65536, 4)
            self.fds += fds
            if not datos and not fds:
                return
            buf += datos
            while len(buf) >= 8:
                objeto, cab = struct.unpack_from("=II", buf)
                tam, op = cab >> 16, cab & 0xFFFF
                if len(buf) < tam:
                    break
                cuerpo, buf = buf[8:tam], buf[tam:]
                self.peticiones.append((objeto, op, cuerpo))
                if objeto == 1 and op == 1:                               # get_registry
                    (registro,) = struct.unpack_from("=I", cuerpo)
                    for n, (nombre, version) in enumerate(self.globales.items(), 1):
                        c.sendall(self.evento(registro, 0, struct.pack("=I", n) + cw.cadena(nombre) + struct.pack("=I", version)))
                elif objeto == 1 and op == 0:                             # sync
                    (cb,) = struct.unpack_from("=I", cuerpo)
                    c.sendall(self.evento(cb, 0, struct.pack("=I", 0)))
                elif objeto == registro and op == 0:                      # bind
                    manager = struct.unpack_from("=I", cuerpo, len(cuerpo) - 4)[0]
                elif objeto == manager and op == 1:                       # create_listener
                    (ctx,) = struct.unpack_from("=I", cuerpo)
                    self.ctx = ctx
                elif objeto == ctx and op == 4 and self.rechazar_commit:  # commit con error de protocolo
                    c.sendall(self.evento(1, 0, struct.pack("=II", ctx, 1) + cw.cadena("metadatos incoherentes")))

    @staticmethod
    def evento(objeto, op, datos):
        return struct.pack("=II", objeto, ((8 + len(datos)) << 16) | op) + datos


@SOLO_LINUX
class Formato(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(dir="/tmp")
        self.ruta = os.path.join(self.d, "wayland-falso")

    def falso(self, **kw):
        f = Falso(self.ruta, kw.pop("globales", {"wl_compositor": 6, cw.GESTOR: 1, "zwlr_screencopy_manager_v1": 3}), **kw)
        f.start()
        self.addCleanup(f.s.close)
        return f

    def test_cadenas_del_protocolo(self):
        for t in ("", "a", "abc", "abcd", "leksso.caja", "ñandú"):
            b = cw.cadena(t)
            self.assertEqual(len(b) % 4, 0, t)
            self.assertEqual(cw.leer_cadena(b, 0), (t, len(b)), t)
        self.assertEqual(cw.cadena("abc"), struct.pack("=I", 4) + b"abc\0")
        self.assertEqual(cw.cadena("abcd"), struct.pack("=I", 5) + b"abcd\0\0\0\0")

    def test_lista_lo_que_ofrece_el_compositor(self):
        self.falso(globales={"wl_compositor": 6, "zwlr_screencopy_manager_v1": 3})
        self.assertEqual(cw.globales_de(self.ruta), {"wl_compositor": (1, 6), "zwlr_screencopy_manager_v1": (2, 3)})

    def test_registra_el_socket_con_las_peticiones_exactas(self):
        f = self.falso()
        escucha = socket.socket(socket.AF_UNIX)
        escucha.bind(os.path.join(self.d, "caja.sock"))
        escucha.listen(1)
        leer, escribir = os.pipe()
        cw.registrar(self.ruta, "ignorada", "leksso.caja.prueba", "abcd1234", escucha, leer)
        # create_listener recibió DOS descriptores (el que escucha y el de cierre) y los cuatro datos del contexto
        self.assertEqual(len(f.fds), 2)
        ops = {p[1]: p[2] for p in f.peticiones if p[0] == f.ctx}            # lo que se le pidió al objeto «contexto»
        creadas = list(ops)
        self.assertIn(1, ops)
        self.assertEqual(cw.leer_cadena(ops[1], 0)[0], cw.MOTOR)                # set_sandbox_engine
        self.assertEqual(cw.leer_cadena(ops[2], 0)[0], "leksso.caja.prueba")    # set_app_id
        self.assertEqual(cw.leer_cadena(ops[3], 0)[0], "abcd1234")              # set_instance_id
        self.assertIn(4, ops)                                                   # commit
        self.assertTrue(creadas)
        orden = [p[1] for p in f.peticiones if p[0] == f.ctx]
        self.assertEqual(orden[:4], [1, 2, 3, 4])                            # engine, app id, instance id, commit, en ese orden
        os.close(escribir)
        escucha.close()

    def test_si_el_compositor_no_admite_el_protocolo_no_sigue(self):
        self.falso(globales={"wl_compositor": 6})
        escucha = socket.socket(socket.AF_UNIX)
        escucha.bind(os.path.join(self.d, "caja.sock"))
        escucha.listen(1)
        leer, escribir = os.pipe()
        with self.assertRaises(cw.ErrorWayland) as e:
            cw.registrar(self.ruta, "x", "a", "i", escucha, leer)
        self.assertIn("no admite wp_security_context_v1", str(e.exception))

    def test_un_error_de_protocolo_del_compositor_se_propaga(self):
        self.falso(rechazar_commit=True)
        escucha = socket.socket(socket.AF_UNIX)
        escucha.bind(os.path.join(self.d, "caja.sock"))
        escucha.listen(1)
        leer, escribir = os.pipe()
        with self.assertRaises(cw.ErrorWayland) as e:
            cw.registrar(self.ruta, "x", "a", "i", escucha, leer)
        self.assertIn("metadatos incoherentes", str(e.exception))

    def test_sin_compositor_da_un_error_claro(self):
        with self.assertRaises(cw.ErrorWayland):
            cw.globales_de(os.path.join(self.d, "no-existe"))

    def test_la_ruta_del_socket(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000", "WAYLAND_DISPLAY": "wayland-1"}):
            self.assertEqual(cw.ruta_de_socket(), "/run/user/1000/wayland-1")
            self.assertEqual(cw.ruta_de_socket("/otro/socket"), "/otro/socket")


@SOLO_LINUX
@unittest.skipUnless(shutil.which("sway") and shutil.which("wayland-info") and shutil.which("bwrap"),
                     "hace falta sway, wayland-info y bubblewrap para esta parte")
class ConSwayDeVerdad(unittest.TestCase):
    """sway sin pantalla (WLR_BACKENDS=headless): lo que de verdad ve una caja con --gui."""
    PELIGROSOS = ("screencopy", "image_copy_capture", "data_control", "virtual_keyboard", "virtual_pointer",
                  "foreign_toplevel", "export_dmabuf", "security_context", "session_lock", "input_method")

    @classmethod
    def setUpClass(cls):
        cls.rt = tempfile.mkdtemp(prefix="xdg-sway-", dir="/tmp")
        os.chmod(cls.rt, 0o700)
        cls.env = dict(os.environ, XDG_RUNTIME_DIR=cls.rt, WLR_BACKENDS="headless", WLR_LIBINPUT_NO_DEVICES="1", WLR_RENDERER="pixman")
        cls.env.pop("WAYLAND_DISPLAY", None)
        cls.sway = subprocess.Popen(["sway", "-c", "/dev/null"], env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fin = time.time() + 15
        cls.socket = None
        while time.time() < fin and cls.socket is None:
            for n in os.listdir(cls.rt):
                if n.startswith("wayland-") and not n.endswith(".lock"):
                    cls.socket = n
            time.sleep(0.2)
        if cls.socket is None:
            cls.sway.kill()
            raise unittest.SkipTest("sway no arrancó sin pantalla en este equipo")
        cls.env["WAYLAND_DISPLAY"] = cls.socket
        cls.sesion = set(cw.globales_de(os.path.join(cls.rt, cls.socket)))

    @classmethod
    def tearDownClass(cls):
        cls.sway.kill()
        cls.sway.wait()

    def caja(self, *opciones, programa=("wayland-info",)):
        return subprocess.run(["bash", os.path.join(AQUI, "caja.sh"), *opciones, "--", *programa], env=dict(
            self.env, LEKSSO_CONTEXTO_WAYLAND=RUTA_AYUDANTE), capture_output=True, text=True, timeout=60)

    @staticmethod
    def interfaces(texto):
        return {p.split("'")[1] for p in texto.splitlines() if p.strip().startswith("interface:")}

    def test_la_sesion_si_ofrece_lo_peligroso(self):
        for p in ("screencopy", "virtual_keyboard", "virtual_pointer", "data_control"):
            self.assertTrue(any(p in g for g in self.sesion), p)             # sin esto la prueba de abajo no demostraría nada

    def test_la_caja_con_gui_no_ve_los_protocolos_privilegiados(self):
        r = self.caja("--gui")
        self.assertEqual(r.returncode, 0, r.stderr)
        vistos = self.interfaces(r.stdout)
        self.assertGreater(len(vistos), 15)                                  # sí ve lo que necesita para dibujar ventanas
        self.assertIn("xdg_wm_base", vistos)
        self.assertIn("wl_seat", vistos)
        for g in vistos:
            for p in self.PELIGROSOS:
                self.assertNotIn(p, g, g)
        self.assertLess(len(vistos), len(self.sesion))

    def test_gui_a_secas_no_trae_xwayland_y_con_x11_si(self):
        r = self.caja("--gui", programa=("sh", "-c", "echo [${DISPLAY:-sin-x11}] $WAYLAND_DISPLAY"))
        self.assertIn("[sin-x11] wayland-0", r.stdout)
        if os.path.isdir("/tmp/.X11-unix"):
            r = self.caja("--gui", "--x11", programa=("sh", "-c", "echo [${DISPLAY:-sin-x11}]"))
            self.assertNotIn("sin-x11", r.stdout)

    def test_gui_completa_avisa_y_enseña_todo(self):
        r = self.caja("--gui-completa")
        self.assertIn("COMPLETO", r.stderr)
        self.assertTrue(any("screencopy" in g for g in self.interfaces(r.stdout)))

    def test_el_ayudante_no_deja_nada_cuando_termina_la_caja(self):
        self.caja("--gui", programa=("true",))
        time.sleep(2.5)
        sobran = [n for n in os.listdir(self.rt) if n.startswith("leksso-contexto-")]
        self.assertEqual(sobran, [])

    def test_sin_compositor_la_caja_con_ventana_no_arranca(self):
        env = dict(self.env, XDG_RUNTIME_DIR=tempfile.mkdtemp(dir="/tmp"), LEKSSO_CONTEXTO_WAYLAND=RUTA_AYUDANTE)
        env.pop("WAYLAND_DISPLAY")
        r = subprocess.run(["bash", os.path.join(AQUI, "caja.sh"), "--gui", "--", "true"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 6)
        self.assertIn("--gui-completa", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class VigilarAlPadre(unittest.TestCase):
    def test_un_zombi_cuenta_como_muerto(self):
        """Quien lanzó la caja termina pero nadie lo recoge todavía: debe verse como muerto (si no, el ayudante no termina)."""
        p = subprocess.Popen(["true"])
        fin = time.time() + 5
        while time.time() < fin and cw._vive(p.pid) and os.path.exists(f"/proc/{p.pid}"):
            time.sleep(0.05)
            try:
                with open(f"/proc/{p.pid}/stat", "rb") as f:
                    if f.read().rsplit(b")", 1)[1].split()[0] == b"Z":
                        break
            except OSError:
                break
        self.assertFalse(cw._vive(p.pid))                                  # sigue sin recoger (zombi)
        p.wait()
        self.assertFalse(cw._vive(p.pid))                                  # ya recogido
        self.assertTrue(cw._vive(os.getpid()))


class Cableado(unittest.TestCase):
    def leer(self, ruta):
        with open(os.path.join(AQUI, "..", ruta), encoding="utf-8") as f:
            return f.read()

    def test_wine_pide_x11_de_forma_explicita(self):
        self.assertIn("caja --gui --x11 ", self.leer("config/bin/leksso-wine"))

    def test_se_instala(self):
        self.assertIn("leksso-contexto-wayland", self.leer("scripts/provision-base.sh"))

    def test_caja_documenta_las_tres_opciones(self):
        t = self.leer("scripts/caja.sh")
        for x in ("--gui-completa", "--x11", "wp_security_context_v1"):
            self.assertIn(x, t)


if __name__ == "__main__":
    import unittest.mock          # noqa: F401  (lo usa test_la_ruta_del_socket)
    unittest.main()
