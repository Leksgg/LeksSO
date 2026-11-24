#!/usr/bin/env python3
"""Comprobaciones estáticas de provision-base.sh, que corre con `set -u` y se reejecuta en cada actualización: una variable
usada antes de definirse la rompería entera (pasó con RAIZ). Uso: python3 scripts/test_provision.py"""
import os
import re
import subprocess
import unittest

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "provision-base.sh")


class Pruebas(unittest.TestCase):
    def setUp(self):
        self.lineas = open(RUTA, encoding="utf-8").read().splitlines()

    def test_las_variables_se_definen_antes_de_usarse(self):
        definidas = set()
        for i, l in enumerate(self.lineas, 1):
            s = l.strip()
            if s.startswith("#"):
                continue
            usadas = set(re.findall(r"\$\{?(RAIZ|USUARIO|HOME_USR)\b", re.sub(r"'[^']*'", "''", s)))
            for v in usadas - definidas:
                self.fail(f"línea {i}: ${v} se usa antes de definirse: {s[:80]}")
            for v in re.findall(r"^(RAIZ|USUARIO|HOME_USR)=", s):
                definidas.add(v)

    def test_sintaxis(self):
        r = subprocess.run(["bash", "-n", RUTA], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_el_usuario_no_entra_en_input_ni_se_instala_firejail(self):
        codigo = [l for l in self.lineas if not l.strip().startswith("#")]
        for l in codigo:
            if "usermod -aG" in l:
                self.assertNotRegex(l, r"\binput\b", l)          # hallazgo 7: lectura del teclado de todos
        self.assertFalse([l for l in codigo if re.search(r"AISLAMIENTO=.*firejail", l.split("#")[0])])    # hallazgo 15
        self.assertTrue([l for l in codigo if "usermod -aG" in l and "seatd" in l], "el usuario debe seguir en el grupo seatd")

    def test_reinicia_el_permisor_en_marcha_para_que_lo_reconozca_el_servicio_de_administracion(self):
        texto = "\n".join(l for l in self.lineas if not l.strip().startswith("#"))
        self.assertRegex(texto, r"try-restart leksso-permisor\.service")
        self.assertLess(texto.index('leksso-permisor.service" /etc/systemd/user/'), texto.index("try-restart leksso-permisor.service"))   # primero la unidad nueva, luego el reinicio

    def test_no_instala_npm_ni_los_asistentes_en_cada_provision(self):
        for l in self.lineas:
            if not l.strip().startswith("#"):
                self.assertNotRegex(l, r"npm install", l)       # hallazgo 5: se instalan al elegirlos, con versión fijada

    def test_instala_lo_que_las_ventanas_y_el_registro_necesitan(self):
        texto = "\n".join(self.lineas)
        for esperado in ("leksso-auditoria", "99leksso-auditoria", "leksso-seguridad", "leksso-copias", "leksso-copias-ui",
                         "leksso-auditoria-foto.timer", "leksso-tema", "leksso-apariencia", "leksso-conexiones", "leksso-conexiones-foto.timer",
                         "leksso-bloqueos.service", "leksso_conexiones_ui.py", "confiables-de-fabrica.json"):
            self.assertIn(esperado, texto, esperado)


if __name__ == "__main__":
    unittest.main()
