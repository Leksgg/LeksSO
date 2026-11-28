#!/usr/bin/env python3
"""Proyectar (leksso-proyectar): órdenes de cada modo, envío de ventanas, barra al cambiar pantallas y cableado.
Uso: python3 scripts/test_proyectar.py"""
import importlib.machinery
import importlib.util
import json
import os
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
_l = importlib.machinery.SourceFileLoader("leksso_proyectar", os.path.join(RAIZ, "config", "bin", "leksso-proyectar"))
p = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_proyectar", _l))
_l.exec_module(p)


def s(nombre, activa=True, ident=1):
    return {"name": nombre, "active": activa, "id": ident, "rect": {"x": 0}}


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


class Modos(unittest.TestCase):
    dos = [s("HDMI-A-1"), s("eDP-1")]

    def test_la_del_portatil_es_la_principal(self):
        self.assertEqual([x["name"] for x in p.ordenar(self.dos)], ["eDP-1", "HDMI-A-1"])

    def test_solo_enciende_antes_de_apagar(self):
        self.assertEqual(p.ordenes("solo:HDMI-A-1", self.dos), ["output HDMI-A-1 enable", "output eDP-1 disable"])

    def test_una_pantalla_que_no_esta_no_apaga_nada(self):
        self.assertEqual(p.ordenes("solo:DP-9", self.dos), [])
        self.assertEqual(p.ordenes("otra", self.dos), [])

    def test_extender_enciende_todas(self):
        self.assertEqual(p.ordenes("extender", self.dos), ["output eDP-1 enable", "output HDMI-A-1 enable"])


class Posiciones(unittest.TestCase):
    def test_vuelven_a_su_sitio(self):
        dos = [{"name": "eDP-1", "active": True, "rect": {"x": 0, "y": 0}},
               {"name": "HDMI-A-1", "active": True, "rect": {"x": 1920, "y": 0}}]
        self.assertEqual(p.recolocar(p.posiciones(dos), dos),
                         ["output HDMI-A-1 position 1920 0", "output eDP-1 position 0 0"])

    def test_con_otra_pantalla_no_se_recoloca(self):
        self.assertEqual(p.recolocar({"eDP-1": [0, 0], "DP-1": [1920, 0]}, [s("eDP-1"), s("HDMI-A-1")]), [])


class Enviar(unittest.TestCase):
    dos = [s("eDP-1"), s("HDMI-A-1")]

    def test_siguiente_y_anterior_dan_la_vuelta(self):
        self.assertEqual(p.destino(self.dos, "eDP-1", "siguiente"), "HDMI-A-1")
        self.assertEqual(p.destino(self.dos, "HDMI-A-1", "siguiente"), "eDP-1")
        self.assertEqual(p.destino(self.dos, "eDP-1", "anterior"), "HDMI-A-1")

    def test_sin_otra_pantalla_o_nombre_desconocido(self):
        self.assertIsNone(p.destino([s("eDP-1")], "eDP-1", "siguiente"))
        self.assertIsNone(p.destino(self.dos, "eDP-1", "DP-9"))
        self.assertIsNone(p.destino(self.dos, "eDP-1", "eDP-1"))


class Vigilar(unittest.TestCase):
    def revisar(self, antes, ahora):
        with mock.patch.object(p, "salidas", return_value=ahora), mock.patch.object(p, "sway") as sway, \
                mock.patch.object(p, "reiniciar_barra") as barra, mock.patch.object(p, "quitar_espejo") as espejo:
            p.revisar(antes)
        return sway, barra, espejo

    def test_al_arrancar_no_reinicia_la_barra(self):
        self.revisar(None, [s("eDP-1")])[1].assert_not_called()

    def test_sin_cambios_no_hace_nada(self):
        uno = [s("eDP-1")]
        self.revisar(p.firma(uno), uno)[1].assert_not_called()

    def test_la_misma_tele_reconectada_reinicia_la_barra(self):
        antes = p.firma([s("eDP-1"), s("HDMI-A-1", ident=2)])
        self.revisar(antes, [s("eDP-1"), s("HDMI-A-1", ident=7)])[1].assert_called_once()

    def test_al_quitar_la_segunda_se_cierra_el_espejo(self):
        antes = p.firma([s("eDP-1"), s("HDMI-A-1", ident=2)])
        self.revisar(antes, [s("eDP-1")])[2].assert_called_once()

    def test_nunca_deja_todo_apagado(self):
        sway = self.revisar(None, [s("eDP-1", activa=False)])[0]
        sway.assert_called_once_with("output eDP-1 enable")


class Cableado(unittest.TestCase):
    def test_boton_del_rail(self):
        barras = {b["name"]: b for b in json.loads(leer("config/waybar/config.jsonc"))}
        self.assertIn("custom/proyectar", barras["raiz"]["modules-left"])
        self.assertEqual(barras["raiz"]["custom/proyectar"]["on-click"], "leksso-proyectar")
        self.assertEqual(leer("config/waybar/style.css").count("#custom-proyectar"), 2)

    def test_sway(self):
        c = leer("config/sway/config")
        for linea in ("exec leksso-proyectar vigilar", "bindsym $mod+p exec leksso-proyectar",
                      "bindsym button3 focus, exec leksso-proyectar menu", 'app_id="leksso-proyectar"'):
            self.assertIn(linea, c)

    def test_instalacion(self):
        t = leer("scripts/provision-base.sh")
        self.assertIn('config/bin/leksso-proyectar" /usr/local/bin/', t)
        self.assertIn("wl-mirror", t)
        self.assertIn("leksso-barra.reiniciar", leer("config/bin/leksso-barra"))


if __name__ == "__main__":
    unittest.main()
