#!/usr/bin/env python3
"""Pruebas de la barra inferior: batería (colores, parpadeo, carga, sin batería) y modo de energía, con un /sys falso.
Además comprueba que config.jsonc es JSON válido y que los módulos de la barra existen. Uso: python3 scripts/test_barra.py"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(AQUI, "..", "config", "bin")


def cargar(nombre):
    ruta = os.path.join(BIN, nombre)
    cargador = importlib.machinery.SourceFileLoader(nombre.replace("-", "_"), ruta)
    spec = importlib.util.spec_from_loader(cargador.name, cargador)
    mod = importlib.util.module_from_spec(spec)
    cargador.exec_module(mod)
    return mod


bateria = cargar("leksso-barra-bateria")
perfil = cargar("leksso-barra-perfil")


def sysfs(nivel=None, estado="Discharging", corriente=False, extra=None):
    d = tempfile.mkdtemp()
    if nivel is not None:
        b = os.path.join(d, "BAT0")
        os.makedirs(b)
        datos = {"capacity": str(nivel), "status": estado, "energy_now": "30000000", "energy_full": "50000000",
                 "energy_full_design": "60000000", "power_now": "10000000"}
        datos.update(extra or {})
        for k, v in datos.items():
            with open(os.path.join(b, k), "w") as f:
                f.write(v)
    ac = os.path.join(d, "AC")
    os.makedirs(ac)
    with open(os.path.join(ac, "type"), "w") as f:
        f.write("Mains")
    with open(os.path.join(ac, "online"), "w") as f:
        f.write("1" if corriente else "0")
    return d


def leer(nivel, **kw):
    with mock.patch.object(bateria, "RAIZ", sysfs(nivel, **kw)):
        return bateria.estado()


class Bateria(unittest.TestCase):
    def test_colores_por_nivel(self):
        self.assertEqual(leer(80)["class"], ["bien"])
        self.assertEqual(leer(51)["class"], ["bien"])
        self.assertEqual(leer(50)["class"], ["media"])
        self.assertEqual(leer(21)["class"], ["media"])
        self.assertEqual(leer(20)["class"], ["baja"])
        self.assertEqual(leer(11)["class"], ["baja"])

    def test_parpadeo_al_diez_o_menos(self):
        self.assertEqual(leer(10)["class"], ["baja", "critica"])
        self.assertEqual(leer(3)["class"], ["baja", "critica"])

    def test_enchufada_siempre_verde_y_sin_parpadeo(self):
        self.assertEqual(leer(5, estado="Charging", corriente=True)["class"], ["cargando"])
        self.assertEqual(leer(100, estado="Full", corriente=True)["class"], ["cargando"])
        self.assertEqual(leer(8, estado="Not charging", corriente=True)["class"], ["cargando"])

    def test_rayo_solo_al_cargar(self):
        self.assertIn(bateria.RAYO, leer(40, estado="Charging", corriente=True)["text"])
        self.assertNotIn(bateria.RAYO, leer(40)["text"])

    def test_texto_con_porcentaje(self):
        self.assertTrue(leer(42)["text"].endswith("42%"))

    def test_sin_bateria_no_pinta_nada(self):
        self.assertEqual(leer(None), {"text": ""})

    def test_valores_fuera_de_rango_se_recortan(self):
        self.assertEqual(leer(150)["percentage"], 100)

    def test_tooltip_con_tiempo_y_salud(self):
        t = leer(50)["tooltip"]
        self.assertIn("Quedan 3 h 00 min", t)
        self.assertIn("Salud de la batería: 83 %", t)
        self.assertIn("Faltan 2 h 00 min", leer(50, estado="Charging", corriente=True)["tooltip"])

    def test_icono_por_nivel(self):
        self.assertEqual(bateria.icono(0), bateria.PILAS[0])
        self.assertEqual(bateria.icono(100), bateria.PILAS[4])
        self.assertEqual(bateria.icono(50), bateria.PILAS[2])


class Perfil(unittest.TestCase):
    def test_estado_de_cada_modo(self):
        for clave, clase in (("power-saver", "ahorro"), ("balanced", "equilibrado"), ("performance", "rendimiento")):
            with mock.patch.object(perfil, "actual", return_value=clave):
                e = perfil.estado()
            self.assertEqual(e["class"], clase)
            self.assertIn(perfil.MODOS[clave][0], e["text"])

    def test_sin_demonio_se_oculta(self):
        with mock.patch.object(perfil, "actual", return_value=""):
            self.assertEqual(perfil.estado(), {"text": ""})

    def test_menu_elige_y_cambia(self):
        with mock.patch.object(perfil, "actual", return_value="balanced"), \
             mock.patch.object(perfil.shutil, "which", return_value="/usr/bin/fuzzel"), \
             mock.patch.object(perfil.subprocess, "run") as run, \
             mock.patch.object(perfil, "poner") as poner:
            run.return_value = mock.Mock(returncode=0, stdout="2\n")
            self.assertEqual(perfil.menu(), 0)
            poner.assert_called_once_with("performance")

    def test_menu_cancelado_no_cambia(self):
        with mock.patch.object(perfil, "actual", return_value="balanced"), \
             mock.patch.object(perfil.shutil, "which", return_value="/usr/bin/fuzzel"), \
             mock.patch.object(perfil.subprocess, "run") as run, \
             mock.patch.object(perfil, "poner") as poner:
            run.return_value = mock.Mock(returncode=1, stdout="")
            perfil.menu()
            poner.assert_not_called()

    def test_menu_sin_fuzzel_pasa_al_siguiente(self):
        with mock.patch.object(perfil, "actual", return_value="performance"), \
             mock.patch.object(perfil.shutil, "which", return_value=None), \
             mock.patch.object(perfil, "poner") as poner:
            perfil.menu()
            poner.assert_called_once_with("power-saver")


class Configuracion(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(AQUI, "..", "config", "waybar", "config.jsonc"), encoding="utf-8") as f:
            self.barras = {b["name"]: b for b in json.load(f)}

    def test_modulos_declarados(self):
        t = self.barras["tareas"]
        for m in t["modules-right"]:
            if m.startswith("custom/") or m in ("cpu", "memory", "pulseaudio", "network", "clock"):
                self.assertIn(m, t, m)
        self.assertNotIn("custom/version", t["modules-right"])
        self.assertNotIn("battery", t["modules-right"])

    def test_scripts_de_la_barra_existen(self):
        t = self.barras["tareas"]
        for m in ("custom/bateria", "custom/perfil"):
            self.assertTrue(os.path.exists(os.path.join(BIN, t[m]["exec"])))

    def test_senales_sin_repetir(self):
        senales = [m["signal"] for b in self.barras.values() for m in b.values() if isinstance(m, dict) and "signal" in m]
        self.assertEqual(len(senales), len(set(senales)))

    def test_se_instalan_en_provision(self):
        with open(os.path.join(AQUI, "provision-base.sh"), encoding="utf-8") as f:
            s = f.read()
        self.assertIn("leksso-barra-bateria", s)
        self.assertIn("leksso-barra-perfil", s)


if __name__ == "__main__":
    unittest.main()
