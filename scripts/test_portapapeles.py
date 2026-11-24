#!/usr/bin/env python3
"""Historial del portapapeles (leksso-portapapeles-guardar): lo sensible no se guarda y lo demás caduca.
Hallazgo 17 de la revisión de la 0.1.52. Usa un cliphist y un wl-paste falsos: no toca el portapapeles de nadie.
Solo Linux (los falsos son scripts de sh). Uso: python3 scripts/test_portapapeles.py"""
import importlib.machinery
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")

cargador = importlib.machinery.SourceFileLoader("guardar_portapapeles", os.path.join(RAIZ, "config", "bin", "leksso-portapapeles-guardar"))
pp = importlib.util.module_from_spec(importlib.util.spec_from_loader("guardar_portapapeles", cargador))
cargador.exec_module(pp)

CLIPHIST_FALSO = r'''#!/bin/sh
# Un cliphist de mentira: el historial es un archivo de líneas «id<TAB>texto», la más nueva al final.
T=$(printf '\t')
case "$1" in
  store) dato=$(cat); n=$(( $(cat "$FALSO_DB.n" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FALSO_DB.n"
         printf '%s\t%s\n' "$n" "$dato" >> "$FALSO_DB" ;;
  list)  [ -f "$FALSO_DB" ] && tac "$FALSO_DB" ;;
  delete) while IFS= read -r l; do id="${l%%"$T"*}"; grep -v "^$id$T" "$FALSO_DB" > "$FALSO_DB.t"; mv "$FALSO_DB.t" "$FALSO_DB"; done ;;
esac
exit 0
'''
WLPASTE_FALSO = '''#!/bin/sh
[ "$1" = "--list-types" ] && printf '%s\\n' $FALSO_TIPOS
exit 0
'''


