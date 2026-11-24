#!/usr/bin/env python3
"""Volver a la versión anterior (leksso-actualizar volver): aparta lo que añadió la versión nueva, funciona sin red, tiene su
entrada en el menú de arranque y su botón en Configuración. Uso: python3 scripts/test_volver.py"""
import importlib.machinery
import importlib.util
import os
import stat
import subprocess
import tempfile
import time
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
_l = importlib.machinery.SourceFileLoader("leksso_actualizar", os.path.join(AQUI, "leksso-actualizar.py"))
act = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_actualizar", _l))
_l.exec_module(act)


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


def poner(ruta, antiguedad=0, texto="x"):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    t = time.time() - antiguedad
    os.utime(ruta, (t, t))


class Apartar(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.zonas = [self.t + "/bin/leksso-*", self.t + "/lib/leksso-ia/*", self.t + "/sbin/caja"]
        self.resp = self.t + "/respaldo/1"

    def test_aparta_lo_que_la_instalacion_nueva_no_ha_escrito_y_deja_lo_demas(self):
        marca = time.time() - 2
        poner(self.t + "/bin/leksso-viejo", antiguedad=3600)              # lo añadió la versión de la que se vuelve
        poner(self.t + "/bin/leksso-vigente", antiguedad=0)               # lo ha reescrito la versión a la que se vuelve
        poner(self.t + "/lib/leksso-ia/nuevo.py", antiguedad=7200)
        poner(self.t + "/sbin/caja", antiguedad=7200)
        poner(self.t + "/bin/otra-cosa", antiguedad=7200)                 # fuera de las zonas: no se toca
        apartados, destino = act.limpiar_sobrantes(marca, zonas=self.zonas, respaldo=self.resp)
        self.assertEqual(sorted(apartados), sorted([self.t + "/bin/leksso-viejo", self.t + "/lib/leksso-ia/nuevo.py", self.t + "/sbin/caja"]))
        self.assertFalse(os.path.exists(self.t + "/bin/leksso-viejo"))
        self.assertTrue(os.path.exists(self.t + "/bin/leksso-vigente"))
        self.assertTrue(os.path.exists(self.t + "/bin/otra-cosa"))
        # nada se borra: está en el respaldo con su ruta original
        self.assertEqual(open(destino + self.t + "/bin/leksso-viejo").read(), "x")
        self.assertTrue(os.path.exists(destino + self.t + "/lib/leksso-ia/nuevo.py"))

    def test_no_toca_carpetas(self):
        os.makedirs(self.t + "/lib/leksso-ia/__pycache__")
        poner(self.t + "/lib/leksso-ia/__pycache__/a.pyc", antiguedad=9999)
        apartados, _ = act.limpiar_sobrantes(time.time(), zonas=self.zonas, respaldo=self.resp)
        self.assertEqual(apartados, [])
        self.assertTrue(os.path.isdir(self.t + "/lib/leksso-ia/__pycache__"))

    def test_sin_nada_que_apartar_no_crea_respaldo(self):
        poner(self.t + "/bin/leksso-ok", antiguedad=0)
        apartados, destino = act.limpiar_sobrantes(time.time() - 2, zonas=self.zonas, respaldo=self.resp)
        self.assertEqual(apartados, [])
        self.assertFalse(os.path.exists(destino))

    def test_las_zonas_no_incluyen_lo_del_usuario_ni_los_ajustes(self):
        for z in act.ARCHIVOS_DE_LEKSSO:
            self.assertFalse(z.startswith("/etc/leksso"), z)             # ajustes, permisos de los asistentes, claves
            self.assertFalse(z.startswith("/var/lib/leksso"), z)
            self.assertFalse(z.startswith("/etc/sudoers"), z)
            self.assertFalse(z.startswith("/home"), z)
            self.assertTrue(z.startswith(("/usr/local/", "/usr/share/leksso", "/etc/systemd/", "/etc/udev/rules.d/70-leksso",
                                          "/etc/apt/apt.conf.d/99leksso", "/etc/fonts/conf.d/65-leksso", "/etc/grub.d/42_leksso")), z)


class FlujoDeVolver(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.anterior = self.t + "/version-anterior"
        poner(self.anterior, texto="0.1.52\n")
        self.llamadas = []

    def correr(self, red=True, apartados=(), update_grub=True, arranque=False):
        ordenes = []

        def sub(cmd, **kw):
            ordenes.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        existe = os.path.exists
        with mock.patch.object(act, "ANTERIOR", self.anterior), \
                mock.patch.object(act, "raiz_o_salir", lambda: None), mock.patch.object(act, "bloquear", lambda: None), \
                mock.patch.object(act, "usuario_real", lambda a=False: "leks"), \
                mock.patch.object(act, "preparar_clon", lambda tolerar_sin_red=False: self.llamadas.append(("clon", tolerar_sin_red))), \
                mock.patch.object(act, "verificar", lambda tag: (self.llamadas.append(("verificar", tag)) or ("a" * 40, "huella"))), \
                mock.patch.object(act, "version_actual", lambda: "0.1.53"), \
                mock.patch.object(act, "instalar_version", lambda *a: self.llamadas.append(("instalar", a[0]))), \
                mock.patch.object(act, "limpiar_sobrantes", lambda marca: (list(apartados), "/respaldo")), \
                mock.patch("subprocess.run", sub), \
                mock.patch("os.path.exists", lambda p: update_grub if p == "/usr/sbin/update-grub" else existe(p)):
            rc = act.volver(arranque=arranque)
        return rc, ordenes

    def test_vuelve_con_la_copia_local_aunque_no_haya_red_y_verifica_la_firma(self):
        rc, _ = self.correr()
        self.assertEqual(rc, 0)
        self.assertEqual(self.llamadas[0], ("clon", True))                 # tolera la falta de red
        self.assertEqual(self.llamadas[1], ("verificar", "v0.1.52"))       # y la firma de la versión anterior se comprueba igual
        self.assertEqual(self.llamadas[2], ("instalar", "v0.1.52"))

    def test_tras_volver_no_queda_una_versión_anterior_que_alterne(self):
        self.correr()
        self.assertFalse(os.path.exists(self.anterior))                   # para ir hacia delante, «Actualizar ahora»

    def test_si_se_apartó_algo_recarga_systemd_y_si_era_de_grub_actualiza_el_menu(self):
        _, ordenes = self.correr(apartados=["/etc/systemd/system/leksso-nuevo.service", "/etc/grub.d/42_leksso_volver"])
        self.assertIn(["systemctl", "daemon-reload"], ordenes)
        self.assertIn(["update-grub"], ordenes)

    def test_sin_update_grub_no_lo_llama(self):
        _, ordenes = self.correr(update_grub=False, apartados=["/etc/grub.d/42_leksso_volver"])
        self.assertNotIn(["update-grub"], ordenes)

    def test_si_la_instalacion_falla_no_se_aparta_nada(self):
        with mock.patch.object(act, "ANTERIOR", self.anterior), mock.patch.object(act, "raiz_o_salir", lambda: None), \
                mock.patch.object(act, "bloquear", lambda: None), mock.patch.object(act, "usuario_real", lambda a=False: "leks"), \
                mock.patch.object(act, "preparar_clon", lambda tolerar_sin_red=False: None), \
                mock.patch.object(act, "verificar", lambda tag: ("a" * 40, "h")), mock.patch.object(act, "version_actual", lambda: "0.1.53"), \
                mock.patch.object(act, "instalar_version", lambda *a: (_ for _ in ()).throw(SystemExit("falló"))), \
                mock.patch.object(act, "limpiar_sobrantes", lambda marca: self.fail("no debe apartar nada si la instalación falló")):
            with self.assertRaises(SystemExit):
                act.volver()
        self.assertTrue(os.path.exists(self.anterior))                    # y se puede reintentar

    def test_sin_version_anterior_guardada_se_niega(self):
        os.remove(self.anterior)
        with self.assertRaises(SystemExit) as e:
            self.correr()
        self.assertIn("No hay una versión anterior", str(e.exception))

    def test_version_anterior_no_valida_se_niega(self):
        poner(self.anterior, texto="../../etc\n")
        with self.assertRaises(SystemExit):
            self.correr()


class SinRed(unittest.TestCase):
    def test_preparar_clon_tolera_o_no_segun_se_pida(self):
        t = tempfile.mkdtemp()
        os.makedirs(t + "/.git")

        def git_falso(*args, cwd=None, entrada=None):
            return subprocess.CompletedProcess(args, 1 if args[0] == "fetch" else 0, "", "sin red")
        with mock.patch.object(act, "CLON", t), mock.patch.object(act, "git", git_falso):
            act.preparar_clon(tolerar_sin_red=True)                       # no sale
            with self.assertRaises(SystemExit):
                act.preparar_clon()                                       # una actualización normal sí exige red


class AlArrancar(unittest.TestCase):
    def test_usuario_sin_sudo_solo_en_arranque(self):
        import types
        pw = lambda n, uid, sh="/bin/bash": types.SimpleNamespace(pw_name=n, pw_uid=uid, pw_shell=sh)
        todos = [pw("root", 0), pw("daemon", 1, "/usr/sbin/nologin"), pw("leks", 1000), pw("otro", 1001), pw("nobody", 65534, "/usr/sbin/nologin")]
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch("pwd.getpwall", lambda: todos):
            os.environ.pop("SUDO_USER", None)
            self.assertEqual(act.usuario_real(arranque=True), "leks")
            with self.assertRaises(SystemExit):
                act.usuario_real(arranque=False)
        with mock.patch.dict(os.environ, {"SUDO_USER": "ana"}):
            self.assertEqual(act.usuario_real(arranque=True), "ana")      # si hay sudo, manda quien lo usa


GRUB_10LINUX = r'''#!/bin/sh
cat <<'EOF'
menuentry 'Debian GNU/Linux' --class debian --class gnu-linux --class gnu --class os $menuentry_id_option 'gnulinux-simple-1234-abcd' {
	load_video
	insmod gzio
	insmod part_gpt
	search --no-floppy --fs-uuid --set=root 1234-abcd
	echo	'Cargando Linux 6.12.74-amd64 ...'
	linux	/boot/vmlinuz-6.12.74-amd64 root=UUID=1234-abcd ro  quiet splash
	echo	'Cargando imagen de memoria inicial ...'
	initrd	/boot/initrd.img-6.12.74-amd64
}
submenu 'Opciones avanzadas para Debian GNU/Linux' $menuentry_id_option 'gnulinux-advanced-1234-abcd' {
	menuentry 'Debian GNU/Linux, con Linux 6.12.74-amd64' --class debian $menuentry_id_option 'gnulinux-6.12.74-amd64-advanced-1234-abcd' {
		linux	/boot/vmlinuz-6.12.74-amd64 root=UUID=1234-abcd ro  quiet
	}
}
EOF
'''


@unittest.skipIf(os.name == "nt", "usa sh y awk")
class EntradaDeArranque(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.gen = self.t + "/10_linux"
        with open(self.gen, "w", encoding="utf-8") as f:
            f.write(GRUB_10LINUX)
        os.chmod(self.gen, 0o755)
        self.ant = self.t + "/version-anterior"
        poner(self.ant, texto="0.1.52\n")
        self.script = os.path.join(RAIZ, "config", "grub", "42_leksso_volver")

    def generar(self, gen=None, ant=None):
        env = dict(os.environ, LEKSSO_GRUB_10LINUX=gen or self.gen, LEKSSO_VERSION_ANTERIOR=ant or self.ant)
        return subprocess.run(["sh", self.script], capture_output=True, text=True, env=env)

    def test_una_entrada_con_la_orden_de_volver_y_nada_mas(self):
        r = self.generar()
        self.assertEqual(r.returncode, 0, r.stderr)
        s = r.stdout
        self.assertEqual(s.count("menuentry "), 1)                        # solo la primera, no el submenú de opciones avanzadas
        self.assertNotIn("submenu", s)
        self.assertIn("menuentry 'LeksSO: volver a la versión anterior' --class debian", s)
        self.assertIn("$menuentry_id_option 'leksso-volver' {", s)        # identificador propio: los de GRUB no pueden repetirse
        self.assertNotIn("gnulinux-simple", s)
        self.assertIn("leksso.volver=1", s)
        linux = [l for l in s.splitlines() if l.strip().startswith("linux")][0]
        self.assertTrue(linux.rstrip().endswith("leksso.volver=1"))
        self.assertNotIn("quiet", linux)
        self.assertNotIn("splash", linux)
        self.assertIn("root=UUID=1234-abcd", linux)                       # el mismo kernel y el mismo disco de siempre
        self.assertIn("initrd	/boot/initrd.img-6.12.74-amd64", s)
        self.assertEqual(s.count("{"), s.count("}"))                      # llaves cuadradas: grub.cfg seguiría siendo válido
        self.assertTrue(s.rstrip().endswith("}"))

    def test_sin_version_anterior_no_imprime_nada(self):
        r = self.generar(ant=self.t + "/no-existe")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_sin_generador_no_imprime_nada(self):
        r = self.generar(gen=self.t + "/no-hay")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_si_el_generador_cambia_de_forma_no_inventa_nada(self):
        with open(self.gen, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho 'menuentry_rara sin comillas {'\necho '}'\n")
        r = self.generar()
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_si_el_generador_falla_no_rompe_el_menu(self):
        with open(self.gen, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 1\n")
        r = self.generar()
        self.assertEqual((r.returncode, r.stdout), (0, ""))


class Cableado(unittest.TestCase):
    def test_la_unidad_solo_actua_con_la_orden_del_menu_y_no_frena_arranques_normales(self):
        u = leer("config/systemd/leksso-volver-arranque.service")
        self.assertIn("ConditionKernelCommandLine=leksso.volver=1", u)
        self.assertIn("ExecStart=/usr/local/bin/leksso-actualizar volver --arranque", u)
        self.assertIn("ExecStartPost=/usr/bin/systemctl --no-block reboot", u)  # solo se reinicia si volver terminó bien
        self.assertNotIn("network-online", u)                             # no puede retrasar los arranques normales
        self.assertIn("Before=getty@tty1.service", u)

    def test_la_provision_instala_la_unidad_y_la_entrada_y_actualiza_grub_con_cuidado(self):
        p = leer("scripts/provision-base.sh")
        self.assertIn('leksso-volver-arranque.service" /etc/systemd/system/', p)
        self.assertIn("systemctl enable leksso-volver-arranque.service", p)
        self.assertIn('config/grub/42_leksso_volver" /etc/grub.d/42_leksso_volver', p)
        i = p.index("42_leksso_volver")
        self.assertIn("command -v update-grub", p[i - 200:i + 300])       # solo si el equipo usa GRUB
        self.assertIn("||", p[i:i + 400])                                 # y un fallo de update-grub no detiene la instalación

    def test_la_ventana_dice_a_que_version_se_vuelve_y_explica_lo_del_arranque(self):
        w = leer("config/bin/leksso-actualizaciones")
        self.assertIn('f"Volver a {nombre', w)
        self.assertIn("LeksSO: volver a la versión anterior", w)
        self.assertIn("sin necesitar red", w)

    def test_el_script_de_grub_es_ejecutable_en_git(self):
        r = subprocess.run(["git", "-C", RAIZ, "ls-files", "-s", "config/grub/42_leksso_volver"], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            self.skipTest("todavía no está en git")
        self.assertTrue(r.stdout.startswith("100755"), r.stdout)


if __name__ == "__main__":
    unittest.main()
