#!/usr/bin/env python3
"""Pruebas de leksso-tema: cambiar de tema reescribe los colores de la configuración del usuario, la ida y vuelta
deja los archivos idénticos y un tema que no existe no toca nada. Uso: python3 scripts/test_tema.py"""
import os
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "config", "ui"))
import leksso_ui  # noqa: E402

TEMA = os.path.join(RAIZ, "scripts", "leksso-tema.py")
_spec = importlib.util.spec_from_file_location("aplicar_tema", os.path.join(RAIZ, "scripts", "aplicar-tema.py"))
generador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generador)
COPIAS = {
    "waybar/style.css": ".config/waybar/style.css",
    "kitty/kitty.conf": ".config/kitty/kitty.conf", "sway/config": ".config/sway/config",
    "mako/config": ".config/mako/config", "fuzzel/fuzzel.ini": ".config/fuzzel/fuzzel.ini",
    "swaylock/config": ".config/swaylock/config", "qt6ct/colors/leksso.conf": ".config/qt6ct/colors/leksso.conf",
    "pcmanfm-qt/settings.conf": ".config/pcmanfm-qt/default/settings.conf",
}


class PruebasTema(unittest.TestCase):
    def setUp(self):
        self.casa = tempfile.mkdtemp()
        for origen, destino in COPIAS.items():
            d = os.path.join(self.casa, destino)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy(os.path.join(RAIZ, "config", origen), d)
        self.env = dict(os.environ, HOME=self.casa)

    def tearDown(self):
        shutil.rmtree(self.casa, ignore_errors=True)

    def tema(self, *a):
        return subprocess.run([sys.executable, TEMA, *a], env=self.env, capture_output=True, text=True)

    def contenido(self):
        out = {}
        for destino in COPIAS.values():
            out[destino] = open(os.path.join(self.casa, destino), "rb").read()
        return out

    def test_ida_y_vuelta_identica(self):
        antes = self.contenido()
        self.assertEqual(self.tema("aplicar", "pizarra").returncode, 0)
        self.assertNotEqual(antes, self.contenido())
        self.assertEqual(self.tema("actual").stdout.strip(), "pizarra")
        self.assertEqual(self.tema("aplicar", "marea").returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_no_quedan_colores_del_tema_anterior(self):
        self.tema("aplicar", "pizarra")
        viejo = set(leksso_ui.tokens("marea").values()) - set(leksso_ui.tokens("pizarra").values())
        for destino, datos in self.contenido().items():
            if destino.endswith("settings.conf"):
                continue  # solo lleva algunos colores
            texto = datos.decode("utf-8").lower()
            for c in ("021012", "00c4bf", "e3edef"):
                self.assertNotIn(c, texto, f"{destino} sigue con {c}")
        self.assertTrue(viejo)

    def test_tema_desconocido_no_toca_nada(self):
        antes = self.contenido()
        r = self.tema("aplicar", "noexiste")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_reaplicar_tras_copiar_la_base(self):
        self.tema("aplicar", "pizarra")
        for origen, destino in COPIAS.items():  # una actualización vuelve a copiar la base (Marea)
            shutil.copy(os.path.join(RAIZ, "config", origen), os.path.join(self.casa, destino))
        self.assertEqual(self.tema("reaplicar").returncode, 0)
        barra = open(os.path.join(self.casa, ".config", "waybar", "style.css"), encoding="utf-8").read().lower()
        self.assertIn(leksso_ui.tokens("pizarra")["bg"], barra)   # la base recién copiada vuelve a llevar Pizarra
        self.assertNotIn("021012", barra)
        self.tema("aplicar", "marea")
        base = {d: open(os.path.join(RAIZ, "config", o), "rb").read() for o, d in COPIAS.items()}
        self.assertEqual(base, self.contenido())

    def test_hay_nueve_temas(self):
        self.assertEqual(set(self.tema("listar").stdout.split()),
                         {"marea", "pizarra", "waves", "alba", "grisrosa", "blancorosa", "grafito", "purpura", "blancopurpura"})

    def test_grafito_y_purpuras_se_aplican_y_se_deshacen(self):
        """Grafito (el de serie), Púrpura (oscuro) y Blanco y púrpura (claro): pintan todo y se vuelve a Marea sin diferencias."""
        antes = self.contenido()
        for nombre, claro in (("grafito", False), ("purpura", False), ("blancopurpura", True)):
            self.assertEqual(self.tema("aplicar", nombre).returncode, 0)
            t = leksso_ui.tokens(nombre)
            texto = open(os.path.join(self.casa, ".config", "waybar", "style.css"), encoding="utf-8").read().lower()
            self.assertIn(t["bg"], texto)
            self.assertNotIn("021012", texto)
            self.assertNotIn("00c4bf", texto)                 # ni el turquesa de Marea
            kitty = open(os.path.join(self.casa, ".config", "kitty", "kitty.conf"), encoding="utf-8").read().lower()
            self.assertIn("background #" + t["bg"], kitty)
            self.assertEqual(leksso_ui.es_claro(nombre), claro)
        self.assertEqual(self.tema("aplicar", "marea").returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_la_instalacion_pone_grafito_a_quien_no_eligio(self):
        texto = open(os.path.join(RAIZ, "scripts", "provision-base.sh"), encoding="utf-8").read()
        self.assertIn('if [ ! -e "$HOME_USR/.config/leksso/tema" ]; then', texto)
        self.assertIn("echo grafito |", texto)
        self.assertNotIn("echo waves |", texto)

    def test_waves_ida_y_vuelta_identica(self):
        antes = self.contenido()
        self.assertEqual(self.tema("aplicar", "waves").returncode, 0)
        texto = open(os.path.join(self.casa, ".config", "waybar", "style.css"), encoding="utf-8").read().lower()
        self.assertIn(leksso_ui.tokens("waves")["bg"], texto)
        self.assertNotIn("021012", texto)
        self.assertEqual(self.tema("aplicar", "pizarra").returncode, 0)  # de un tema a otro sin pasar por Marea
        self.assertEqual(self.tema("aplicar", "marea").returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_temas_rosas_se_aplican_y_se_deshacen(self):
        """Gris y rosa (oscuro) y Blanco y rosa (claro): se pintan todos los archivos y se vuelve a Marea sin diferencias."""
        antes = self.contenido()
        for nombre, claro in (("grisrosa", False), ("blancorosa", True)):
            self.assertEqual(self.tema("aplicar", nombre).returncode, 0)
            t = leksso_ui.tokens(nombre)
            texto = open(os.path.join(self.casa, ".config", "waybar", "style.css"), encoding="utf-8").read().lower()
            self.assertIn(t["bg"], texto)
            self.assertNotIn("021012", texto)                 # no queda el fondo de Marea
            kitty = open(os.path.join(self.casa, ".config", "kitty", "kitty.conf"), encoding="utf-8").read().lower()
            self.assertIn("background #" + t["bg"], kitty)
            self.assertEqual(leksso_ui.es_claro(nombre), claro)
            if claro:
                self.assertIn("color15 #" + t["text"], kitty)
        self.assertEqual(self.tema("aplicar", "marea").returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_tema_claro_completo(self):
        antes = self.contenido()
        self.assertEqual(self.tema("aplicar", "alba").returncode, 0)
        t = leksso_ui.tokens("alba")
        kitty = open(os.path.join(self.casa, ".config", "kitty", "kitty.conf"), encoding="utf-8").read().lower()
        self.assertIn("color15 #" + t["text"], kitty)        # el blanco brillante no se queda invisible sobre fondo claro
        self.assertIn("background #" + t["bg"], kitty)
        iconos = os.path.join(self.casa, ".local", "share", "icons", "LeksSO")
        self.assertTrue(os.path.isdir(iconos))
        svgs = [os.path.join(r, f) for r, _, fs in os.walk(iconos) for f in fs if f.endswith(".svg")]
        self.assertTrue(svgs)
        todo = "".join(open(f, encoding="utf-8").read().lower() for f in svgs)
        self.assertNotIn("#021012", todo)                     # ningún icono conserva el fondo oscuro de Marea
        self.assertNotIn("#112123", todo)
        self.assertEqual(self.tema("aplicar", "marea").returncode, 0)
        self.assertFalse(os.path.isdir(iconos))               # con Marea valen los del sistema
        self.assertEqual(antes, self.contenido())
        self.assertIn("color15 #ffffff", open(os.path.join(self.casa, ".config", "kitty", "kitty.conf"), encoding="utf-8").read().lower())

    def test_no_queda_ningun_color_propio_del_tema_anterior(self):
        """Todos los papeles cambian (también el relleno de selección), no solo fondo, acento y texto."""
        for nombre in ("pizarra", "purpura"):
            self.assertEqual(self.tema("aplicar", nombre).returncode, 0)
            viejo = set(leksso_ui.tokens("marea").values()) - set(leksso_ui.tokens(nombre).values())
            for destino, datos in self.contenido().items():
                if destino.endswith("settings.conf"):
                    continue
                texto = datos.decode("utf-8").lower()
                for c in viejo:
                    self.assertNotIn(c, texto, f"{nombre}: {destino} sigue con {c} de Marea")
            self.assertEqual(self.tema("aplicar", "marea").returncode, 0)

    def test_pantalla_de_bloqueo_sigue_el_tema(self):
        swaylock = os.path.join(self.casa, ".config", "swaylock", "config")
        propia = os.path.join(self.casa, ".config", "leksso", "bloqueo.png")
        self.assertEqual(self.tema("aplicar", "grafito").returncode, 0)
        self.assertIn("image=" + propia, open(swaylock, encoding="utf-8").read())
        self.assertTrue(os.path.isfile(propia))
        self.assertEqual(self.tema("aplicar", "marea").returncode, 0)
        self.assertIn("image=/usr/share/leksso/bloqueo.png", open(swaylock, encoding="utf-8").read())

    def test_etiquetas_de_iconos_oscuras_en_tema_claro(self):
        """En un tema claro el texto de las etiquetas (sobre el color del tipo de archivo) pasa a ser el texto oscuro del tema."""
        self.assertEqual(self.tema("aplicar", "blancopurpura").returncode, 0)
        icono = os.path.join(self.casa, ".local", "share", "icons", "LeksSO", "scalable", "mimetypes", "text-x-javascript.svg")
        texto = open(icono, encoding="utf-8").read().lower()
        self.assertIn('font-size="11" fill="#' + leksso_ui.tokens("blancopurpura")["text"] + '">js<', texto)

    def test_nombre_de_tema_raro_vuelve_a_la_base(self):
        """~/.config/leksso/tema lo puede escribir cualquier programa del usuario: un nombre con rutas no se usa."""
        os.makedirs(os.path.join(self.casa, ".config", "leksso"))
        casa_real = os.environ.get("HOME")
        os.environ["HOME"] = self.casa
        try:
            for raro in ("../../etc/passwd", "marea/../x", "grafito.json", ""):
                open(os.path.join(self.casa, ".config", "leksso", "tema"), "w").write(raro + "\n")
                self.assertEqual(leksso_ui.tema_activo(), leksso_ui.BASE, raro)
        finally:
            if casa_real is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = casa_real

    def test_contraste_del_tema_claro(self):
        self.assertTrue(leksso_ui.es_claro("alba"))
        self.assertFalse(leksso_ui.es_claro("marea"))

    def test_estilo_de_ventanas_sigue_el_tema(self):
        os.makedirs(os.path.join(self.casa, ".config", "leksso"))
        open(os.path.join(self.casa, ".config", "leksso", "tema"), "w").write("pizarra\n")
        casa_real = os.environ.get("HOME")
        os.environ["HOME"] = self.casa
        try:
            self.assertNotIn("#021012", leksso_ui.pintar(leksso_ui.ESTILO_BASE))
        finally:
            if casa_real is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = casa_real


class PruebasGenerador(unittest.TestCase):
    """aplicar-tema.py genera los archivos de colores: lo que genera debe ser lo que hay en config/tema, y su comprobación
    debe saltar ante un tema ilegible."""

    def test_reproduce_los_archivos_de_colores(self):
        for nombre in generador.TEMAS:
            datos = json.load(open(os.path.join(RAIZ, "config", "tema", nombre + ".json"), encoding="utf-8"))
            guardado = {k: v.lstrip("#") for k, v in datos["colores"].items()}
            generado = generador.tokens(nombre)[0]
            if nombre == "marea":
                guardado.pop("faint"); generado.pop("faint")   # ajustado a mano en la 0.1.58 (#7f8f91), fuera del generador
            self.assertEqual(generado, guardado, nombre)
            self.assertEqual(datos["modo"], "claro" if generador.TEMAS[nombre].get("claro") else "oscuro", nombre)

    def test_purpura_de_marca(self):
        self.assertEqual(generador.tokens("blancopurpura")[0]["acc"], "340091")
        self.assertEqual(generador.tokens("purpura")[0]["soft"], "340091")

    def comprobar_con(self, temas):
        reales = generador.TEMAS
        generador.TEMAS = temas
        salida = io.StringIO()
        try:
            with contextlib.redirect_stdout(salida):
                fallos = generador.comprobar()
        finally:
            generador.TEMAS = reales
        return fallos, salida.getvalue()

    def test_los_temas_reales_pasan_la_comprobacion(self):
        self.assertEqual(self.comprobar_con(generador.TEMAS)[0], 0)

    def test_comprobacion_detecta_poco_contraste(self):
        # #340091 como acento de texto sobre fondo oscuro: 1,4:1
        fallos, salida = self.comprobar_con({"x": {"nh": 284, "nc": .045, "ah": 284, "sh": 320, "magenta": 350, "acc_hex": "340091"}})
        self.assertGreater(fallos, 0)
        self.assertIn("CONTRASTE x: acc", salida)

    def test_comprobacion_detecta_estado_parecido_al_acento(self):
        fallos, salida = self.comprobar_con({"x": {"nh": 255, "nc": .006, "ah": 148, "sh": 148, "magenta": 320}})
        self.assertIn("MATIZ x: ok", salida)

    def test_comprobacion_detecta_colores_repetidos(self):
        fondo = generador.tokens("grafito")[0]["s1"]
        fallos, salida = self.comprobar_con({"x": dict(generador.TEMAS["grafito"], acc_hex=fondo)})
        self.assertIn("REPETIDOS x", salida)


if __name__ == "__main__":
    unittest.main()
