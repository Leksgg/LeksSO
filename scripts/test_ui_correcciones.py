#!/usr/bin/env python3
"""Comprobaciones estáticas de las correcciones de la revisión de interfaz (24-nov-2026): foco con teclado, botón principal,
confirmaciones con verbo, ventanas flotantes, gris legible y nombres. Uso: python3 scripts/test_ui_correcciones.py"""
import glob
import os
import re
import unittest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def leer(ruta):
    return open(os.path.join(RAIZ, ruta), encoding="utf-8").read()


def ventanas():
    return [p for p in glob.glob(os.path.join(RAIZ, "config", "bin", "leksso-*")) if os.path.isfile(p)] + \
           glob.glob(os.path.join(RAIZ, "config", "ui", "*.py"))


class Pruebas(unittest.TestCase):
    def test_ningun_control_queda_sin_foco_de_teclado(self):
        for p in ventanas():
            self.assertNotIn("Qt.NoFocus", open(p, encoding="utf-8").read(), p)    # con Tab tiene que verse dónde se está

    def test_el_foco_se_ve_y_hay_boton_principal_y_tema_en_uso(self):
        ui = leer("config/ui/leksso_ui.py")
        for esperado in ("QPushButton:focus {", "QPushButton#principal {", "QPushButton#principal:disabled", "QPushButton#activo {"):
            self.assertIn(esperado, ui, esperado)

    def test_confirmaciones_con_el_verbo_y_cancelar_por_defecto(self):
        ui = leer("config/ui/leksso_ui.py")
        self.assertIn("def confirmar(", ui)
        self.assertIn("setDefaultButton(b_no)", ui)
        for p in ventanas():
            t = open(p, encoding="utf-8").read()
            self.assertNotRegex(t, r"QMessageBox\.question\(", p)          # nada de «Sí / No»

    def test_las_ventanas_grandes_flotan_como_las_demas(self):
        sway = leer("config/sway/config")
        for app in ("leksso-seguridad", "leksso-copias-ui", "leksso-apariencia"):
            self.assertRegex(sway, r'for_window \[app_id="%s"\] floating enable' % app, app)

    def test_gris_tenue_con_contraste_suficiente(self):
        def lum(h):
            c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
            return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        m = re.search(r'"faint":\s*"#([0-9a-fA-F]{6})"', leer("config/tema/grafito.json"))
        fondo = re.search(r'"bg":\s*"#([0-9a-fA-F]{6})"', leer("config/tema/grafito.json")).group(1)
        a, b = sorted((lum(m.group(1)), lum(fondo)), reverse=True)
        self.assertGreaterEqual((a + 0.05) / (b + 0.05), 4.5)
        self.assertNotIn("667576", leer("config/ui/leksso_ui.py"))

    def test_nombres_en_castellano_en_el_menu(self):
        menu = leer("config/bin/leksso-menu")
        self.assertIn('"Brave Web Browser": "Navegador Brave"', menu)
        self.assertIn('"Volume Control": "Volumen"', menu)
        self.assertIn('"btop++"', menu)

    def test_notas_de_version_con_formato(self):
        self.assertIn("setMarkdown(", leer("config/bin/leksso-actualizaciones"))


if __name__ == "__main__":
    unittest.main()
