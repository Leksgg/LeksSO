#!/usr/bin/env python3
"""Pruebas del permiso de administrador de las ventanas (leksso_ui.sudo_modo y sudo_cmd) con un sudo falso que imita los tres
casos reales: sin contraseña (-n), PAM que no la pide (-S) y con contraseña. Uso: python3 scripts/test_sudo.py"""
import importlib.util
import os
import shutil
import stat
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(AQUI, "..", "config", "ui", "leksso_ui.py")

SUDO_FALSO = r'''#!/usr/bin/env python3
import os, subprocess, sys
modo, clave = os.environ["FAKE_SUDO_MODO"], "buena"
a, i, cmd, n, S, v = sys.argv[1:], 0, [], False, False, False
while i < len(a):
    if a[i] == "-n": n = True
    elif a[i] == "-S": S = True
    elif a[i] == "-v": v = True
    elif a[i] == "-p": i += 1
    else: cmd = a[i:]; break
    i += 1
def sin_clave():
    sys.stderr.write("sudo: a password is required\n"); sys.exit(1)
rest = None
if modo == "n":
    pass
elif modo == "S":
    if n: sin_clave()
elif modo == "clave":
    if n: sin_clave()
    linea = sys.stdin.readline().rstrip("\n")
    if linea != clave:
        sys.stderr.write("Sorry, try again.\n"); sys.exit(1)
    rest = sys.stdin.read()
if v or not cmd: sys.exit(0)
datos = rest if rest is not None else (sys.stdin.read() if not sys.stdin.isatty() else "")
r = subprocess.run(cmd, input=datos, capture_output=True, text=True)
sys.stdout.write(r.stdout); sys.stderr.write(r.stderr); sys.exit(r.returncode)
'''


class Pruebas(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        ruta = os.path.join(self.t, "sudo")
        with open(ruta, "w") as f:
            f.write(SUDO_FALSO)
        os.chmod(ruta, os.stat(ruta).st_mode | stat.S_IEXEC)
        self.path = os.environ["PATH"]
        os.environ["PATH"] = self.t + os.pathsep + self.path
        spec = importlib.util.spec_from_file_location("leksso_ui", UI)
        self.ui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ui)

    def tearDown(self):
        os.environ["PATH"] = self.path
        os.environ.pop("FAKE_SUDO_MODO", None)
        shutil.rmtree(self.t, ignore_errors=True)

    def modo(self, m):
        os.environ["FAKE_SUDO_MODO"] = m
        self.ui._SUDO.update({"modo": None, "clave": None})

    def test_no_hereda_una_entrada_estandar_abierta_y_muda(self):
        """Era el origen del fallo intermitente: con la entrada de quien lanza la prueba abierta, el sudo se quedaba esperando
        15 s dos veces. Se prueba con una tubería abierta que nunca recibe nada."""
        import subprocess
        import time
        codigo = ("import sys; sys.path.insert(0, %r); import importlib.util as u; s = u.spec_from_file_location('x', %r); "
                  "m = u.module_from_spec(s); s.loader.exec_module(m); import os; os.environ['FAKE_SUDO_MODO'] = 'n'; "
                  "print(m.sudo_modo())" % (os.path.dirname(UI), UI))
        entorno = dict(os.environ, PATH=self.t + os.pathsep + self.path)
        p = subprocess.Popen([sys.executable, "-c", codigo], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=entorno)
        t0 = time.time()
        try:
            salida, _ = p.communicate(timeout=10)
        finally:
            p.kill()
            p.stdin and p.stdin.close()
        self.assertEqual(salida.strip(), "n")
        self.assertLess(time.time() - t0, 8)

    def test_detecta_los_tres_modos(self):
        for m, esperado in (("n", "n"), ("S", "S"), ("clave", "clave")):
            self.modo(m)
            self.assertEqual(self.ui.sudo_modo(), esperado)

    def test_sin_contrasena_y_con_pam_abierto_pasan_los_datos_intactos(self):
        for m in ("n", "S"):
            self.modo(m)
            rc, out, err = self.ui.sudo_cmd(["cat"], entrada='{"clave":"x"}')
            self.assertEqual((rc, out), (0, '{"clave":"x"}'), m)     # la entrada llega al programa sin tocar

    def test_con_contrasena_hay_que_pedirla_antes(self):
        self.modo("clave")
        self.ui.sudo_modo()
        rc, out, err = self.ui.sudo_cmd(["cat"], entrada="x")
        self.assertEqual(rc, 1)
        self.assertIn("password is required", err)

    def test_con_contrasena_buena_los_datos_siguen_llegando(self):
        self.modo("clave")
        self.ui.sudo_modo()
        self.ui._SUDO["clave"] = "buena"
        rc, out, err = self.ui.sudo_cmd(["cat"], entrada='{"hora":"03:00"}')
        self.assertEqual((rc, out), (0, '{"hora":"03:00"}'))      # la 1.ª línea la consume sudo; el resto es del programa

    def test_contrasena_mala_se_olvida(self):
        self.modo("clave")
        self.ui.sudo_modo()
        self.ui._SUDO["clave"] = "mala"
        rc, _, err = self.ui.sudo_cmd(["cat"], entrada="x")
        self.assertEqual(rc, 1)
        self.assertIsNone(self.ui._SUDO["clave"])                 # para que se vuelva a pedir

    def test_olvidar_clave_al_cerrar(self):
        self.ui._SUDO["clave"] = "algo"
        self.ui.olvidar_clave()
        self.assertIsNone(self.ui._SUDO["clave"])


if __name__ == "__main__":
    unittest.main()
