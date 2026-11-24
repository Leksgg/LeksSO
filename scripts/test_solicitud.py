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
SECRETO = "00112233445566778899aabbccddeeff"
HUELLA = "0" * 64


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


class Protocolo(unittest.TestCase):
    def test_palabras_del_codigo(self):
        self.assertEqual(len(sol.PALABRAS), len(set(sol.PALABRAS)))
        self.assertGreaterEqual(len(sol.PALABRAS), 128)     # con cuatro, al menos 2 ** 28 combinaciones
        for p in sol.PALABRAS:
            self.assertRegex(p, r"^[a-z]{2,7}$")            # sin tildes ni eñes: se leen y se comparan fácil

    def test_el_codigo_es_de_cuatro_palabras_y_depende_de_las_cuatro_cosas(self):
        c = sol.codigo(CLAVE, HOST, "00112233aabbccdd", SECRETO)
        self.assertRegex(c, r"^[a-z]+(-[a-z]+){3}$")
        self.assertEqual(c, sol.codigo(CLAVE, HOST, "00112233aabbccdd", SECRETO))
        self.assertGreaterEqual(len(sol.PALABRAS) ** sol.N_PALABRAS, 2 ** 28)
        distintos = {sol.codigo(CLAVE, HOST, f"{i:016x}", SECRETO) for i in range(500)}
        self.assertGreater(len(distintos), 495)             # el número del equipo que recibe cambia el código
        distintos = {sol.codigo(CLAVE, HOST, "0" * 16, f"{i:032x}") for i in range(500)}
        self.assertGreater(len(distintos), 495)             # y el de quien pide también
        base = sol.codigo(CLAVE, HOST, "0" * 16, SECRETO)
        self.assertNotEqual(base, sol.codigo(OTRA, HOST, "0" * 16, SECRETO))
        self.assertNotEqual(base, sol.codigo(CLAVE, OTRA, "0" * 16, SECRETO))

    def test_las_palabras_salen_sin_sesgo(self):
        """Con un solo byte y una lista de 137 palabras, las 119 primeras saldrían el doble de veces que las 18 últimas."""
        veces = {}
        for i in range(100_000):
            primera = sol.codigo(CLAVE, HOST, f"{i:016x}", SECRETO).split("-")[0]
            veces[primera] = veces.get(primera, 0) + 1
        self.assertEqual(len(veces), len(sol.PALABRAS))                       # salen todas
        self.assertLess(max(veces.values()) / min(veces.values()), 1.4)       # con el sesgo antiguo la razón era 2

    def test_el_compromiso_es_una_huella_sha256_del_numero(self):
        h = sol.compromiso(SECRETO)
        self.assertRegex(h, r"^[0-9a-f]{64}$")
        self.assertEqual(h, sol.compromiso(SECRETO))
        self.assertNotEqual(h, sol.compromiso(SECRETO[:-1] + "0"))

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
        linea = sol.linea_solicitud("DESKTOP-1", CLAVE, HUELLA)
        self.assertEqual(sol.leer_solicitud(linea), ("DESKTOP-1", CLAVE, HUELLA))
        k = " ".join(CLAVE)
        for mala in ("", "HOLA", f"LEKSSO-SOLICITUD 2 x {k}",                       # sin huella
                     f"LEKSSO-SOLICITUD 1 DESKTOP-1 {k} {HUELLA}",                    # versión antigua
                     f"LEKSSO-SOLICITUD 2 a b {k} {HUELLA}", f'LEKSSO-SOLICITUD 2 a"b {k} {HUELLA}',
                     f"LEKSSO-SOLICITUD 2 x ssh-ed25519 mal {HUELLA}",
                     f"LEKSSO-SOLICITUD 2 x {k} " + "z" * 64,                          # la huella no es hexadecimal
                     f"LEKSSO-SOLICITUD 2 x {k} " + "0" * 63,                          # corta
                     f"LEKSSO-SOLICITUD 2 x {k} {HUELLA} sobra"):
            self.assertIsNone(sol.leer_solicitud(mala), mala)

    def test_ida_y_vuelta_de_la_revelacion(self):
        self.assertEqual(sol.leer_revelacion(sol.linea_revelacion(SECRETO)), SECRETO)
        for mala in ("", "LEKSSO-REVELAR", f"LEKSSO-REVELAR 1 {SECRETO}", f"LEKSSO-REVELAR 2 {SECRETO[:-1]}",
                     f"LEKSSO-REVELAR 2 {SECRETO}0", "LEKSSO-REVELAR 2 " + "Z" * 32, f"LEKSSO-REVELAR 2 {SECRETO} x",
                     f"LEKSSO-SOLICITUD 2 x {' '.join(CLAVE)} {HUELLA}"):
            self.assertIsNone(sol.leer_revelacion(mala), mala)

    def test_respuesta(self):
        r = sol.leer_respuesta(f"PENDIENTE 2 00112233aabbccdd a01 {HOST[0]} {HOST[1]}\n")
        self.assertEqual(r, ("PENDIENTE", "00112233aabbccdd", "a01", HOST))
        self.assertEqual(sol.leer_respuesta("RECHAZADA ya hay una\n"), ("RECHAZADA", "ya hay una"))
        for mala in ("", "PENDIENTE 2 corto a01 x y", f"PENDIENTE 2 00112233aabbccdd -oProxyCommand=x {HOST[0]} {HOST[1]}",
                     f"PENDIENTE 2 00112233aabbccdd root;id {HOST[0]} {HOST[1]}",
                     f"PENDIENTE 1 00112233aabbccdd a01 {HOST[0]} {HOST[1]}"):             # versión antigua: no vale
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
            resp, cola = self.correr(d, sol.linea_solicitud("DESKTOP-1", CLAVE, sol.compromiso(SECRETO)))
            r = sol.leer_respuesta(resp)
            self.assertEqual(r[0], "PENDIENTE")
            self.assertEqual(sol.pendientes(cola), [])                          # aún no se ha revelado: no se enseña nada
            self.assertEqual(self.correr(d, sol.linea_revelacion(SECRETO))[0].strip(), "OK")
            p = sol.pendientes(cola)
            self.assertEqual(len(p), 1)
            self.assertEqual(p[0]["ip"], "192.168.1.20")                       # la dirección la pone el sistema
            self.assertEqual(p[0]["codigo"], sol.codigo(CLAVE, r[3], r[1], SECRETO))     # lo que calcula quien pide
            self.assertEqual(os.stat(p[0]["ruta"]).st_mode & 0o077, 0) if os.name != "nt" else None

    def test_rechazos(self):
        with tempfile.TemporaryDirectory() as d:
            buena = sol.linea_solicitud("X", CLAVE, sol.compromiso(SECRETO))
            self.assertIn("RECHAZADA", self.correr(d, buena, local=False)[0])          # SSH apagado o público
            self.assertIn("RECHAZADA", self.correr(d, buena, ip="8.8.8.8")[0])
            self.assertIn("mal formada", self.correr(d, "GET / HTTP/1.1\n")[0])
            self.assertIn("mal formada", self.correr(d, b"A" * 5000 + b"\n")[0])
            self.assertIn("mal formada", self.correr(d, buena.strip())[0])              # sin fin de línea
            self.assertEqual(sol.pendientes(os.path.join(d, "cola")), [])
            self.assertIn("PENDIENTE", self.correr(d, buena)[0])
            self.assertIn("ya hay una", self.correr(d, buena)[0])


