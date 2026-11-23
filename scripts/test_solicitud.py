#!/usr/bin/env python3
"""Solicitud de conexión por SSH (leksso-solicitud): protocolo, código, límites, autorización y cableado.
Uso: python3 scripts/test_solicitud.py"""
import importlib.machinery
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")

l = importlib.machinery.SourceFileLoader("leksso_solicitud", os.path.join(AQUI, "leksso-solicitud.py"))
sol = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_solicitud", l))
l.exec_module(sol)

CLAVE = ("ssh-ed25519", "AAAAC3NzaC1lZDI1NTE5AAAAIJ1mN0n2c1pQ0m2rYw1k8m3h4u5v6w7x8y9z0a1b2c3d")
OTRA = ("ssh-ed25519", "AAAAC3NzaC1lZDI1NTE5AAAAIKq7m2n3b4v5c6x7z8l9k0j1h2g3f4d5s6a7p8o9i0u1")
HOST = ("ssh-ed25519", "AAAAC3NzaC1lZDI1NTE5AAAAIHhostkeyhostkeyhostkeyhostkeyhostkeyhostke0")


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


class Protocolo(unittest.TestCase):
    def test_palabras_del_codigo(self):
        self.assertEqual(len(sol.PALABRAS), len(set(sol.PALABRAS)))
        self.assertGreaterEqual(len(sol.PALABRAS), 120)
        for p in sol.PALABRAS:
            self.assertRegex(p, r"^[a-z]{2,7}$")            # sin tildes ni eñes: se leen y se comparan fácil

    def test_el_codigo_depende_de_las_tres_cosas(self):
        c = sol.codigo(CLAVE, HOST, "00112233aabbccdd")
        self.assertRegex(c, r"^[a-z]+-[a-z]+$")
        self.assertEqual(c, sol.codigo(CLAVE, HOST, "00112233aabbccdd"))
        distintos = {sol.codigo(CLAVE, HOST, f"{i:016x}") for i in range(200)}
        self.assertGreater(len(distintos), 150)             # el número del equipo cambia el código
        self.assertGreater(len({sol.codigo(CLAVE, HOST, "0" * 16), sol.codigo(OTRA, HOST, "0" * 16),
                                sol.codigo(CLAVE, OTRA, "0" * 16)}), 1)

    def test_clave_publica(self):
        self.assertEqual(sol.partir_clave(" ".join(CLAVE) + " yo@casa"), CLAVE)
        for mala in ("", "ssh-ed25519", "ssh-dss AAAA" + "B" * 60, "ssh-ed25519 no*es*base64" + "A" * 40,
                     'command="rm" ssh-ed25519 ' + CLAVE[1], "ssh-ed25519 " + "A" * 10):
            self.assertIsNone(sol.partir_clave(mala), mala)

    def test_nombre_del_equipo(self):
        self.assertEqual(sol.nombre_limpio('PORTATIL "de" Leks; rm -rf /\n'), "PORTATILdeLeksrm-rf")
        self.assertEqual(sol.nombre_limpio(""), "equipo-sin-nombre")
        self.assertEqual(len(sol.nombre_limpio("x" * 200)), 40)

    def test_ida_y_vuelta_de_la_solicitud(self):
        linea = sol.linea_solicitud("DESKTOP-1", CLAVE)
        self.assertEqual(sol.leer_solicitud(linea), ("DESKTOP-1", CLAVE))
        for mala in ("", "HOLA", "LEKSSO-SOLICITUD 2 x " + " ".join(CLAVE), "LEKSSO-SOLICITUD 1 a b " + " ".join(CLAVE),
                     'LEKSSO-SOLICITUD 1 a"b ' + " ".join(CLAVE), "LEKSSO-SOLICITUD 1 x ssh-ed25519 mal"):
            self.assertIsNone(sol.leer_solicitud(mala), mala)

    def test_respuesta(self):
        r = sol.leer_respuesta(f"PENDIENTE 1 00112233aabbccdd a01 {HOST[0]} {HOST[1]}\n")
        self.assertEqual(r, ("PENDIENTE", "00112233aabbccdd", "a01", HOST))
        self.assertEqual(sol.leer_respuesta("RECHAZADA ya hay una\n"), ("RECHAZADA", "ya hay una"))
        for mala in ("", "PENDIENTE 1 corto a01 x y", f"PENDIENTE 1 00112233aabbccdd -oProxyCommand=x {HOST[0]} {HOST[1]}",
                     f"PENDIENTE 1 00112233aabbccdd root;id {HOST[0]} {HOST[1]}"):
            self.assertIsNone(sol.leer_respuesta(mala), mala)

    def test_solo_red_local(self):
        for ip in ("192.168.1.20", "10.0.0.5", "172.16.3.4", "127.0.0.1", "::ffff:192.168.1.9", "::1"):
            self.assertTrue(sol.es_local(ip), ip)
        for ip in ("8.8.8.8", "172.32.0.1", "", "no-es-ip", "2001:db8::1", "::ffff:8.8.8.8"):
            self.assertFalse(sol.es_local(ip), ip)


