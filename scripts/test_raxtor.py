#!/usr/bin/env python3
"""Fuente Raxtor en LeksSO: solo para cifras, sin tocar la contraseña ni la terminal, y sin la fuente dentro del repositorio.
La parte de fontconfig usa la fuente real si está en el equipo (variable LEKSSO_RAXTOR_DIR, «/mnt/d/Desktop Fonts/TTF» o
~/.local/share/fonts); si no, se omite. Uso: python3 scripts/test_raxtor.py"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
CONF = os.path.join(RAIZ, "config", "fontconfig", "65-leksso-raxtor.conf")


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


def regla(texto, selector):
    """El cuerpo de la regla CSS que empieza por ese selector."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", texto)
    assert m, selector
    return m.group(1)


class Regla(unittest.TestCase):
    def test_es_xml_valido_y_solo_toca_raxtor(self):
        raiz = ET.parse(CONF).getroot()
        self.assertEqual(raiz.tag, "fontconfig")
        coincidencias = raiz.findall("match")
        self.assertEqual(len(coincidencias), 2)
        for m in coincidencias:
            self.assertEqual(m.get("target"), "scan")
        self.assertEqual(coincidencias[0].find("test/string").text, "Raxtor-Bold.ttf")     # primero el Bold, que cambia de familia
        self.assertEqual(coincidencias[1].find("test/string").text, "Raxtor")

    def test_solo_deja_cifras_dos_puntos_y_porcentaje(self):
        cs = ET.parse(CONF).getroot().findall("match")[1].find("edit/charset")
        puntos = set()
        for hijo in cs:
            if hijo.tag == "int":
                puntos.add(int(hijo.text, 0))
            elif hijo.tag == "range":
                a, b = (int(x.text, 0) for x in hijo.findall("int"))
                puntos |= set(range(a, b + 1))
        self.assertEqual(puntos, {0x25} | set(range(0x30, 0x3b)))
        for letra in "aeioun" "ÁÉÑñ¿¡":
            self.assertNotIn(ord(letra), puntos)

    def test_titulos_solo_mayusculas_cifras_y_signos(self):
        m = ET.parse(CONF).getroot().findall("match")[0]
        self.assertEqual(m.find("edit[@name='family']/string").text, "Raxtor Titulos")
        puntos = set()
        for hijo in m.find("edit[@name='charset']/charset"):
            a, b = (int(x.text, 0) for x in hijo.findall("int"))
            puntos |= set(range(a, b + 1))
        for c in "ABZ019 .:-%":
            self.assertIn(ord(c), puntos, c)
        for c in "aenzÁÉÑñ¿¡":
            self.assertNotIn(ord(c), puntos, c)        # lo que Raxtor no trae sale de Montserrat

    def test_no_cambia_las_fuentes_genericas_ni_las_paginas_web(self):
        t = open(CONF, encoding="utf-8").read()
        sin_comentarios = re.sub(r"<!--.*?-->", "", t, flags=re.S)
        self.assertNotIn("<alias", sin_comentarios)
        self.assertNotIn("sans-serif", sin_comentarios)
        self.assertNotIn("<prefer", sin_comentarios)

    def test_se_instala(self):
        p = leer("scripts/provision-base.sh")
        self.assertIn("65-leksso-raxtor.conf", p)
        self.assertIn("/etc/fonts/conf.d/", p)


