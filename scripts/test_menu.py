#!/usr/bin/env python3
"""Menú de aplicaciones: la pestaña «Para instalar» (catálogo de leksso-apps) e impresoras en la base.
Uso: python3 scripts/test_menu.py"""
import importlib.machinery
import importlib.util
import os
import sys
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")

# El menú importa Qt al cargarse; aquí solo se prueba la lógica, así que se sustituye por dobles.
for nombre in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "leksso_ui"):
    sys.modules.setdefault(nombre, mock.MagicMock())


def cargar(nombre, ruta):
    l = importlib.machinery.SourceFileLoader(nombre, os.path.join(RAIZ, ruta))
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader(nombre, l))
    l.exec_module(m)
    return m


menu = cargar("leksso_menu", "config/bin/leksso-menu")

CAT = [
    ("Juegos", "steam", "Steam", "steam", "steam", "steam", "Cliente oficial."),
    ("Juegos", "heroic", "Epic Games", "deb-github", "x", "heroic", ""),
    ("Vídeo", "obs", "OBS Studio", "apt", "obs-studio", "obs-studio", ""),
    ("Vídeo", "raro", "Cosa manual", "manual", "", "", "A mano."),
    ("Extensiones de VS Code", "vscode-ia", "Extensiones: IA", "vscode-ext", "a.b", "a.b", ""),
]
ALT = {"heroic": "Es de terceros."}


class ParaInstalar(unittest.TestCase):
    def test_solo_lo_que_falta_y_se_puede_instalar(self):
        r = menu.para_instalar(CAT, ALT, lambda tipo, c: c == "obs-studio", hay_code=False)
        self.assertEqual([x[1] for x in r], ["steam", "heroic"])       # obs ya está; manual y extensiones, fuera

    def test_extensiones_solo_con_vscode(self):
        r = menu.para_instalar(CAT, ALT, lambda *_: False, hay_code=True)
        self.assertIn("vscode-ia", [x[1] for x in r])

    def test_alternativa_lleva_su_aviso(self):
        r = {x[1]: x for x in menu.para_instalar(CAT, ALT, lambda *_: False)}
        self.assertEqual(r["heroic"][3:], ("Es de terceros.", True))
        self.assertEqual(r["steam"][3:], ("Cliente oficial.", False))

    def test_si_la_comprobacion_falla_se_ofrece(self):
        def roto(*_):
            raise OSError("sin dpkg")
        self.assertEqual(len(menu.para_instalar(CAT[:1], ALT, roto)), 1)

    def test_orden_de_instalar_va_en_terminal_y_escapa_el_nombre(self):
        o = menu.orden_instalar("obs")
        self.assertEqual(o[0], "leksso-term")
        self.assertIn("leksso-apps instalar obs;", o[-1])
        self.assertIn("'x; rm -rf /'", menu.orden_instalar("x; rm -rf /")[-1])

    def test_el_catalogo_real_se_carga_y_tiene_obs_y_steam(self):
        m = menu.cargar_catalogo()
        self.assertIsNotNone(m)
        ids = [x[1] for x in menu.para_instalar(m.CATALOGO, m.ALTERNATIVAS, lambda *_: False)]
        for esperado in ("obs", "steam"):
            self.assertIn(esperado, ids)

    def test_sin_catalogo_no_revienta(self):
        self.assertIsNone(menu.cargar_catalogo(["/no/existe"]))


class Impresoras(unittest.TestCase):
    def test_la_base_trae_deteccion_y_ventana_de_impresoras(self):
        with open(os.path.join(RAIZ, "scripts", "provision-base.sh"), encoding="utf-8") as f:
            p = f.read()
        for paquete in ("cups", "avahi-daemon", "libnss-mdns", "system-config-printer"):
            self.assertRegex(p, rf"ESCRITORIO=\([^)]*\b{paquete}\b")
        self.assertIn('usermod -aG lpadmin "$USUARIO"', p)

    def test_ajustes_abre_la_ventana_y_si_no_la_web_de_cups(self):
        with open(os.path.join(RAIZ, "config", "bin", "leksso-ajustes"), encoding="utf-8") as f:
            a = f.read()
        self.assertIn("exec system-config-printer || exec brave-browser http://localhost:631", a)


if __name__ == "__main__":
    unittest.main()
