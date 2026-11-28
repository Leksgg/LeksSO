#!/usr/bin/env python3
"""Comprobaciones estáticas de provision-base.sh, que corre con `set -u` y se reejecuta en cada actualización: una variable
usada antes de definirse la rompería entera (pasó con RAIZ). Uso: python3 scripts/test_provision.py"""
import configparser
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

    def test_labwc_ya_no_se_instala_ni_se_configura_y_se_retira_si_estaba(self):
        codigo = [l for l in self.lineas if not l.strip().startswith("#")]
        array = [l for l in codigo if l.startswith("ESCRITORIO=")][0]
        self.assertNotIn("labwc", array.replace("(", " ").replace(")", " ").split())
        self.assertFalse([l for l in codigo if "labwc" in l and "purge" not in l and "dpkg -s" not in l], "solo puede quedar la retirada")
        self.assertTrue([l for l in codigo if "apt-get purge -y labwc" in l])

    def test_el_portal_ofrece_selector_de_archivos_con_el_tema_de_leksso(self):
        array = [l for l in self.lineas if l.startswith("ESCRITORIO=")][0].split("#")[0].replace("(", " ").replace(")", " ").split()
        self.assertIn("xdg-desktop-portal-wlr", array)           # compartir pantalla y capturas
        self.assertIn("xdg-desktop-portal-lxqt", array)          # abrir y guardar archivos
        self.assertIn("/etc/xdg-desktop-portal/sway-portals.conf", "\n".join(self.lineas))
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        portales = configparser.ConfigParser()
        portales.read(os.path.join(raiz, "config", "xdg-desktop-portal", "sway-portals.conf"), encoding="utf-8")
        self.assertEqual(portales["preferred"]["org.freedesktop.impl.portal.filechooser"], "lxqt")
        self.assertTrue(portales["preferred"]["default"].startswith("wlr"))
        sway = open(os.path.join(raiz, "config", "sway", "config"), encoding="utf-8").read()
        self.assertRegex(sway, r"dbus-update-activation-environment [^\n]*QT_QPA_PLATFORMTHEME=qt6ct")   # el selector es Qt
        # Debian arranca ese selector con el tema de LXQt: nuestro servicio, en /usr/local/share, lo cambia por el de LeksSO
        self.assertIn("/usr/local/share/dbus-1/services/", "\n".join(self.lineas))
        servicio = open(os.path.join(raiz, "config", "xdg-desktop-portal", "org.freedesktop.impl.portal.desktop.lxqt.service"), encoding="utf-8").read()
        self.assertIn("Exec=/usr/bin/env QT_QPA_PLATFORMTHEME=qt6ct /usr/libexec/xdg-desktop-portal-lxqt", servicio)
        self.assertIn("libfm-qt-l10n", array)                    # el selector en español

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

    def test_el_video_tiene_controladores_de_la_grafica(self):
        # La base se instala sin «recomendados»: los controladores de decodificación hay que pedirlos por su nombre.
        grafica = next(l for l in self.lineas if l.startswith("GRAFICA=("))
        for paquete in ("mesa-va-drivers", "intel-media-va-driver", "i965-va-driver"):
            self.assertIn(paquete, grafica)
        texto = "\n".join(self.lineas)
        for esperado in ("nvidia-vaapi-driver", "intel-media-va-driver-non-free", "51-leksso-hdmi-pcm.conf", "rtkit"):
            self.assertIn(esperado, texto, esperado)


if __name__ == "__main__":
    unittest.main()
