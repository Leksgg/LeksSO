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
BASE = leksso_ui.BASE
BASE_T = leksso_ui.tokens(BASE)
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

    def leer(self, *rel):
        return open(os.path.join(self.casa, *rel), encoding="utf-8").read().lower()

    def test_ida_y_vuelta_identica(self):
        antes = self.contenido()
        self.assertEqual(self.tema("aplicar", "pizarra").returncode, 0)
        self.assertNotEqual(antes, self.contenido())
        self.assertEqual(self.tema("actual").stdout.strip(), "pizarra")
        self.assertEqual(self.tema("aplicar", BASE).returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_la_base_es_grafito(self):
        self.assertEqual(BASE, "grafito")
        self.assertEqual(self.tema("actual").stdout.strip(), "grafito")      # sin elegir nada
        self.assertEqual(open(os.path.join(RAIZ, "config", "tema", "activo")).read().strip(), "grafito")
        barra = open(os.path.join(RAIZ, "config", "waybar", "style.css"), encoding="utf-8").read().lower()
        self.assertIn(leksso_ui.tokens("grafito")["bg"], barra)

    def test_no_quedan_colores_del_tema_anterior(self):
        self.tema("aplicar", "pizarra")
        for destino, datos in self.contenido().items():
            if destino.endswith("settings.conf"):
                continue  # solo lleva algunos colores
            texto = datos.decode("utf-8").lower()
            for c in (BASE_T["bg"], BASE_T["acc"], BASE_T["text"]):
                self.assertNotIn(c, texto, f"{destino} sigue con {c}")

    def test_tema_desconocido_no_toca_nada(self):
        antes = self.contenido()
        r = self.tema("aplicar", "noexiste")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_reaplicar_tras_copiar_la_base(self):
        self.tema("aplicar", "pizarra")
        for origen, destino in COPIAS.items():  # una actualización vuelve a copiar la base (Grafito)
            shutil.copy(os.path.join(RAIZ, "config", origen), os.path.join(self.casa, destino))
        self.assertEqual(self.tema("reaplicar").returncode, 0)
        barra = self.leer(".config", "waybar", "style.css")
        self.assertIn(leksso_ui.tokens("pizarra")["bg"], barra)   # la base recién copiada vuelve a llevar Pizarra
        self.assertNotIn(BASE_T["bg"], barra)
        self.tema("aplicar", BASE)
        base = {d: open(os.path.join(RAIZ, "config", o), "rb").read() for o, d in COPIAS.items()}
        self.assertEqual(base, self.contenido())

    def test_hay_siete_temas(self):
        self.assertEqual(set(self.tema("listar").stdout.split()),
                         {"grafito", "grafitoclaro", "waves", "wavesclaro", "pizarra", "grisrosa", "blancorosa"})

    def test_temas_retirados_no_estan(self):
        for retirado in ("marea", "alba", "purpura", "blancopurpura"):
            self.assertFalse(os.path.exists(os.path.join(RAIZ, "config", "tema", retirado + ".json")), retirado)
            self.assertNotEqual(self.tema("aplicar", retirado).returncode, 0, retirado)

    def test_temas_se_aplican_y_se_deshacen(self):
        """Cada tema pinta barra y terminal, es claro u oscuro según su archivo y se vuelve a la base sin diferencias."""
        antes = self.contenido()
        for nombre, claro in (("waves", False), ("pizarra", False), ("grisrosa", False),
                              ("grafitoclaro", True), ("wavesclaro", True), ("blancorosa", True)):
            self.assertEqual(self.tema("aplicar", nombre).returncode, 0)
            t = leksso_ui.tokens(nombre)
            texto = self.leer(".config", "waybar", "style.css")
            self.assertIn(t["bg"], texto)
            self.assertNotIn(BASE_T["bg"], texto)
            kitty = self.leer(".config", "kitty", "kitty.conf")
            self.assertIn("background #" + t["bg"], kitty)
            self.assertEqual(leksso_ui.es_claro(nombre), claro)
            if claro:
                self.assertIn("color15 #" + t["text"], kitty)    # el blanco brillante no se queda invisible sobre fondo claro
        self.assertEqual(self.tema("aplicar", BASE).returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_de_un_tema_a_otro_sin_pasar_por_la_base(self):
        antes = self.contenido()
        self.assertEqual(self.tema("aplicar", "waves").returncode, 0)
        self.assertEqual(self.tema("aplicar", "wavesclaro").returncode, 0)
        self.assertNotIn(leksso_ui.tokens("waves")["bg"], self.leer(".config", "waybar", "style.css"))
        self.assertEqual(self.tema("aplicar", "pizarra").returncode, 0)
        self.assertEqual(self.tema("aplicar", BASE).returncode, 0)
        self.assertEqual(antes, self.contenido())

    def test_tema_claro_completo(self):
        antes = self.contenido()
        self.assertEqual(self.tema("aplicar", "grafitoclaro").returncode, 0)
        iconos = os.path.join(self.casa, ".local", "share", "icons", "LeksSO")
        self.assertTrue(os.path.isdir(iconos))
        svgs = [os.path.join(r, f) for r, _, fs in os.walk(iconos) for f in fs if f.endswith(".svg")]
        self.assertTrue(svgs)
        todo = "".join(open(f, encoding="utf-8").read().lower() for f in svgs)
        self.assertNotIn("#" + BASE_T["bg"], todo)              # ningún icono conserva el fondo oscuro de la base
        self.assertNotIn("#" + BASE_T["s2"], todo)
        self.assertEqual(self.tema("aplicar", BASE).returncode, 0)
        self.assertFalse(os.path.isdir(iconos))                 # con la base valen los del sistema
        self.assertEqual(antes, self.contenido())
        self.assertIn("color15 #ffffff", self.leer(".config", "kitty", "kitty.conf"))

    def test_no_queda_ningun_color_propio_del_tema_anterior(self):
        """Todos los papeles cambian (también el relleno de selección), no solo fondo, acento y texto."""
        for nombre in ("pizarra", "wavesclaro"):
            self.assertEqual(self.tema("aplicar", nombre).returncode, 0)
            viejo = set(BASE_T.values()) - set(leksso_ui.tokens(nombre).values())
            for destino, datos in self.contenido().items():
                if destino.endswith("settings.conf"):
                    continue
                texto = datos.decode("utf-8").lower()
                for c in viejo:
                    self.assertNotIn(c, texto, f"{nombre}: {destino} sigue con {c} de la base")
            self.assertEqual(self.tema("aplicar", BASE).returncode, 0)

    def test_pantalla_de_bloqueo_sigue_el_tema(self):
        swaylock = os.path.join(self.casa, ".config", "swaylock", "config")
        propia = os.path.join(self.casa, ".config", "leksso", "bloqueo.png")
        self.assertEqual(self.tema("aplicar", "waves").returncode, 0)
        self.assertIn("image=" + propia, open(swaylock, encoding="utf-8").read())
        self.assertTrue(os.path.isfile(propia))
        self.assertEqual(self.tema("aplicar", BASE).returncode, 0)
        self.assertIn("image=/usr/share/leksso/bloqueo.png", open(swaylock, encoding="utf-8").read())

    def test_etiquetas_de_iconos_oscuras_en_tema_claro(self):
        """En un tema claro el texto de las etiquetas (sobre el color del tipo de archivo) pasa a ser el texto oscuro del tema."""
        self.assertEqual(self.tema("aplicar", "wavesclaro").returncode, 0)
        icono = os.path.join(self.casa, ".local", "share", "icons", "LeksSO", "scalable", "mimetypes", "text-x-javascript.svg")
        texto = open(icono, encoding="utf-8").read().lower()
        self.assertIn('font-size="11" fill="#' + leksso_ui.tokens("wavesclaro")["text"] + '">js<', texto)

    def test_nombre_de_tema_raro_vuelve_a_la_base(self):
        """~/.config/leksso/tema lo puede escribir cualquier programa del usuario: un nombre con rutas no se usa."""
        os.makedirs(os.path.join(self.casa, ".config", "leksso"))
        casa_real = os.environ.get("HOME")
        os.environ["HOME"] = self.casa
        try:
            for raro in ("../../etc/passwd", "waves/../x", "waves.json", ""):
                open(os.path.join(self.casa, ".config", "leksso", "tema"), "w").write(raro + "\n")
                self.assertEqual(leksso_ui.tema_activo(), leksso_ui.BASE, raro)
        finally:
            if casa_real is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = casa_real

    def test_estilo_de_ventanas_sigue_el_tema(self):
        os.makedirs(os.path.join(self.casa, ".config", "leksso"))
        open(os.path.join(self.casa, ".config", "leksso", "tema"), "w").write("pizarra\n")
        casa_real = os.environ.get("HOME")
        os.environ["HOME"] = self.casa
        try:
            self.assertNotIn("#" + BASE_T["bg"], leksso_ui.pintar(leksso_ui.ESTILO_BASE))
        finally:
            if casa_real is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = casa_real


class PruebasMigracion(unittest.TestCase):
    """El bloque de provision-base.sh que pasa a quien tenía un tema retirado al más parecido. Se ejecuta el bloque real,
    con la carpeta de temas instalados y el usuario cambiados por unos de prueba."""

    def setUp(self):
        texto = open(os.path.join(RAIZ, "scripts", "provision-base.sh"), encoding="utf-8").read()
        i = texto.index('TEMA_USR="$HOME_USR/.config/leksso/tema"')
        j = texto.index('sudo -u "$USUARIO" leksso-tema reaplicar')
        self.casa = tempfile.mkdtemp()
        self.temas = os.path.join(self.casa, "temas")
        os.makedirs(self.temas)
        for f in os.listdir(os.path.join(RAIZ, "config", "tema")):
            if f.endswith(".json"):
                shutil.copy(os.path.join(RAIZ, "config", "tema", f), self.temas)
        self.bloque = texto[i:j].replace("/usr/local/share/leksso/temas", self.temas)
        os.makedirs(os.path.join(self.casa, ".config", "leksso"))
        self.archivo = os.path.join(self.casa, ".config", "leksso", "tema")

    def tearDown(self):
        shutil.rmtree(self.casa, ignore_errors=True)

    def migrar(self, contenido):
        if contenido is None:
            if os.path.exists(self.archivo):
                os.remove(self.archivo)
        else:
            open(self.archivo, "w").write(contenido)
        guion = "set -euo pipefail\nU() { \"$@\"; }\nHOME_USR=" + self.casa + "\n" + self.bloque
        r = subprocess.run(["bash", "-c", guion], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return open(self.archivo).read().strip() if os.path.exists(self.archivo) else None

    def test_retirados_al_mas_parecido(self):
        self.assertEqual(self.migrar("marea\n"), "grafito")
        self.assertEqual(self.migrar("alba\n"), "wavesclaro")
        self.assertEqual(self.migrar("purpura\n"), "grafito")
        self.assertEqual(self.migrar("../../etc/x\n"), "grafito")
        self.assertEqual(self.migrar("../temas/waves\n"), "grafito")   # una ruta que lleva a un tema que existe tampoco vale

    def test_los_que_siguen_no_cambian(self):
        for nombre in ("waves", "pizarra", "grisrosa", "blancorosa", "grafitoclaro", "wavesclaro", "grafito"):
            self.assertEqual(self.migrar(nombre + "\n"), nombre)

    def test_sin_eleccion_no_crea_nada(self):
        self.assertIsNone(self.migrar(None))          # sin archivo se usa la base, Grafito

    def test_quita_los_archivos_de_temas_retirados(self):
        texto = open(os.path.join(RAIZ, "scripts", "provision-base.sh"), encoding="utf-8").read()
        self.assertIn("rm -f /usr/local/share/leksso/temas/marea.json /usr/local/share/leksso/temas/alba.json", texto)
        self.assertLess(texto.index('install -m 0644 "$RAIZ"/config/tema/*.json'),
                        texto.index("rm -f /usr/local/share/leksso/temas/marea.json"))


class PruebasGenerador(unittest.TestCase):
    """aplicar-tema.py genera los archivos de colores: lo que genera debe ser lo que hay en config/tema, y su comprobación
    debe saltar ante un tema ilegible."""

    def test_reproduce_los_archivos_de_colores(self):
        archivos = {f[:-5] for f in os.listdir(os.path.join(RAIZ, "config", "tema")) if f.endswith(".json")}
        self.assertEqual(archivos, set(generador.TEMAS))
        for nombre in generador.TEMAS:
            datos = json.load(open(os.path.join(RAIZ, "config", "tema", nombre + ".json"), encoding="utf-8"))
            guardado = {k: v.lstrip("#") for k, v in datos["colores"].items()}
            self.assertEqual(generador.tokens(nombre)[0], guardado, nombre)
            self.assertEqual(datos["modo"], "claro" if generador.TEMAS[nombre].get("claro") else "oscuro", nombre)

    def test_versiones_claras_comparten_acento(self):
        """Grafito claro y Waves claro son las versiones claras: mismo matiz de acento y de neutros que su tema oscuro."""
        for oscuro, claro in (("grafito", "grafitoclaro"), ("waves", "wavesclaro")):
            o, c = generador.TEMAS[oscuro], generador.TEMAS[claro]
            self.assertTrue(c.get("claro"))
            self.assertEqual((o["nh"], o["ah"], o["sh"]), (c["nh"], c["ah"], c["sh"]))

    def comprobar_con(self, temas, cambios=None):
        """Comprobación sobre `temas`; `cambios` sustituye papeles de la paleta generada (una paleta defectuosa a propósito)."""
        reales_t, reales_k = generador.TEMAS, generador.tokens
        generador.TEMAS = temas
        if cambios:
            generador.tokens = lambda nombre: (dict(reales_k(nombre)[0], **cambios), reales_k(nombre)[1])
        salida = io.StringIO()
        try:
            with contextlib.redirect_stdout(salida):
                fallos = generador.comprobar()
        finally:
            generador.TEMAS, generador.tokens = reales_t, reales_k
        return fallos, salida.getvalue()

    def test_los_temas_reales_pasan_la_comprobacion(self):
        self.assertEqual(self.comprobar_con(generador.TEMAS)[0], 0)

    def test_comprobacion_detecta_poco_contraste(self):
        # un acento índigo oscuro como texto sobre fondo oscuro: 1,4:1
        fallos, salida = self.comprobar_con({"grafito": generador.TEMAS["grafito"]}, {"acc": "340091"})
        self.assertGreater(fallos, 0)
        self.assertIn("CONTRASTE grafito: acc", salida)

    def test_comprobacion_detecta_estado_parecido_al_acento(self):
        fallos, salida = self.comprobar_con({"x": {"nh": 255, "nc": .006, "ah": 148, "sh": 148, "magenta": 320}})
        self.assertIn("MATIZ x: ok", salida)

    def test_comprobacion_detecta_estado_ilegible_sobre_su_relleno(self):
        """El aviso de la barra pinta el texto del estado sobre su relleno (*_soft): tiene que leerse."""
        fallos, salida = self.comprobar_con({"grafito": generador.TEMAS["grafito"]}, {"warn_soft": "ffe14a", "warn": "fff06a"})
        self.assertIn("CONTRASTE grafito: warn sobre warn_soft", salida)

    def test_comprobacion_detecta_gris_tenue_ilegible(self):
        fallos, salida = self.comprobar_con({"grafito": generador.TEMAS["grafito"]}, {"faint": "2a2c30"})
        self.assertIn("CONTRASTE grafito: faint sobre bg", salida)

    def test_comprobacion_detecta_colores_repetidos(self):
        fondo = generador.tokens("grafito")[0]["s1"]
        fallos, salida = self.comprobar_con({"grafito": generador.TEMAS["grafito"]}, {"line": fondo})
        self.assertIn("REPETIDOS grafito", salida)


if __name__ == "__main__":
    unittest.main()