class DondeSeUsa(unittest.TestCase):
    def test_barra_con_raxtor_primero(self):
        css = leer("config/waybar/style.css")
        familias = re.findall(r"font-family:\s*([^;]+);", css)
        self.assertEqual(len(familias), 3)
        for f in familias:
            self.assertTrue(f.strip().startswith('"Raxtor"'), f)
            self.assertIn("Montserrat", f)                       # las letras salen de Montserrat

    def test_bloqueo_hora_y_fecha_si_contrasena_no(self):
        css = leer("config/bin/leksso-bloquear")
        for sel in ("#clock-label", "#date-label"):
            self.assertIn('"Raxtor", "Montserrat"', regla(css, sel), sel)
        for sel in ("#input-label", "#input-field", "#unlock-button", "#error-label", "#warning-label", "#ayuda-label"):
            self.assertNotIn("Raxtor", regla(css, sel), sel)      # la parte de la contraseña se queda como estaba
        self.assertNotIn("Raxtor", regla(css, "window"))

    def test_ventanas_avisos_y_lanzador(self):
        ui = leer("config/ui/leksso_ui.py")
        self.assertIn('font-family: "Montserrat", "DejaVu Sans"; }', ui)               # cuerpo: Montserrat (Qt dibuja Raxtor entera, no solo cifras)
        self.assertNotRegex(ui.split("QLabel#titulo")[0], r'"Raxtor"')
        self.assertIn('QLabel#titulo { font-family: "Raxtor Titulos", "Montserrat"', ui)  # títulos: Raxtor en MAYÚSCULAS
        self.assertIn("font=Raxtor,Montserrat", leer("config/mako/config"))
        self.assertIn("font=Raxtor:size=13,Montserrat:size=13", leer("config/fuzzel/fuzzel.ini"))
        p = leer("scripts/provision-base.sh")
        self.assertIn("fonts-montserrat", p)
        self.assertIn("fonts-jetbrains-mono", p)
        self.assertIn("font pango:Montserrat", leer("config/sway/config"))

    def test_la_terminal_sigue_en_monoespaciada(self):
        k = leer("config/kitty/kitty.conf")
        self.assertIn("JetBrains Mono", k)
        self.assertNotIn("Raxtor", k)                             # las cifras de una terminal tienen que alinearse


class SinLaFuenteEnElRepositorio(unittest.TestCase):
    def test_ningun_archivo_de_fuente_en_el_repositorio(self):
        r = subprocess.run(["git", "-C", RAIZ, "ls-files"], capture_output=True, text=True)
        if r.returncode != 0:
            self.skipTest("no es un repositorio git")
        fuentes = [x for x in r.stdout.splitlines() if x.lower().endswith((".ttf", ".otf", ".woff", ".woff2", ".ttc"))]
        self.assertEqual(fuentes, [], "Raxtor (y cualquier fuente con derechos reservados) no puede ir en el repositorio público")


def buscar_raxtor():
    candidatas = [os.environ.get("LEKSSO_RAXTOR_DIR", ""), "/mnt/d/Desktop Fonts/TTF", os.path.expanduser("~/.local/share/fonts")]
    for d in candidatas:
        if d and glob.glob(os.path.join(d, "[Rr]axtor-[Rr]egular.ttf")):
            return d
    return None


@unittest.skipUnless(shutil.which("fc-list") and buscar_raxtor(), "hace falta fontconfig y la fuente Raxtor en el equipo")
class ConFontconfigDeVerdad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tempfile.mkdtemp()
        os.makedirs(cls.t + "/fuentes")
        for f in glob.glob(os.path.join(buscar_raxtor(), "[Rr]axtor-*.ttf")):
            shutil.copy(f, cls.t + "/fuentes")
        with open(cls.t + "/fonts.conf", "w", encoding="utf-8") as f:
            f.write(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig>'
                    f'<dir>{cls.t}/fuentes</dir><cachedir>{cls.t}/cache</cachedir><include>{CONF}</include></fontconfig>')
        cls.env = dict(os.environ, FONTCONFIG_FILE=cls.t + "/fonts.conf", HOME=cls.t)

    def lista(self, charset_hex):
        r = subprocess.run(["fc-list", f":charset={charset_hex}", "family"], capture_output=True, text=True, env=self.env)
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]

    def test_ofrece_las_cifras_y_los_dos_puntos(self):
        for c in ("30", "31", "39", "3a", "25"):
            self.assertIn("Raxtor", self.lista(c), c)

    def test_no_ofrece_letras_tildes_ni_signos_de_texto(self):
        for c in ("61", "e1", "f1", "bf", "2c", "2e", "20", "2d"):        # a á ñ ¿ , . espacio -  (en «Raxtor», la de las cifras)
            self.assertNotIn("Raxtor", self.lista(c), c)

    def test_titulos_ofrece_mayusculas_cifras_y_signos_pero_no_minusculas_ni_tildes(self):
        for c in ("41", "5a", "30", "20", "2d", "2e"):
            self.assertIn("Raxtor Titulos", self.lista(c), c)
        for c in ("61", "e1", "d1", "f1", "bf"):
            self.assertNotIn("Raxtor Titulos", self.lista(c), c)


if __name__ == "__main__":
    unittest.main()
