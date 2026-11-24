#!/usr/bin/env python3
"""Comprobaciones estáticas de zonas.sh y de quien lo llama: el panel de la IA solo existe cuando hace falta (un asistente abierto o
el panel abierto a mano) y el botón de carpetas muestra u oculta el panel lateral del explorador. Uso: python3 scripts/test_zonas.py"""
import os
import re
import subprocess
import unittest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def leer(ruta):
    return open(os.path.join(RAIZ, ruta), encoding="utf-8").read()


def sin_comentarios(t):
    return "\n".join(l for l in t.splitlines() if not l.strip().startswith("#"))


class Pruebas(unittest.TestCase):
    def test_sintaxis(self):
        r = subprocess.run(["bash", "-n", os.path.join(RAIZ, "config", "sway", "zonas.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_el_panel_de_la_ia_no_se_monta_al_arrancar(self):
        z = sin_comentarios(leer("config/sway/zonas.sh"))
        montar = z[z.index("montar() {"):z.index("\n}\n", z.index("montar() {"))]
        self.assertNotIn("panel.py", montar)
        self.assertNotIn("panel-ia", montar)

    def test_la_zona_se_crea_al_lanzar_un_asistente_o_abrir_el_panel(self):
        self.assertIn("--zona-ia", leer("config/sway/zonas.sh"))
        self.assertRegex(leer("config/bin/leksso-asistentes"), r'"leksso-zonas", "--zona-ia", "--auto"')
        self.assertIn("leksso-zonas --zona-ia", leer("config/bin/leksso-panel-ia"))

    def test_la_zona_abierta_por_un_asistente_se_cierra_con_el_ultimo_y_la_abierta_a_mano_se_queda(self):
        z = leer("config/sway/zonas.sh")
        self.assertIn("cerrar_zona_auto", z)
        self.assertRegex(z, r'if \[ "\$\{1:-\}" = "--auto" \]; then : > "\$ZONA_AUTO"; else rm -f "\$ZONA_AUTO"; fi')
        self.assertRegex(z, r'\[ -e "\$ZONA_AUTO" \] \|\| return 0')           # sin marca no se cierra nada

    def test_el_boton_de_carpetas_ya_no_depende_de_una_marca_que_no_existe(self):
        z = sin_comentarios(leer("config/sway/zonas.sh"))
        plegar = z[z.index("plegar() {"):z.index("\n}\n", z.index("plegar() {"))]
        self.assertNotIn('con_mark="explorador"', plegar)
        self.assertIn("wtype -k F9", plegar)
        self.assertIn("wtype", sin_comentarios(leer("scripts/provision-base.sh")))


if __name__ == "__main__":
    unittest.main()
