#!/usr/bin/env python3
"""Calendario de consulta (leksso-calendario): la lógica de meses y festivos y la coherencia de los datos de festivos.
Uso: python3 scripts/test_calendario.py"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")
_l = importlib.machinery.SourceFileLoader("leksso_calendario", os.path.join(RAIZ, "config", "bin", "leksso-calendario"))
cal = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_calendario", _l))
_l.exec_module(cal)
RUTA_DATOS = os.path.join(RAIZ, "config", "calendario", "festivos.json")


def datos():
    return cal.cargar([RUTA_DATOS])


class Logica(unittest.TestCase):
    def test_rejilla_empieza_en_lunes_y_cubre_el_mes(self):
        for anio, mes in ((2026, 11), (2026, 12), (2027, 2), (2028, 2)):
            r = cal.rejilla(anio, mes)
            self.assertEqual(len(r), 42)
            self.assertEqual(r[0].weekday(), 0)                         # lunes
            self.assertEqual(r[0].isocalendar()[2], 1)
            dias = {d.day for d in r if d.month == mes}
            ultimo = (datetime.date(anio + (mes == 12), mes % 12 + 1, 1) - datetime.timedelta(days=1)).day
            self.assertEqual(dias, set(range(1, ultimo + 1)))

    def test_noviembre_2026(self):
        r = cal.rejilla(2026, 11)
        self.assertEqual(r[0], datetime.date(2026, 10, 26))             # el 1 de noviembre es domingo
        self.assertEqual(r[6], datetime.date(2026, 11, 1))

    def test_mes_vecino(self):
        self.assertEqual(cal.mes_vecino(2026, 12, 1), (2027, 1))
        self.assertEqual(cal.mes_vecino(2026, 1, -1), (2025, 12))
        self.assertEqual(cal.mes_vecino(2026, 5, 0), (2026, 5))
        self.assertEqual(cal.mes_vecino(2026, 3, 14), (2027, 5))

    def test_festivos_del_mes_en_orden(self):
        fs = cal.festivos_del_mes(datos(), 2026, 12)
        self.assertEqual([d.day for d, _, _ in fs], [7, 8, 25])
        self.assertEqual(cal.festivos_del_mes(datos(), 2026, 6), [])

    def test_estado_de_cada_anio(self):
        d = datos()
        self.assertEqual(cal.estado_anio(d, 2026)[0], "completo")
        e, nota = cal.estado_anio(d, 2027)
        self.assertEqual(e, "incompleto")
        self.assertIn("locales", nota)
        e, nota = cal.estado_anio(d, 2035)
        self.assertEqual(e, "ausente")                                  # no se enseña un año sin datos como si no hubiera festivos
        self.assertIn("2035", nota)

    def test_sin_archivo_no_falla(self):
        self.assertEqual(cal.cargar(["/no/existe.json", ""]), {})
        self.assertEqual(cal.festivos_del_anio({}, 2026), {})

    def test_nombre_del_dia(self):
        self.assertEqual(cal.nombre_dia(datetime.date(2026, 12, 25)), "viernes")
        self.assertEqual(cal.nombre_dia(datetime.date(2026, 12, 7)), "lunes")


class DatosDeFestivos(unittest.TestCase):
    """El archivo de festivos es lo que la gente lee como verdad: se comprueba que no tenga erratas evidentes."""

    def setUp(self):
        with open(RUTA_DATOS, encoding="utf-8") as f:
            self.todo = json.load(f)["anios"]

    def test_fechas_validas_del_anio_y_sin_repetir(self):
        for anio, d in self.todo.items():
            fechas = [datetime.date.fromisoformat(f["fecha"]) for f in d["festivos"]]
            self.assertEqual({x.year for x in fechas}, {int(anio)}, anio)
            self.assertEqual(len(fechas), len(set(fechas)), f"{anio}: fechas repetidas")
            self.assertEqual(fechas, sorted(fechas), f"{anio}: fuera de orden")

    def test_ambitos_y_nombres(self):
        for anio, d in self.todo.items():
            for f in d["festivos"]:
                self.assertIn(f["ambito"], cal.AMBITOS, f"{anio} {f['fecha']}")
                self.assertTrue(f["nombre"].strip())

    def test_2026_tiene_14_festivos_doce_mas_dos_locales(self):
        fs = self.todo["2026"]["festivos"]
        self.assertEqual(len(fs), 14)
        self.assertEqual(sum(1 for f in fs if f["ambito"] == "local"), 2)
        self.assertEqual(sum(1 for f in fs if f["ambito"] != "local"), 12)

    def test_2027_tiene_12_de_comunidad_y_nacionales_y_avisa_de_las_locales(self):
        d = self.todo["2027"]
        self.assertEqual(len(d["festivos"]), 12)
        self.assertFalse(d["completo"])
        self.assertTrue(d.get("nota"))
        self.assertEqual(sum(1 for f in d["festivos"] if f["ambito"] == "local"), 0)

    def test_dias_de_la_semana_de_fechas_conocidas(self):
        """Fechas comprobadas contra el BOE: el día de la semana tiene que cuadrar."""
        esperado = {"2026-11-02": 0, "2026-12-07": 0, "2026-12-25": 4, "2026-05-02": 5, "2027-08-16": 0, "2027-03-19": 4,
                    "2027-03-25": 3, "2027-03-26": 4, "2027-12-25": 5, "2027-12-06": 0}
        todas = {f["fecha"] for d in self.todo.values() for f in d["festivos"]}
        for fecha, dia in esperado.items():
            self.assertIn(fecha, todas)
            self.assertEqual(datetime.date.fromisoformat(fecha).weekday(), dia, fecha)

    def test_los_festivos_de_domingo_van_trasladados_a_lunes(self):
        """En 2026 el 1 de noviembre y el 6 de diciembre caen en domingo: el festivo es el lunes siguiente."""
        fechas = {f["fecha"] for f in self.todo["2026"]["festivos"]}
        self.assertNotIn("2026-11-01", fechas)
        self.assertNotIn("2026-12-06", fechas)
        self.assertIn("2026-11-02", fechas)
        self.assertIn("2026-12-07", fechas)

    def test_cada_anio_cita_su_fuente(self):
        for anio, d in self.todo.items():
            self.assertTrue(d.get("fuente"), anio)
            self.assertTrue(d.get("revisado"), anio)


class Instalacion(unittest.TestCase):
    def test_provision_instala_el_calendario_y_los_festivos(self):
        s = open(os.path.join(AQUI, "provision-base.sh"), encoding="utf-8").read()
        self.assertIn("config/bin/leksso-calendario", s)
        self.assertIn("/usr/local/share/leksso/festivos.json", s)

    def test_el_reloj_abre_el_calendario(self):
        s = open(os.path.join(RAIZ, "config", "waybar", "config.jsonc"), encoding="utf-8").read()
        self.assertIn('"on-click": "leksso-calendario"', s)
        json.loads(s) if s.lstrip().startswith("{") else json.loads(s[s.index("["):])   # el archivo sigue siendo JSON válido

    def test_la_ventana_flota_y_no_va_a_la_zona_central(self):
        sway = open(os.path.join(RAIZ, "config", "sway", "config"), encoding="utf-8").read()
        self.assertIn('app_id="leksso-calendario"] floating enable', sway)
        zonas = open(os.path.join(RAIZ, "config", "sway", "zonas.sh"), encoding="utf-8").read()
        self.assertIn("calendario", zonas)


if __name__ == "__main__":
    unittest.main()