class Cola(unittest.TestCase):
    def poner(self, d, ip="192.168.1.20", hora=None, nombre="X"):
        s = {"nombre": nombre, "ip": ip, "clave": list(CLAVE), "nonce": "0" * 16, "codigo": "pera-luna",
             "hora": hora or time.time()}
        ruta = os.path.join(d, f"{int(s['hora'] * 1000)}-{ip}.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(s, f)
        return ruta

    def test_caducan_y_las_rotas_se_borran(self):
        with tempfile.TemporaryDirectory() as d:
            viva = self.poner(d)
            vieja = self.poner(d, ip="192.168.1.21", hora=time.time() - sol.CADUCA - 5)
            rota = os.path.join(d, "1-rota.json")
            open(rota, "w").write("{no es json")
            p = sol.pendientes(d)
            self.assertEqual([s["ruta"] for s in p], [viva])
            self.assertFalse(os.path.exists(vieja))
            self.assertFalse(os.path.exists(rota))

    def test_limites(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sol.motivo_rechazo(d, "192.168.1.20"), "")
            self.assertIn("red local", sol.motivo_rechazo(d, "8.8.8.8"))
            self.assertIn("sesion", sol.motivo_rechazo(os.path.join(d, "no-existe"), "192.168.1.20"))
            self.poner(d, ip="192.168.1.20")
            self.assertIn("ya hay una", sol.motivo_rechazo(d, "192.168.1.20"))      # una por equipo
            self.poner(d, ip="192.168.1.21")
            self.poner(d, ip="192.168.1.22")
            self.assertIn("demasiadas", sol.motivo_rechazo(d, "192.168.1.23"))      # tres en total

    def test_dos_rechazos_silencian_diez_minutos(self):
        with tempfile.TemporaryDirectory() as d:
            ip, t = "192.168.1.50", 1_000_000.0
            sol.anotar_rechazo(d, ip, t)
            self.assertFalse(sol.silenciado(d, ip, t + 1))
            sol.anotar_rechazo(d, ip, t + 2)
            self.assertTrue(sol.silenciado(d, ip, t + 3))
            self.assertIn("espera", sol.motivo_rechazo(d, ip, t + 3))
            self.assertFalse(sol.silenciado(d, "192.168.1.51", t + 3))
            self.assertFalse(sol.silenciado(d, ip, t + sol.SILENCIO + 5))


class Autorizar(unittest.TestCase):
    S = {"nombre": "DESKTOP-1", "ip": "192.168.1.20", "clave": CLAVE}

    def test_la_clave_solo_vale_desde_la_red_local(self):
        linea = sol.linea_autorizada(self.S, ahora=0)
        self.assertTrue(linea.startswith('from="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16" ssh-ed25519 ' + CLAVE[1]))
        self.assertIn("solicitud:DESKTOP-1:", linea)
        self.assertNotIn("\n", linea)

    def test_se_anade_una_vez_y_no_pisa_las_que_habia(self):
        with tempfile.TemporaryDirectory() as casa:
            os.makedirs(os.path.join(casa, ".ssh"))
            ruta = os.path.join(casa, ".ssh", "authorized_keys")
            open(ruta, "w").write("ssh-ed25519 " + OTRA[1] + " antigua")          # sin salto de línea final
            sol.autorizar(self.S, casa)
            sol.autorizar(self.S, casa)
            lineas = open(ruta, encoding="utf-8").read().splitlines()
            self.assertEqual(len(lineas), 2)
            self.assertEqual(lineas[0], "ssh-ed25519 " + OTRA[1] + " antigua")
            self.assertIn(CLAVE[1], lineas[1])


class Recibir(unittest.TestCase):
    def correr(self, d, linea, ip="192.168.1.20", local=True):
        hostkey = os.path.join(d, "host.pub")
        with open(hostkey, "w") as f:
            f.write(" ".join(HOST) + " root@a01\n")
        cola = os.path.join(d, "cola")
        os.makedirs(cola, exist_ok=True)
        entrada = mock.Mock()
        entrada.buffer = io.BytesIO(linea if isinstance(linea, bytes) else linea.encode())
        salida = io.StringIO()
        with mock.patch.object(sol, "HOSTKEY", hostkey), mock.patch.object(sol, "carpeta_cola", lambda: cola), \
                mock.patch.object(sol, "modo_local", lambda: local), mock.patch.object(sol, "clave_valida_de_verdad", lambda c: True), \
                mock.patch.dict(os.environ, {"REMOTE_ADDR": ip}), mock.patch("sys.stdin", entrada), mock.patch("sys.stdout", salida), \
                mock.patch("signal.alarm", lambda *_: None, create=True):
            sol.recibir()
        return salida.getvalue(), cola

    def test_solicitud_buena_queda_en_cola_con_el_mismo_codigo_en_los_dos_lados(self):
        with tempfile.TemporaryDirectory() as d:
            resp, cola = self.correr(d, sol.linea_solicitud("DESKTOP-1", CLAVE))
            r = sol.leer_respuesta(resp)
            self.assertEqual(r[0], "PENDIENTE")
            p = sol.pendientes(cola)
            self.assertEqual(len(p), 1)
            self.assertEqual(p[0]["ip"], "192.168.1.20")                       # la dirección la pone el sistema
            self.assertEqual(p[0]["codigo"], sol.codigo(CLAVE, r[3], r[1]))     # lo que calcula quien pide
            self.assertEqual(os.stat(p[0]["ruta"]).st_mode & 0o077, 0) if os.name != "nt" else None

    def test_rechazos(self):
        with tempfile.TemporaryDirectory() as d:
            buena = sol.linea_solicitud("X", CLAVE)
            self.assertIn("RECHAZADA", self.correr(d, buena, local=False)[0])          # SSH apagado o público
            self.assertIn("RECHAZADA", self.correr(d, buena, ip="8.8.8.8")[0])
            self.assertIn("mal formada", self.correr(d, "GET / HTTP/1.1\n")[0])
            self.assertIn("mal formada", self.correr(d, b"A" * 5000 + b"\n")[0])
            self.assertIn("mal formada", self.correr(d, buena.strip())[0])              # sin fin de línea
            self.assertEqual(sol.pendientes(os.path.join(d, "cola")), [])
            self.assertIn("PENDIENTE", self.correr(d, buena)[0])
            self.assertIn("ya hay una", self.correr(d, buena)[0])


class Cableado(unittest.TestCase):
    def test_solo_existe_en_modo_local_y_se_quita_al_apagar(self):
        t = leer("config/bin/leksso-acceso-remoto")
        self.assertIn("tcp dport 22222", t)
        self.assertRegex(t, r'SOLICITUD=.ip saddr \{ 10\.0\.0\.0/8, 172\.16\.0\.0/12, 192\.168\.0\.0/16 \}')
        on = t[t.index("  on)"):t.index("  off)")]
        self.assertRegex(on, r'if \[ "\$MODO" = local \]; then\s+nft add rule inet leksso entrada \$SOLICITUD')
        self.assertLess(on.index("quitar_solicitudes"), on.index("poner_solicitudes"))     # al pasar a público se quita
        self.assertIn("quitar_solicitudes", t[t.index("  off)"):])
        self.assertIn('comment "leksso-acceso-remoto solicitud"', t)                       # quitar_regla la borra también

    def test_el_servicio_corre_sin_privilegios_y_encerrado(self):
        t = leer("config/bin/leksso-acceso-remoto")
        for x in ("User=$u", "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=read-only", "Accept=yes",
                  "MaxConnectionsPerSource=2", "RuntimeMaxSec=20"):
            self.assertIn(x, t)

    def test_instalado_vigilado_y_flotante(self):
        self.assertIn('scripts/leksso-solicitud.py" /usr/local/bin/leksso-solicitud', leer("scripts/provision-base.sh"))
        sway = leer("config/sway/config")
        self.assertIn("exec leksso-solicitud vigilar", sway)
        self.assertIn('app_id="leksso-solicitud"] floating enable', sway)
        self.assertIn("|solicitud|", leer("config/sway/zonas.sh"))
        self.assertIn("Esperar una solicitud", leer("config/bin/leksso-ajustes"))

    def test_la_ventana_no_permite_con_intro_y_tiene_cerrar(self):
        t = leer("scripts/leksso-solicitud.py")
        self.assertIn("self.no.setDefault(True)", t)
        self.assertIn("si.setAutoDefault(False)", t)
        self.assertIn('setObjectName("cerrar")', t)
        self.assertNotIn("shell=True", t)


if __name__ == "__main__":
    unittest.main()
