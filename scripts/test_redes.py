#!/usr/bin/env python3
"""Ventana de redes (leksso-redes): lectura de nmcli, órdenes de conexión y conexión con la barra y Ajustes.
Uso: python3 scripts/test_redes.py"""
import importlib.machinery
import importlib.util
import json
import os
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


l = importlib.machinery.SourceFileLoader("leksso_redes", os.path.join(RAIZ, "config/bin/leksso-redes"))
redes = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_redes", l))
l.exec_module(redes)

WIFI = ("*:Casa:78:WPA2\n"
        " :Casa:40:WPA2\n"
        " :Vecino\\:5G:90:WPA1 WPA2\n"
        " ::55:WPA2\n"
        " :Bar abierto:30:\n"
        " :Otra:xx:--\n")


class Lectura(unittest.TestCase):
    def test_partir_respeta_los_dos_puntos_del_nombre(self):
        self.assertEqual(redes.partir(" :Vecino\\:5G:90:WPA2"), [" ", "Vecino:5G", "90", "WPA2"])
        self.assertEqual(redes.partir("a\\\\b:c"), ["a\\b", "c"])

    def test_lista_de_wifi(self):
        r = redes.parse_wifi(WIFI)
        self.assertEqual([x["ssid"] for x in r], ["Casa", "Vecino:5G", "Bar abierto", "Otra"])   # conectada arriba; oculta fuera
        self.assertTrue(r[0]["en_uso"])
        self.assertEqual(r[0]["senal"], 78)                 # la antena en uso, no la repetida
        self.assertFalse(r[2]["segura"])
        self.assertFalse(r[3]["segura"])
        self.assertEqual(r[3]["senal"], 0)
        self.assertEqual(redes.parse_wifi(""), [])

    def test_redes_guardadas_solo_wifi(self):
        t = "Casa:802-11-wireless\nCable 1:802-3-ethernet\nlo:loopback\nMi\\:red:802-11-wireless\n"
        self.assertEqual(redes.parse_guardadas(t), {"Casa", "Mi:red"})

    def test_estado(self):
        self.assertEqual(redes.parse_estado("wlan0:wifi:connected:Casa\nlo:loopback:unmanaged:\n"),
                         ("Conectado por wifi a Casa.", True))
        self.assertEqual(redes.parse_estado("eth0:ethernet:connected:Cable\nwlan0:wifi:disconnected:\n"),
                         ("Conectado por cable.", True))
        self.assertEqual(redes.parse_estado("eth0:ethernet:unavailable:\n"), ("Sin conexión.", False))
        self.assertEqual(redes.parse_estado(""), ("Sin conexión.", False))

    def test_linea_de_la_lista(self):
        r = redes.parse_wifi(WIFI)
        self.assertIn("Casa", redes.linea_red(r[0], {"Casa"}))
        self.assertIn("conectada, con clave", redes.linea_red(r[0], {"Casa"}))
        self.assertIn("guardada, con clave", redes.linea_red(r[1], {"Vecino:5G"}))
        self.assertTrue(redes.linea_red(r[2], set()).endswith("abierta"))

    def test_barras_de_senal(self):
        self.assertEqual([len(redes.barras(s)) for s in (0, 25, 26, 60, 80, 100, 250)], [1, 1, 2, 3, 4, 4, 4])


class Conexion(unittest.TestCase):
    def test_clave_wifi(self):
        self.assertFalse(redes.clave_valida("1234567"))
        self.assertTrue(redes.clave_valida("12345678"))
        self.assertFalse(redes.clave_valida("x" * 64))
        self.assertFalse(redes.clave_valida(None))

    def test_ordenes(self):
        self.assertEqual(redes.orden_conectar("Casa", {"Casa"})[3:], ["connection", "up", "id", "Casa"])
        o = redes.orden_conectar("Nueva; rm -rf /", set(), "clave secreta")
        self.assertEqual(o[3:], ["device", "wifi", "connect", "Nueva; rm -rf /", "password", "clave secreta"])   # un argumento, sin shell
        self.assertNotIn("password", redes.orden_conectar("Bar abierto", set()))

    def test_errores_en_cristiano(self):
        self.assertEqual(redes.mensaje_error("Error: Connection activation failed: Secrets were required, but not provided."),
                         "La clave no es correcta.")
        self.assertIn("Buscar de nuevo", redes.mensaje_error("Error: No network with SSID 'x' found."))
        self.assertEqual(redes.mensaje_error(""), "No he podido conectar.")
        self.assertTrue(redes.mensaje_error("Error: algo raro").startswith("No he podido conectar. Error: algo raro"))


class Cableado(unittest.TestCase):
    def test_la_barra_y_ajustes_abren_la_ventana_no_la_terminal(self):
        barras = json.loads(leer("config/waybar/config.jsonc"))
        tareas = next(b for b in barras if b["name"] == "tareas")
        self.assertEqual(tareas["network"]["on-click"], "leksso-redes")
        self.assertIn('("Red", "Cable y Wi-Fi", ["leksso-redes"], "nmcli")', leer("config/bin/leksso-ajustes"))

    def test_flotante_fuera_del_centro_e_instalada_con_la_de_texto(self):
        self.assertIn('app_id="leksso-redes"] floating enable', leer("config/sway/config"))
        self.assertIn("|redes|", leer("config/sway/zonas.sh"))
        p = leer("scripts/provision-base.sh")
        self.assertIn('config/bin/leksso-redes"', p)
        self.assertIn('config/bin/leksso-redes-texto"', p)
        self.assertIn("exec nmtui", leer("config/bin/leksso-redes-texto"))

    def test_la_ventana_tiene_cerrar_esc_y_no_usa_shell(self):
        t = leer("config/bin/leksso-redes")
        self.assertIn('setObjectName("cerrar")', t)
        self.assertIn("Key_Escape", t)
        self.assertNotIn("shell=True", t)


if __name__ == "__main__":
    unittest.main()