@unittest.skipIf(os.name == "nt", "los programas falsos son scripts de sh: se prueba en Linux")
class Portapapeles(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        b = os.path.join(self.d, "bin")
        os.makedirs(b)
        for nombre, texto in (("cliphist", CLIPHIST_FALSO), ("wl-paste", WLPASTE_FALSO)):
            ruta = os.path.join(b, nombre)
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(texto)
            os.chmod(ruta, 0o755)
        self.db = os.path.join(self.d, "historial")
        self.env = mock.patch.dict(os.environ, {
            "PATH": b + os.pathsep + os.environ["PATH"], "FALSO_DB": self.db, "FALSO_TIPOS": "text/plain",
            "XDG_CONFIG_HOME": os.path.join(self.d, "config"), "XDG_CACHE_HOME": os.path.join(self.d, "cache")})
        self.env.start()
        os.environ.pop("CLIPBOARD_STATE", None)
        self.addCleanup(self.env.stop)

    def historial(self):
        try:
            with open(self.db, encoding="utf-8") as f:
                return [x.split("\t")[1] for x in f.read().splitlines()]
        except OSError:
            return []

    def poner_caducidad(self, minutos):
        os.makedirs(os.path.dirname(pp.ruta_config()), exist_ok=True)
        with open(pp.ruta_config(), "w", encoding="utf-8") as f:
            f.write(f"caduca_min={minutos}\n")

    # ----- lo sensible no se guarda -----
    def test_que_es_sensible(self):
        self.assertTrue(pp.es_sensible({}, ["text/plain", "x-kde-passwordManagerHint"]))
        self.assertTrue(pp.es_sensible({}, ["X-KDE-PASSWORDMANAGERHINT"]))               # sin distinguir mayúsculas
        self.assertTrue(pp.es_sensible({"CLIPBOARD_STATE": "sensitive"}, []))
        self.assertTrue(pp.es_sensible({"CLIPBOARD_STATE": "clear"}, []))
        self.assertFalse(pp.es_sensible({"CLIPBOARD_STATE": "data"}, ["text/plain", "text/html"]))
        self.assertFalse(pp.es_sensible({}, []))

    def test_lo_normal_se_guarda(self):
        self.assertTrue(pp.guardar(b"una receta", entorno={}, ahora=1000.0))
        self.assertEqual(self.historial(), ["una receta"])

    def test_lo_que_marca_un_gestor_de_contrasenas_no_se_guarda(self):
        os.environ["FALSO_TIPOS"] = "text/plain x-kde-passwordManagerHint"
        self.assertFalse(pp.guardar(b"hunter2", entorno={}, ahora=1000.0))
        self.assertEqual(self.historial(), [])
        self.assertEqual(pp.leer_tiempos(), {})

    def test_el_estado_sensible_de_wl_clipboard_tampoco_se_guarda(self):
        self.assertFalse(pp.guardar(b"hunter2", entorno={"CLIPBOARD_STATE": "sensitive"}, ahora=1000.0))
        self.assertEqual(self.historial(), [])

    def test_vacio_o_enorme_no_se_guarda(self):
        self.assertFalse(pp.guardar(b"", entorno={}))
        self.assertFalse(pp.guardar(b"x" * (pp.MAX_BYTES + 1), entorno={}))
        self.assertEqual(self.historial(), [])

    # ----- caducidad -----
    def test_por_defecto_caduca_a_las_dos_horas(self):
        self.assertEqual(pp.minutos_de_caducidad(), 120)
        pp.guardar(b"vieja", entorno={}, ahora=1000.0)
        pp.guardar(b"nueva", entorno={}, ahora=1000.0 + 100 * 60)
        self.assertEqual(self.historial(), ["vieja", "nueva"])                         # a los 100 min aún no
        borradas = pp.caducar(ahora=1000.0 + 121 * 60)
        self.assertEqual(len(borradas), 1)
        self.assertEqual(self.historial(), ["nueva"])                                  # la vieja se fue, la nueva sigue

    def test_la_caducidad_se_puede_cambiar_y_quitar(self):
        self.poner_caducidad(15)
        pp.guardar(b"a", entorno={}, ahora=1000.0)
        pp.caducar(ahora=1000.0 + 16 * 60)
        self.assertEqual(self.historial(), [])
        self.poner_caducidad(0)                                                         # nunca
        pp.guardar(b"b", entorno={}, ahora=1000.0)
        pp.caducar(ahora=1000.0 + 10 * 365 * 24 * 3600)
        self.assertEqual(self.historial(), ["b"])

    def test_un_valor_raro_vuelve_al_por_defecto(self):
        for malo in ("caduca_min=abc", "caduca_min=-5", "caduca_min=", "otra=15", "basura"):
            self.poner_caducidad("")
            with open(pp.ruta_config(), "w", encoding="utf-8") as f:
                f.write(malo + "\n")
            self.assertEqual(pp.minutos_de_caducidad(), 120, malo)

    def test_lo_que_ya_estaba_sin_hora_empieza_a_contar_desde_ahora(self):
        with open(self.db, "w", encoding="utf-8") as f:                                  # un historial de antes, sin horas
            f.write("1\tantiguo\n")
        self.assertEqual(pp.caducar(ahora=5000.0), [])                                   # no se borra de golpe
        self.assertEqual(pp.leer_tiempos(), {"1": 5000.0})
        pp.caducar(ahora=5000.0 + 121 * 60)
        self.assertEqual(self.historial(), [])

    def test_el_archivo_de_horas_olvida_lo_que_ya_no_existe_y_es_privado(self):
        pp.guardar(b"uno", entorno={}, ahora=1000.0)
        pp.guardar(b"dos", entorno={}, ahora=1001.0)
        self.assertEqual(len(pp.leer_tiempos()), 2)
        os.remove(self.db)                                                               # alguien vació el historial por otro lado
        pp.caducar(ahora=1002.0)
        self.assertEqual(pp.leer_tiempos(), {})
        ruta = pp.ruta_tiempos()
        pp.guardar_tiempos({"1": 1.0})
        self.assertEqual(stat.S_IMODE(os.stat(ruta).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(ruta)).st_mode), 0o700)

    def test_el_archivo_de_horas_roto_no_rompe_nada(self):
        os.makedirs(os.path.dirname(pp.ruta_tiempos()), exist_ok=True)
        with open(pp.ruta_tiempos(), "w", encoding="utf-8") as f:
            f.write("{no es json")
        self.assertEqual(pp.leer_tiempos(), {})
        self.assertTrue(pp.guardar(b"sigue funcionando", entorno={}, ahora=1000.0))


class Cableado(unittest.TestCase):
    def leer(self, ruta):
        with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
            return f.read()

    def test_la_sesion_guarda_con_el_filtro_y_ya_no_con_cliphist_a_pelo(self):
        sway = self.leer("config/sway/config")
        self.assertNotIn("--watch cliphist store", sway)
        self.assertIn("wl-paste --type text --watch leksso-portapapeles-guardar guardar", sway)
        self.assertIn("wl-paste --type image --watch leksso-portapapeles-guardar guardar", sway)
        self.assertIn("leksso-portapapeles-guardar caducar", sway)

    def test_se_instala_y_la_ventana_deja_cambiar_el_tiempo(self):
        self.assertIn("config/bin/leksso-portapapeles-guardar", self.leer("scripts/provision-base.sh"))
        ventana = self.leer("config/bin/leksso-portapapeles")
        self.assertIn("caduca_min", ventana)
        self.assertIn("Nunca", ventana)

    def test_el_guardador_no_importa_qt_porque_arranca_en_cada_copia(self):
        self.assertNotIn("PySide6", self.leer("config/bin/leksso-portapapeles-guardar"))


if __name__ == "__main__":
    unittest.main()
