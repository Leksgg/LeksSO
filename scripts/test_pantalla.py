#!/usr/bin/env python3
"""Ver la pantalla de otro equipo (leksso-pantalla) y la ventana «Acceso remoto» (leksso-remoto).
Uso: python3 scripts/test_pantalla.py"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import time
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")


def cargar(nombre, ruta):
    l = importlib.machinery.SourceFileLoader(nombre, os.path.join(RAIZ, ruta))
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader(nombre, l))
    l.exec_module(m)
    return m


pan = cargar("leksso_pantalla_t", "scripts/leksso-pantalla.py")
rem = cargar("leksso_remoto_t", "config/bin/leksso-remoto")
K1 = "AAAAC3NzaC1lZDI1NTE5AAAAIJ1mN0n2c1pQ0m2rYw1k8m3h4u5v6w7x8y9z0a1b2c3d"
K2 = "AAAAC3NzaC1lZDI1NTE5AAAAIKq7m2n3b4v5c6x7z8l9k0j1h2g3f4d5s6a7p8o9i0u1"


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


class Peticiones(unittest.TestCase):
    def test_se_admite_solo_cuando_se_puede_contestar(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pan.motivo_no(d, False, True), "")
            self.assertIn("sesion abierta", pan.motivo_no(os.path.join(d, "no"), False, True))
            self.assertIn("bloqueada", pan.motivo_no(d, True, True))           # con la pantalla bloqueada no se pide
            self.assertIn("wayvnc", pan.motivo_no(d, False, False))

    def test_una_peticion_y_una_sesion_a_la_vez(self):
        with tempfile.TemporaryDirectory() as d:
            ahora = time.time()
            pan.escribir_json(pan.ruta("solicitud.json", d), {"id": "1", "nombre": "X", "ip": "i", "hora": ahora})
            self.assertIn("esperando", pan.motivo_no(d, False, True, ahora))
            self.assertEqual(pan.motivo_no(d, False, True, ahora + pan.ESPERA_PERMISO + 5), "")     # caduca sola
            os.unlink(pan.ruta("solicitud.json", d))
            pan.escribir_json(pan.ruta("sesion.json", d), {"modo": "ver", "fin": ahora + 100, "inicio": ahora})
            self.assertIn("ya se esta compartiendo", pan.motivo_no(d, False, True, ahora))

    def test_tras_un_no_hay_que_esperar(self):
        with tempfile.TemporaryDirectory() as d:
            ahora = time.time()
            pan.responder({"id": "7"}, "no", d)
            self.assertIn("espera", pan.motivo_no(d, False, True, ahora))
            self.assertEqual(pan.motivo_no(d, False, True, ahora + pan.PAUSA_TRAS_NO + 2), "")
            self.assertEqual(pan.leer_json(pan.ruta("respuesta-7.json", d)), {"decision": "no"})

    def test_archivos_solo_para_el_usuario(self):
        if os.name == "nt":
            self.skipTest("permisos de Linux")
        with tempfile.TemporaryDirectory() as d:
            pan.escribir_json(pan.ruta("sesion.json", d), {"a": 1})
            self.assertEqual(os.stat(pan.ruta("sesion.json", d)).st_mode & 0o077, 0)


class Compartir(unittest.TestCase):
    def test_sin_puerto_y_solo_mirar_sin_teclado(self):
        ver = pan.orden_wayvnc("ver", "/run/user/1000/leksso-pantalla/vnc.sock", "/c.sock")
        self.assertIn("--unix-socket", ver)                      # escucha en un archivo de la sesión, no en la red
        self.assertIn("--disable-input", ver)
        self.assertEqual(ver[-1], "/run/user/1000/leksso-pantalla/vnc.sock")
        self.assertNotIn("--disable-input", pan.orden_wayvnc("manejar", "/s", "/c"))
        self.assertIn("--disable-input", pan.orden_wayvnc("cualquier-otra-cosa", "/s", "/c"))   # ante la duda, solo mirar

    def test_el_vigilante_corta_cuando_toca(self):
        t = 1000.0
        s = {"modo": "ver", "inicio": t, "fin": t + pan.DURACION, "avisado": False}
        self.assertEqual(pan.que_hacer(s, True, False, t + 60), ("nada", ""))
        self.assertEqual(pan.que_hacer(None, True, False, t)[0], "cortar")             # alguien lo arrancó sin permiso vigente
        self.assertEqual(pan.que_hacer(s, True, True, t + 60), ("cortar", "pantalla bloqueada"))
        self.assertEqual(pan.que_hacer(s, True, False, t + pan.DURACION - 60)[0], "avisar")
        self.assertEqual(pan.que_hacer(dict(s, avisado=True), True, False, t + pan.DURACION - 60)[0], "nada")
        self.assertEqual(pan.que_hacer(s, False, False, t + 3)[0], "nada")              # arrancando: no se retira todavía
        self.assertEqual(pan.que_hacer(s, False, False, t + 30)[0], "limpiar")
        self.assertEqual(pan.que_hacer(None, False, False, t), ("nada", ""))

    def test_la_sesion_caduca(self):
        with tempfile.TemporaryDirectory() as d:
            t = time.time()
            pan.escribir_json(pan.ruta("sesion.json", d), {"modo": "manejar", "fin": t + 5})
            self.assertIsNotNone(pan.sesion_viva(d, t))
            self.assertIsNone(pan.sesion_viva(d, t + 6))
            pan.escribir_json(pan.ruta("sesion.json", d), {"modo": "raro", "fin": t + 5})
            self.assertIsNone(pan.sesion_viva(d, t))

    def test_el_aviso_sale_del_programa_en_marcha_no_del_permiso(self):
        self.assertEqual(pan.estado_barra(False, {"nombre": "X"}), ("", "", ""))        # con permiso pero sin programa: nada
        texto, clase, ayuda = pan.estado_barra(True, None)                                # sin permiso pero en marcha: se ve
        self.assertEqual(clase, "compartiendo")
        self.assertIn("#ff735a", texto)
        self.assertIn("PARAR", ayuda)
        self.assertIn("con PORTATIL", pan.estado_barra(True, {"nombre": "PORTATIL"})[2])


class QuienAyuda(unittest.TestCase):
    def test_respuesta(self):
        self.assertEqual(pan.leer_resultado("PERMITIDO ver /run/user/1000/leksso-pantalla/vnc.sock\n"),
                         ("PERMITIDO", "ver", "/run/user/1000/leksso-pantalla/vnc.sock"))
        self.assertEqual(pan.leer_resultado("DENEGADO han dicho que no"), ("DENEGADO", "han dicho que no"))
        for mala in ("", "PERMITIDO ver /etc/passwd", "PERMITIDO todo /run/user/1000/leksso-pantalla/vnc.sock",
                     "PERMITIDO ver /run/user/1000/leksso-pantalla/vnc.sock extra", "Welcome to Debian"):
            self.assertIsNone(pan.leer_resultado(mala), mala)

    def test_destino_raro_no_llega_a_ssh(self):
        dicho = []
        for malo in ("-oProxyCommand=calc", "a01@host; rm -rf /", "a b", "", "a01@"):
            self.assertEqual(pan.pedir(malo, salida=dicho.append), 2, malo)

    def test_nombre(self):
        self.assertEqual(pan.nombre_limpio('PC "de" Leks;\n'), "PCdeLeks")


class AccesoRemoto(unittest.TestCase):
    TEXTO = (f'from="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16" ssh-ed25519 {K1} solicitud:DESKTOP-1:2026-11-23\n'
             "# un comentario\n\n"
             f"ssh-ed25519 {K2} leks@portatil\n"
             f"ssh-ed25519 {K1}\n"
             "basura sin clave\n")

    def test_lista_de_quien_puede_entrar(self):
        a = rem.parse_autorizadas(self.TEXTO)
        self.assertEqual([x["nombre"] for x in a], ["DESKTOP-1", "leks@portatil", "Equipo sin nombre"])
        self.assertTrue(a[0]["solo_local"])
        self.assertIn("permitido en pantalla el 2026-11-23", a[0]["detalle"])
        self.assertFalse(a[1]["solo_local"])
        self.assertIn("solo desde tu red", rem.texto_de_lista(a[0]))
        self.assertIn("desde cualquier sitio", rem.texto_de_lista(a[1]))
        self.assertEqual(rem.parse_autorizadas(""), [])

    def test_quitar_solo_esa_linea(self):
        a = rem.parse_autorizadas(self.TEXTO)
        nuevo = rem.quitar(self.TEXTO, a[1]["linea"])
        self.assertNotIn("leks@portatil", nuevo)
        self.assertIn("solicitud:DESKTOP-1", nuevo)
        self.assertIn("# un comentario", nuevo)
        self.assertEqual(len(rem.parse_autorizadas(nuevo)), 2)
        self.assertEqual(rem.quitar("ssh-ed25519 " + K1 + " x\n", "ssh-ed25519 " + K1 + " x"), "")
        self.assertEqual(rem.quitar(self.TEXTO, "no existe"), self.TEXTO)

    def test_frase_de_estado(self):
        self.assertIn("Nadie puede entrar", rem.frase_estado("apagado", 3))
        self.assertIn("1 equipo", rem.frase_estado("local", 1))
        self.assertIn("ningún equipo", rem.frase_estado("local", 0))
        self.assertIn("internet", rem.frase_estado("publico", 2))

    def test_destino(self):
        for bueno in ("ana@192.168.1.40", "192.168.1.40", "a01@leksso-a01", "ana@fe80::1"):
            self.assertTrue(rem.destino_valido(bueno), bueno)
        for malo in ("", "ana@", "ana@host; id", "a b", "-o@x", "ana@host`id`"):
            self.assertFalse(rem.destino_valido(malo), malo)
        self.assertEqual(rem.solo_direccion("ana@192.168.1.40"), "192.168.1.40")

    def test_dice_la_verdad_sobre_lo_que_protege(self):
        t = leer("config/bin/leksso-remoto")
        self.assertIn("no protege frente a quien ya tiene acceso", t)


class Cableado(unittest.TestCase):
    def test_raiz_barra_y_atajo(self):
        barras = json.loads(leer("config/waybar/config.jsonc"))
        raiz = next(b for b in barras if b["name"] == "raiz")
        tareas = next(b for b in barras if b["name"] == "tareas")
        self.assertIn("custom/remoto", raiz["modules-left"])
        self.assertEqual(raiz["custom/remoto"]["on-click"], "leksso-remoto")
        self.assertIn("custom/pantalla", tareas["modules-right"])
        self.assertEqual(tareas["custom/pantalla"]["on-click"], "leksso-pantalla cortar")     # un clic en el aviso corta
        senales = [m["signal"] for b in barras for m in b.values() if isinstance(m, dict) and "signal" in m]
        self.assertEqual(len(senales), len(set(senales)))
        sway = leer("config/sway/config")
        self.assertIn("bindsym $mod+Escape exec leksso-pantalla cortar", sway)
        self.assertIn("exec leksso-pantalla vigilar", sway)
        for app in ("leksso-pantalla", "leksso-pantalla-parar", "leksso-remoto"):
            self.assertIn(f'app_id="{app}"] floating enable', sway)
        self.assertIn("|remoto|pantalla|", leer("config/sway/zonas.sh"))

    def test_instalado_y_se_corta_al_bloquear(self):
        p = leer("scripts/provision-base.sh")
        self.assertRegex(p, r"ESCRITORIO=\([^)]*\bwayvnc\b")
        self.assertIn('scripts/leksso-pantalla.py" /usr/local/bin/leksso-pantalla', p)
        self.assertIn('config/bin/leksso-remoto" /usr/local/bin/leksso-remoto', p)
        self.assertIn('"leksso-pantalla", "cortar", "--silencio"', leer("config/bin/leksso-bloquear"))

    def test_las_ventanas_no_permiten_con_intro_y_tienen_cerrar(self):
        t = leer("scripts/leksso-pantalla.py")
        self.assertIn("self.no.setDefault(True)", t)
        self.assertIn("b.setAutoDefault(False)", t)
        self.assertIn('setObjectName("cerrar")', t)
        self.assertNotIn("shell=True", t)
        self.assertNotIn("shell=True", leer("config/bin/leksso-remoto"))


if __name__ == "__main__":
    unittest.main()