class CompromisoYRevelacion(unittest.TestCase):
    correr = Recibir.correr
    """Hallazgo 4 de la revisión de la 0.1.52: el código de dos palabras se podía falsificar desde la red local."""

    def pedir_y_revelar(self, d, secreto=SECRETO, ip="192.168.1.20"):
        resp, cola = self.correr(d, sol.linea_solicitud("DESKTOP-1", CLAVE, sol.compromiso(secreto)), ip=ip)
        return sol.leer_respuesta(resp), cola

    def test_la_revelacion_con_otro_numero_se_rechaza(self):
        with tempfile.TemporaryDirectory() as d:
            _, cola = self.pedir_y_revelar(d)
            otro = "ff" * 16
            self.assertIn("no hay una solicitud con ese compromiso", self.correr(d, sol.linea_revelacion(otro))[0])
            self.assertEqual(sol.pendientes(cola), [])                          # nada se enseña

    def test_revelar_sin_haber_pedido_se_rechaza(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("RECHAZADA", self.correr(d, sol.linea_revelacion(SECRETO))[0])

    def test_no_se_puede_revelar_dos_veces(self):
        with tempfile.TemporaryDirectory() as d:
            _, cola = self.pedir_y_revelar(d)
            self.assertEqual(self.correr(d, sol.linea_revelacion(SECRETO))[0].strip(), "OK")
            antes = sol.pendientes(cola)[0]["codigo"]
            self.assertIn("ya estaba revelada", self.correr(d, sol.linea_revelacion(SECRETO))[0])
            self.assertEqual(sol.pendientes(cola)[0]["codigo"], antes)

    def test_solo_revela_la_misma_direccion_que_pidio(self):
        with tempfile.TemporaryDirectory() as d:
            _, cola = self.pedir_y_revelar(d, ip="192.168.1.20")
            self.assertIn("no es de esta direccion", self.correr(d, sol.linea_revelacion(SECRETO), ip="192.168.1.99")[0])
            self.assertEqual(sol.pendientes(cola), [])
            self.assertIn("RECHAZADA", self.correr(d, sol.linea_revelacion(SECRETO), ip="8.8.8.8")[0])   # ni de fuera de la red
            self.assertEqual(self.correr(d, sol.linea_revelacion(SECRETO), ip="192.168.1.20")[0].strip(), "OK")

    def test_sin_revelar_a_tiempo_se_descarta(self):
        with tempfile.TemporaryDirectory() as d:
            _, cola = self.pedir_y_revelar(d)
            hora = json.load(open(os.path.join(cola, os.listdir(cola)[0])))["hora"]
            self.assertEqual(len(sol.pendientes(cola, hora + 5, solo_listas=False)), 1)               # esperando
            self.assertEqual(sol.pendientes(cola, hora + sol.ESPERA_REVELAR + 1, solo_listas=False), [])
            self.assertEqual(os.listdir(cola), [])                                                     # y se borró
            self.assertIn("RECHAZADA", self.correr(d, sol.linea_revelacion(SECRETO))[0])

    def test_una_solicitud_esperando_ocupa_su_sitio(self):
        with tempfile.TemporaryDirectory() as d:
            self.pedir_y_revelar(d)
            otra = sol.linea_solicitud("X", CLAVE, sol.compromiso("11" * 16))
            self.assertIn("ya hay una", self.correr(d, otra)[0])                # no se puede inundar con solicitudes sin revelar

    def test_una_version_antigua_recibe_un_mensaje_claro(self):
        with tempfile.TemporaryDirectory() as d:
            vieja = f"LEKSSO-SOLICITUD 1 DESKTOP-1 {' '.join(CLAVE)}\n"
            self.assertIn("version antigua", self.correr(d, vieja)[0])

    def test_el_ataque_del_intermediario_ya_no_se_puede_buscar(self):
        """El atacante fija su número ANTES de conocer el de quien pide (que está escondido tras la huella). Aunque pruebe
        decenas de miles de candidatos contra el código que ve el equipo que recibe, ninguno cuadra: no sabe qué número
        usará el otro lado, y con cuatro palabras acertar a ciegas es una de 352 millones."""
        receptor_codigo = sol.codigo(OTRA, HOST, "aa" * 8, "bb" * 16)       # lo que enseña el equipo que recibe (clave del atacante)
        aciertos = sum(1 for i in range(50_000) if sol.codigo(CLAVE, HOST, f"{i:016x}", SECRETO) == receptor_codigo)
        self.assertEqual(aciertos, 0)

    def test_el_ataque_antiguo_si_funcionaba_con_el_numero_a_la_vista(self):
        """Control de la prueba anterior: si el atacante CONOCIERA el número de quien pide (como pasaba antes, porque ahí
        no había nada que esconder), le bastan unas decenas de miles de intentos para igualar dos palabras."""
        objetivo = sol.codigo(OTRA, HOST, "aa" * 8, "bb" * 16).split("-")[:2]
        encontrado = any(sol.codigo(CLAVE, HOST, f"{i:016x}", SECRETO).split("-")[:2] == objetivo for i in range(300_000))
        self.assertTrue(encontrado)

    def test_quien_pide_manda_la_huella_primero_y_revela_despues(self):
        enviadas = []
        pendiente = f"PENDIENTE 2 00112233aabbccdd a01 {HOST[0]} {HOST[1]}\n"

        def falso(direccion, puerto, linea):
            enviadas.append(linea)
            return pendiente if len(enviadas) == 1 else "OK\n"
        salida = []
        with mock.patch.object(sol, "_hablar", falso), mock.patch.object(sol, "clave_propia", lambda r=None: ("/tmp/x.pub", CLAVE)):
            sol.pedir("192.168.1.30", nombre="PC", espera=0, salida=salida.append)
        self.assertEqual(len(enviadas), 2)
        _, _, huella = sol.leer_solicitud(enviadas[0])
        secreto = sol.leer_revelacion(enviadas[1])
        self.assertIsNotNone(secreto)
        self.assertEqual(sol.compromiso(secreto), huella)                    # lo revelado cuadra con lo prometido
        self.assertNotIn(secreto, enviadas[0])                               # y el número no viajó en la primera línea
        self.assertTrue(any("CÓDIGO: " + sol.codigo(CLAVE, HOST, "00112233aabbccdd", secreto) in x for x in salida))
        self.assertEqual(len(salida[1].split("-")), 4)

    def test_quien_pide_y_quien_recibe_se_entienden_y_ven_el_mismo_codigo(self):
        """De punta a punta, sin red: el cliente (pedir) habla con el servidor (recibir) con las mismas líneas que irían por el cable."""
        with tempfile.TemporaryDirectory() as d:
            cola = os.path.join(d, "cola")
            salida = []
            with mock.patch.object(sol, "_hablar", lambda direccion, puerto, linea: self.correr(d, linea)[0]), \
                    mock.patch.object(sol, "clave_propia", lambda r=None: ("/tmp/x.pub", CLAVE)):
                sol.pedir("192.168.1.30", nombre="PC", espera=0, salida=salida.append)
            visto_por_quien_pide = next(x.split("CÓDIGO: ")[1] for x in salida if x.startswith("CÓDIGO: "))
            listas = sol.pendientes(cola)
            self.assertEqual(len(listas), 1)
            self.assertEqual(listas[0]["codigo"], visto_por_quien_pide)          # lo que se enseña al permitir
            self.assertEqual(len(visto_por_quien_pide.split("-")), 4)

    def test_si_la_revelacion_falla_no_se_enseña_codigo(self):
        respuestas = iter([f"PENDIENTE 2 00112233aabbccdd a01 {HOST[0]} {HOST[1]}\n", "RECHAZADA no hay una solicitud con ese compromiso\n"])
        salida = []
        with mock.patch.object(sol, "_hablar", lambda *a: next(respuestas)), \
                mock.patch.object(sol, "clave_propia", lambda r=None: ("/tmp/x.pub", CLAVE)):
            rc = sol.pedir("192.168.1.30", espera=0, salida=salida.append)
        self.assertEqual(rc, 1)
        self.assertFalse(any("CÓDIGO" in x for x in salida))


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
