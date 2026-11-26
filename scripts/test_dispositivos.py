#!/usr/bin/env python3
"""Cámara y micrófono (leksso-dispositivos), Notificaciones (leksso-notificaciones) y el bloqueo de la cámara.
Uso: python3 scripts/test_dispositivos.py   (las pruebas del bloqueo de verdad solo corren en Linux)"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")


def cargar(nombre, ruta):
    l = importlib.machinery.SourceFileLoader(nombre, os.path.join(RAIZ, ruta))
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader(nombre, l))
    l.exec_module(m)
    return m


disp = cargar("leksso_dispositivos", "config/bin/leksso-dispositivos")
noti = cargar("leksso_notificaciones", "config/bin/leksso-notificaciones")


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


LISTA_V4L2 = """Integrated Camera: Integrated C (usb-0000:00:14.0-8):
\t/dev/video0
\t/dev/video1
\t/dev/media0

Logitech BRIO (usb-0000:00:14.0-2):
\t/dev/video2
\t/dev/video3

Dummy video device (0x0000) (platform:v4l2loopback-000):
\t/dev/video9
"""


class Camara(unittest.TestCase):
    def test_detecta_camaras_y_toma_el_primer_nodo(self):
        c = disp.parse_camaras(LISTA_V4L2)
        self.assertEqual(c[0], ("Integrated Camera: Integrated C", "/dev/video0"))
        self.assertEqual(c[1], ("Logitech BRIO", "/dev/video2"))

    def test_ignora_los_dispositivos_virtuales(self):
        self.assertEqual(len(disp.parse_camaras(LISTA_V4L2)), 2)         # el «loopback» no es una cámara

    def test_sin_camaras(self):
        self.assertEqual(disp.parse_camaras(""), [])
        self.assertEqual(disp.parse_camaras("Cannot open device\n"), [])

    def test_bloqueo_se_lee_del_archivo(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "c.conf")
            self.assertFalse(disp.conf_bloqueo(ruta))
            open(ruta, "w").close()
            self.assertTrue(disp.conf_bloqueo(ruta))


class Sonido(unittest.TestCase):
    def test_volumen(self):
        self.assertEqual(disp.parse_volumen("Volume: 0.45"), (45, False))
        self.assertEqual(disp.parse_volumen("Volume: 1.00 [MUTED]\n"), (100, True))
        self.assertIsNone(disp.parse_volumen(""))
        self.assertIsNone(disp.parse_volumen("Could not find"))

    def test_descripcion_del_dispositivo(self):
        t = 'id 49, type PipeWire:Interface:Node\n    node.description = "Micrófono integrado"\n    node.name = "alsa_input"'
        self.assertEqual(disp.descripcion_nodo(t), "Micrófono integrado")
        self.assertEqual(disp.descripcion_nodo(""), "")


class AvisosDeLaBarra(unittest.TestCase):
    def test_nada_que_ver_si_todo_normal(self):
        self.assertEqual(disp.estado_barra(False, False, False), ("", [], ""))

    def test_camara_en_uso_en_rojo(self):
        t, c, a = disp.estado_barra(True, False, False)
        self.assertIn("#ff735a", t)
        self.assertEqual(c, ["camara-en-uso"])
        self.assertIn("en uso", a)

    def test_camara_bloqueada_en_gris(self):
        t, c, a = disp.estado_barra(False, True, False)
        self.assertEqual(c, ["camara-bloqueada"])
        self.assertIn("bloqueada", a.lower())

    def test_en_uso_manda_sobre_bloqueada(self):
        self.assertEqual(disp.estado_barra(True, True, False)[1], ["camara-en-uso"])

    def test_micro_silenciado_en_ambar_y_se_suma(self):
        t, c, a = disp.estado_barra(True, False, True)
        self.assertEqual(c, ["camara-en-uso", "micro-silenciado"])
        self.assertIn("#f4c855", t)
        self.assertIn("Clic para abrir", a)


class Notificaciones(unittest.TestCase):
    HIST = ("Notification 12: Actualización disponible\n  App name: leksso-actualizar\n  Category: \n  Urgency: normal\n"
            "  Body: LeksSO 0.1.42 ya está\n"
            "Notification 11: Batería baja\n  App name: leksso-barra\n  Urgency: critical\n")

    def test_lee_el_historial(self):
        h = noti.parse_historial(self.HIST)
        self.assertEqual([n["id"] for n in h], [12, 11])
        self.assertEqual(h[0]["app"], "leksso-actualizar")
        self.assertEqual(h[0]["cuerpo"], "LeksSO 0.1.42 ya está")
        self.assertEqual(h[1]["resumen"], "Batería baja")
        self.assertEqual(noti.parse_historial(""), [])

    def test_linea_legible(self):
        h = noti.parse_historial(self.HIST)
        self.assertEqual(noti.resumen_para_lista(h[1]), "leksso-barra · Batería baja")
        self.assertTrue(noti.resumen_para_lista(h[0]).startswith("leksso-actualizar · Actualización disponible — "))
        largo = {"app": "a", "resumen": "x" * 200, "cuerpo": ""}
        self.assertEqual(len(noti.resumen_para_lista(largo)), 90)
        self.assertEqual(noti.resumen_para_lista({"app": "", "resumen": "", "cuerpo": ""}), "(sin título)")

    def test_no_molestar(self):
        self.assertTrue(noti.modo_silencio_activo("default\nsilencio\n"))
        self.assertFalse(noti.modo_silencio_activo("default\n"))
        self.assertFalse(noti.modo_silencio_activo(""))


class Conexion(unittest.TestCase):
    def test_raiz_y_barra_tienen_los_botones(self):
        barras = json.loads(leer("config/waybar/config.jsonc"))
        raiz = next(b for b in barras if b["name"] == "raiz")
        tareas = next(b for b in barras if b["name"] == "tareas")
        for m, prog in (("custom/camara", "leksso-dispositivos"), ("custom/notificaciones", "leksso-notificaciones")):
            self.assertIn(m, raiz["modules-left"])
            self.assertEqual(raiz[m]["on-click"], prog)
        self.assertIn("custom/dispositivos", tareas["modules-right"])
        self.assertEqual(tareas["custom/dispositivos"]["on-click"], "leksso-dispositivos")
        self.assertTrue(tareas["custom/dispositivos"]["hide-empty-text"])

    def test_las_senales_no_se_repiten(self):
        barras = json.loads(leer("config/waybar/config.jsonc"))
        senales = [m["signal"] for b in barras for m in b.values() if isinstance(m, dict) and "signal" in m]
        self.assertEqual(len(senales), len(set(senales)))

    def test_ventanas_flotantes_y_fuera_de_la_zona_central(self):
        sway = leer("config/sway/config")
        zonas = leer("config/sway/zonas.sh")
        for app in ("leksso-dispositivos", "leksso-notificaciones"):
            self.assertIn(f'app_id="{app}"] floating enable', sway)
            self.assertIn(app.replace("leksso-", ""), zonas)

    def test_mako_guarda_historial_y_tiene_no_molestar(self):
        m = leer("config/mako/config")
        self.assertRegex(m, r"max-history=\d+")
        self.assertIn("[mode=silencio]", m)
        self.assertIn("invisible=1", m)

    def test_se_instala_y_bloquear_no_pide_contrasena_pero_permitir_si(self):
        p = leer("scripts/provision-base.sh")
        for x in ("leksso-dispositivos", "leksso-notificaciones", "leksso-camara-raiz.sh", "/etc/sudoers.d/leksso-camara"):
            self.assertIn(x, p)
        regla = re.search(r"printf '%%sudo ALL=\(root\) NOPASSWD:([^']*)'", p[p.index("leksso-camara"):])
        self.assertIsNotNone(regla)
        self.assertIn("leksso-camara-raiz on", regla.group(1))
        self.assertNotIn("leksso-camara-raiz off", regla.group(1))        # permitir la cámara pide contraseña

    def test_la_ventana_tiene_cerrar_y_esc(self):
        for ruta in ("config/bin/leksso-dispositivos", "config/bin/leksso-notificaciones"):
            t = leer(ruta)
            self.assertIn('setObjectName("cerrar")', t)
            self.assertIn("Key_Escape", t)
            self.assertIn("ActivationChange", t)        # se cierra al hacer clic fuera


@unittest.skipIf(sys.platform == "win32", "el bloqueo usa sh y rutas de Linux")
class AyudanteDeBloqueo(unittest.TestCase):
    RUTA = os.path.join(RAIZ, "scripts", "leksso-camara-raiz.sh")

    def correr(self, conf, *args):
        env = dict(os.environ, LEKSSO_CAMARA_CONF=conf)
        return subprocess.run(["sh", self.RUTA, *args], capture_output=True, text=True, env=env)

    def test_on_estado_off(self):
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "bloqueo.conf")
            self.assertEqual(self.correr(conf, "estado").stdout.strip(), "permitida")
            r = self.correr(conf, "on")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.correr(conf, "estado").stdout.strip(), "bloqueada")
            self.assertIn("install uvcvideo /bin/false", open(conf, encoding="utf-8").read())
            self.assertEqual(self.correr(conf, "off").returncode, 0)
            self.assertEqual(self.correr(conf, "estado").stdout.strip(), "permitida")
            self.assertFalse(os.path.exists(conf))

    def test_solo_acepta_sus_tres_ordenes(self):
        with tempfile.TemporaryDirectory() as d:
            for malo in ((), ("encender",), ("on; rm -rf /",), ("off", "extra-ok")):
                r = self.correr(os.path.join(d, "x.conf"), *malo)
                if malo and malo[0] == "off":
                    continue            # «off» con argumentos de más se ignora: lo único que importa es el primero
                self.assertEqual(r.returncode, 2, malo)

    def test_no_deja_archivo_a_medias(self):
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "b.conf")
            self.correr(conf, "on")
            self.assertFalse(os.path.exists(conf + ".nuevo"))


if __name__ == "__main__":
    unittest.main()
