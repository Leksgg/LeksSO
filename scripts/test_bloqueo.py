#!/usr/bin/env python3
"""Pantalla de bloqueo (leksso-bloquear): diseño válido, textos y respaldo.
Uso: python3 scripts/test_bloqueo.py"""
import importlib.machinery
import importlib.util
import os
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")
l = importlib.machinery.SourceFileLoader("leksso_bloquear", os.path.join(RAIZ, "config/bin/leksso-bloquear"))
blo = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_bloquear", l))
l.exec_module(blo)


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


class Diseno(unittest.TestCase):
    def test_es_xml_valido_y_conserva_lo_que_usa_gtklock(self):
        raiz = ET.fromstring(blo.diseno("LeksSO Beta 0.1.45", "a01").encode("utf-8"))
        ids = {o.get("id") for o in raiz.iter("object")}
        for i in ("window-box", "info-box", "time-box", "clock-label", "date-label", "body-revealer", "body-grid",
                  "input-label", "input-field", "message-revealer", "message-scrolled-window", "message-box",
                  "warning-label", "error-label", "unlock-button"):
            self.assertIn(i, ids)
        manejadores = {s.get("handler") for s in raiz.iter("signal")}
        self.assertEqual(manejadores, {"window_pw_toggle_vis", "window_pw_check"})

    def test_ensena_sistema_usuario_y_el_ojo(self):
        t = blo.diseno("LeksSO Beta 0.1.45", "a01")
        self.assertIn(">LeksSO Beta 0.1.45<", t)
        self.assertIn(">Contraseña de a01<", t)
        self.assertIn("view-reveal-symbolic", t)
        self.assertIn('<property name="visibility">0</property>', t)         # la contraseña empieza oculta
        self.assertIn(">Entrar<", t)

    def test_nombres_raros_no_rompen_el_diseno(self):
        ET.fromstring(blo.diseno('LeksSO <b>&"x"', "usu<ario>&").encode("utf-8"))

    def test_sin_version_dice_solo_el_nombre(self):
        with mock.patch("subprocess.run", side_effect=OSError):
            self.assertEqual(blo.nombre_sistema(), "LeksSO")


class Respaldo(unittest.TestCase):
    def test_sin_gtklock_usa_el_bloqueo_de_antes(self):
        llamadas = []
        def run(orden, **_):
            llamadas.append(orden)
            return mock.Mock(returncode=0)
        with mock.patch.object(blo, "ya_bloqueado", lambda: False), mock.patch("shutil.which", lambda _p: None), \
                mock.patch("subprocess.run", run):
            self.assertEqual(blo.bloquear(), 0)
        self.assertEqual(llamadas, [["swaylock", "-f"]])

    def test_si_gtklock_falla_usa_el_bloqueo_de_antes(self):
        llamadas = []
        def run(orden, **_):
            llamadas.append(orden[0])
            return mock.Mock(returncode=1 if orden[0] == "gtklock" else 0, stdout="")
        with mock.patch.object(blo, "ya_bloqueado", lambda: False), mock.patch("shutil.which", lambda _p: "/usr/bin/gtklock"), \
                mock.patch("subprocess.run", run), mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": __import__("tempfile").mkdtemp()}), \
                mock.patch("getpass.getuser", lambda: "a01"), mock.patch.object(os, "getuid", lambda: 1000, create=True):
            self.assertEqual(blo.bloquear(), 0)
        self.assertEqual(llamadas[-2:], ["gtklock", "swaylock"])

    def test_no_pone_dos_bloqueos(self):
        with mock.patch.object(blo, "ya_bloqueado", lambda: True), mock.patch("subprocess.run") as run:
            self.assertEqual(blo.bloquear(), 0)
            run.assert_not_called()

    def test_todo_bloquea_por_el_mismo_sitio(self):
        self.assertIn('["leksso-bloquear"]', leer("config/bin/leksso-energia"))
        self.assertEqual(leer("config/bin/leksso-reposo").count("'leksso-bloquear'"), 2)
        self.assertNotIn("swaylock -f", leer("config/bin/leksso-reposo"))
        self.assertIn("bindsym $mod+l exec leksso-bloquear", leer("config/sway/config"))
        p = leer("scripts/provision-base.sh")
        self.assertRegex(p, r"ESCRITORIO=\([^)]*\bswaylock gtklock\b")       # el de antes sigue instalado, de respaldo
        self.assertIn('config/bin/leksso-bloquear" /usr/local/bin/', p)


if __name__ == "__main__":
    unittest.main()
