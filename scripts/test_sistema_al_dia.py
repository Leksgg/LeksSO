#!/usr/bin/env python3
"""«Sistema y controladores» en Actualizaciones: paquetes pendientes, BIOS y el aviso del raíl.
Uso: python3 scripts/test_sistema_al_dia.py"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")


def cargar(nombre, ruta):
    l = importlib.machinery.SourceFileLoader(nombre, os.path.join(RAIZ, ruta))
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader(nombre, l))
    l.exec_module(m)
    return m


hw = cargar("leksso_hardware_t", "scripts/leksso_hardware.py")
act = cargar("leksso_actualizar_t", "scripts/leksso-actualizar.py")
for _n in ("PySide6", "PySide6.QtCore", "PySide6.QtWidgets", "leksso_ui"):
    sys.modules.setdefault(_n, mock.MagicMock())
ven = cargar("leksso_actualizaciones_t", "config/bin/leksso-actualizaciones")


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


class Bios(unittest.TestCase):
    def fw(self, *dispositivos):
        return json.dumps({"Devices": [{"Name": n, "Flags": f} for n, f in dispositivos]})

    def test_equipo_que_admite_actualizarla(self):
        self.assertIs(hw.parsear_bios_fwupd(self.fw(("TPM", ["internal"]), ("System Firmware", ["internal", "updatable"]))), True)

    def test_equipo_que_no_la_lista(self):
        self.assertIs(hw.parsear_bios_fwupd(self.fw(("Disco", ["updatable"]), ("TPM", ["internal"]))), False)

    def test_la_lista_de_revocaciones_no_es_la_bios(self):
        self.assertIs(hw.parsear_bios_fwupd(self.fw(("UEFI dbx", ["updatable"]))), False)

    def test_si_no_se_entiende_no_se_afirma_nada(self):
        for raro in ("", "no es json", "[]", '{"Devices": 3}'):
            self.assertIsNone(hw.parsear_bios_fwupd(raro), raro)
        self.assertIsNone(hw.parsear_bios_fwupd(self.fw(("System Firmware", ["internal"]))))


class AvisoDelRail(unittest.TestCase):
    def estado(self, d):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(d, f)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_cuenta_paquetes_nvidia_y_firmware(self):
        self.assertEqual(act.sistema_pendiente(self.estado({"paquetes": 27})), 27)
        self.assertEqual(act.sistema_pendiente(self.estado(
            {"paquetes": 2, "nvidia": {"accion": "actualizar"}, "firmware": [{"dispositivo": "x"}]})), 4)
        self.assertEqual(act.sistema_pendiente(self.estado({"paquetes": 0, "nvidia": {"accion": None}, "firmware": []})), 0)

    def test_estados_antiguos_o_rotos_no_avisan_de_mas(self):
        self.assertEqual(act.sistema_pendiente(self.estado({"seguro": [{"nombre": "intel-microcode"}]})), 1)    # sin «paquetes»
        self.assertEqual(act.sistema_pendiente(self.estado({"paquetes": "muchos"})), 0)
        self.assertEqual(act.sistema_pendiente(self.estado([1, 2])), 0)
        self.assertEqual(act.sistema_pendiente("/no/existe.json"), 0)

    def test_el_boton_se_marca_con_cosas_del_sistema(self):
        with mock.patch.object(act, "pendiente", lambda: (None, "0.1.49")), mock.patch.object(act, "sistema_pendiente", lambda: 5), \
                mock.patch("builtins.print") as p:
            act.riel()
        d = json.loads(p.call_args[0][0])
        self.assertEqual(d["class"], "hay")
        self.assertIn("5 por instalar", d["tooltip"])
        with mock.patch.object(act, "pendiente", lambda: (None, "0.1.49")), mock.patch.object(act, "sistema_pendiente", lambda: 0), \
                mock.patch("builtins.print") as p:
            act.riel()
        self.assertEqual(json.loads(p.call_args[0][0])["class"], "al-dia")


class Ventana(unittest.TestCase):
    def test_paquetes_pendientes_activan_el_boton(self):
        t, hay = ven.resumen_hw({"paquetes": 27, "firmware": []})
        self.assertTrue(hay)
        self.assertIn("27 actualizaciones del sistema", t)
        self.assertIn("1 actualización del sistema", ven.resumen_hw({"paquetes": 1})[0])

    def test_al_dia(self):
        t, hay = ven.resumen_hw({"paquetes": 0, "firmware": [], "comprobado": 1})
        self.assertFalse(hay)
        self.assertIn("al día", t)

    def test_la_bios_no_promete_lo_que_no_sabe(self):
        b = "HP 84F8 · BIOS AMI F.34 (12/02/2022)"
        si = ven.resumen_hw({"paquetes": 0, "bios": {"texto": b, "por_fwupd": True}})[0]
        self.assertIn(b, si)
        self.assertIn("web de soporte", si)                       # aunque se pueda, se dice dónde confirmarlo
        no = ven.resumen_hw({"paquetes": 0, "bios": {"texto": b, "por_fwupd": False}})[0]
        self.assertIn("no la recibe por aquí", no)
        self.assertTrue(ven.resumen_hw({"paquetes": 0, "bios": {"texto": b, "por_fwupd": None}})[0].endswith(b + "."))
        self.assertNotIn("BIOS", ven.resumen_hw({"paquetes": 0, "bios": {"texto": ""}})[0])

    def test_el_boton_lanza_la_puesta_al_dia_completa(self):
        t = leer("config/bin/leksso-actualizaciones")
        self.assertIn('"sudo leksso-actualizar hardware sistema"', t)
        self.assertIn("Actualizar sistema y controladores", t)


class Comando(unittest.TestCase):
    def test_sistema_actualiza_apt_y_despues_controladores(self):
        llamadas = []

        def run(orden, **_):
            llamadas.append(orden)
            return mock.Mock(returncode=0)
        with mock.patch.object(hw, "raiz_o_salir", lambda: None), mock.patch.object(hw, "aplicar", lambda a: llamadas.append(["APLICAR"]) or 0), \
                mock.patch("subprocess.run", run), mock.patch("builtins.print"):
            self.assertEqual(hw.sistema([]), 0)
        self.assertEqual(llamadas[0][:2], ["apt-get", "update"])
        self.assertEqual(llamadas[1][-1], "upgrade")
        self.assertIn("--with-new-pkgs", llamadas[1])
        self.assertIn("Dpkg::Options::=--force-confold", llamadas[1])       # no pisa tus archivos de configuración
        self.assertNotIn("dist-upgrade", " ".join(llamadas[1]))
        self.assertEqual(llamadas[2], ["APLICAR"])

    def test_esta_en_la_ayuda_y_en_el_reparto(self):
        t = leer("scripts/leksso_hardware.py")
        self.assertIn('if c == "sistema":', t)
        self.assertIn("hardware sistema", t)


if __name__ == "__main__":
    unittest.main()
