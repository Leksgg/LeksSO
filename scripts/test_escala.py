#!/usr/bin/env python3
"""Pruebas de leksso-escala: tamaño de las cifras de Raxtor (regla de fontconfig del usuario) y escala del escritorio
(archivo que incluye sway). Uso: python3 scripts/test_escala.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESCALA = os.path.join(RAIZ, "scripts", "leksso-escala.py")


class PruebasEscala(unittest.TestCase):
    def setUp(self):
        self.casa = tempfile.mkdtemp()
        self.bin = tempfile.mkdtemp()
        for falso in ("pkill", "swaymsg"):          # que no toque la sesión de quien ejecuta las pruebas
            ruta = os.path.join(self.bin, falso)
            open(ruta, "w").write(f'#!/bin/sh\necho "{falso} $*" >> "{self.casa}/ordenes"\n')
            os.chmod(ruta, 0o755)
        self.env = dict(os.environ, HOME=self.casa, PATH=self.bin + os.pathsep + os.environ["PATH"])
        self.regla = os.path.join(self.casa, ".config", "fontconfig", "conf.d", "66-leksso-cifras.conf")
        self.sway = os.path.join(self.casa, ".config", "sway", "escala.conf")

    def tearDown(self):
        shutil.rmtree(self.casa, ignore_errors=True)
        shutil.rmtree(self.bin, ignore_errors=True)

    def escala(self, *a):
        return subprocess.run([sys.executable, ESCALA, *a], env=self.env, capture_output=True, text=True)

    def ordenes(self):
        try:
            return open(os.path.join(self.casa, "ordenes")).read()
        except OSError:
            return ""

    def test_de_serie(self):
        self.assertEqual(self.escala("actual").stdout.split(), ["cifras", "85", "escritorio", "100"])
        self.assertEqual(self.escala("reaplicar").returncode, 0)
        regla = open(self.regla, encoding="utf-8").read()
        self.assertIn("<string>Raxtor</string>", regla)
        self.assertIn("<double>0.85</double>", regla)
        self.assertNotIn("Raxtor Titulos", regla)           # los títulos no se tocan
        self.assertEqual(open(self.sway).read().splitlines()[-1], "output * scale 1")
        self.assertEqual(self.ordenes(), "")                # reaplicar no reinicia nada

    def test_cifras(self):
        self.assertEqual(self.escala("cifras", "75").returncode, 0)
        self.assertIn("<double>0.75</double>", open(self.regla, encoding="utf-8").read())
        self.assertIn("pkill", self.ordenes())               # la barra se reinicia para leer la regla
        self.assertEqual(self.escala("actual").stdout.split()[1], "75")
        self.assertEqual(self.escala("cifras", "100").returncode, 0)
        self.assertFalse(os.path.exists(self.regla))         # tamaño original: sin regla

    def test_escritorio(self):
        self.assertEqual(self.escala("escritorio", "125").returncode, 0)
        self.assertEqual(open(self.sway).read().splitlines()[-1], "output * scale 1.25")
        self.assertIn("swaymsg output * scale 1.25", self.ordenes())
        self.assertEqual(self.escala("actual").stdout.split()[3], "125")

    def test_valores_fuera_de_lista(self):
        for orden, valor in (("cifras", "10"), ("cifras", "abc"), ("escritorio", "1000"), ("escritorio", "1;reboot")):
            r = self.escala(orden, valor)
            self.assertNotEqual(r.returncode, 0, valor)
        self.assertFalse(os.path.exists(self.sway))
        self.assertFalse(os.path.exists(self.regla))
        self.assertEqual(self.ordenes(), "")

    def test_estado_roto_vuelve_a_lo_de_serie(self):
        os.makedirs(os.path.join(self.casa, ".config", "leksso"))
        for roto in ("{no es json", json.dumps({"cifras": 3, "escritorio": "999"})):
            open(os.path.join(self.casa, ".config", "leksso", "escala.json"), "w").write(roto)
            self.assertEqual(self.escala("actual").stdout.split(), ["cifras", "85", "escritorio", "100"])

    def test_sway_incluye_la_escala_antes_que_local(self):
        sway = open(os.path.join(RAIZ, "config", "sway", "config"), encoding="utf-8").read()
        self.assertIn("include ~/.config/sway/escala.conf", sway)
        self.assertLess(sway.index("include ~/.config/sway/escala.conf"), sway.index("include ~/.config/sway/local.conf"))
        prov = open(os.path.join(RAIZ, "scripts", "provision-base.sh"), encoding="utf-8").read()
        self.assertIn("leksso-escala reaplicar", prov)

    @unittest.skipUnless(shutil.which("pango-view") and shutil.which("fc-match"), "sin pango-view")
    def test_la_regla_encoge_solo_las_cifras(self):
        """Con una fuente que se hace pasar por Raxtor, la regla generada estrecha el texto con cifras y no el de letras."""
        fuente = subprocess.run(["fc-match", "-f", "%{file}", "DejaVu Serif:bold"], capture_output=True, text=True).stdout
        if not fuente:
            self.skipTest("sin fuente de prueba")
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "fuentes"))
            shutil.copy(fuente, os.path.join(d, "fuentes", "Raxtor-Regular.ttf"))
            self.assertEqual(self.escala("cifras", "75").returncode, 0)
            base = ('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig>'
                    '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                    f'<dir>{d}/fuentes</dir><cachedir>{d}/cache</cachedir>'
                    '<match target="scan"><test name="file" compare="contains"><string>Raxtor-Regular</string></test>'
                    '<edit name="family" mode="assign"><string>Raxtor</string></edit></match>'
                    f'<include>{os.path.join(RAIZ, "config", "fontconfig", "65-leksso-raxtor.conf")}</include>')
            def ancho(con_regla, texto):
                conf = os.path.join(d, "fonts.conf")
                open(conf, "w").write(base + (f"<include>{self.regla}</include>" if con_regla else "") + "</fontconfig>")
                env = dict(os.environ, FONTCONFIG_FILE=conf)
                subprocess.run(["fc-cache", "-f"], env=env, capture_output=True)
                png = os.path.join(d, "t.png")
                subprocess.run(["pango-view", "-q", "--font=Raxtor, DejaVu Sans 20", f"--text={texto}", "-o", png],
                               env=env, capture_output=True, check=True)
                datos = open(png, "rb").read()
                return int.from_bytes(datos[16:20], "big")   # ancho de la imagen PNG
            self.assertLess(ancho(True, "12% 17:20"), ancho(False, "12% 17:20"))
            self.assertEqual(ancho(True, "CPU Mem"), ancho(False, "CPU Mem"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
