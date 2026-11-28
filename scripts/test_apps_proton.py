#!/usr/bin/env python3
"""Proton en leksso-apps: qué versión se elige, que una suma distinta no instala y que no entra en --todo.
Uso: python3 scripts/test_apps_proton.py"""
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import os
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
_l = importlib.machinery.SourceFileLoader("leksso_apps", os.path.join(AQUI, "leksso-apps.py"))
apps = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_apps", _l))
_l.exec_module(apps)

SUMA = "a" * 128


def release(version, categoria="Stable", reparto=1, url="https://proton.me/download/x/x.deb", suma=SUMA,
            clave="RolloutPercentage"):
    return {"CategoryName": categoria, "Version": version, clave: reparto,
            "File": [{"Url": url, "Sha512CheckSum": suma}]}


class Version(unittest.TestCase):
    def test_la_estable_mas_alta_por_numero(self):
        r = {"Releases": [release("1.9.0"), release("1.10.0"), release("2.0.0", "EarlyAccess")]}
        self.assertEqual(apps.version_proton(r)[0], "1.10.0")

    def test_un_reparto_parcial_espera(self):
        r = {"Releases": [release("1.2.0", reparto=0.5, clave="RolloutProportion"),
                          release("1.1.0", clave="RolloutProportion")]}
        self.assertEqual(apps.version_proton(r)[0], "1.1.0")

    def test_otro_origen_o_sin_suma_no_vale(self):
        for mala in (release("1.0", url="https://proton.me.evil.com/download/x.deb"),
                     release("1.0", url="http://proton.me/download/x.deb"), release("1.0", suma="")):
            with self.assertRaises(SystemExit):
                apps.version_proton({"Releases": [mala]})


class Suma(unittest.TestCase):
    def bajar(self, suma):
        def falso(url, destino):
            with open(destino, "wb") as f:
                f.write(b"paquete")
        with mock.patch.object(apps, "descargar", falso), contextlib.redirect_stdout(io.StringIO()):
            return apps.bajar_comprobado("https://x.example.com/a.deb", suma)

    def test_la_suma_correcta_pasa(self):
        self.assertEqual(self.bajar(("sha512", hashlib.sha512(b"paquete").hexdigest())), b"paquete")

    def test_una_suma_distinta_no_pasa(self):
        with self.assertRaises(SystemExit):
            self.bajar(("sha256", "0" * 64))


class Llavero(unittest.TestCase):
    def test_el_lanzador_pide_el_llavero(self):
        escrito = {}

        def falso(cmd, **kw):
            escrito["texto"] = kw["input"].decode()
            return mock.Mock(returncode=0)
        lanzador = "[Desktop Entry]\nName=Proton Pass\nExec=proton-pass %U\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=lanzador)), \
                mock.patch.object(apps.subprocess, "run", falso), mock.patch.object(apps, "sudo", return_value=0):
            self.assertEqual(apps.usar_llavero("proton-pass"), 0)
        self.assertIn("\nExec=proton-pass --password-store=gnome-libsecret %U\n", escrito["texto"])


class Catalogo(unittest.TestCase):
    def test_proton_no_entra_en_todo_ni_completo(self):
        for opcion in ("--todo", "--completo"):
            hechos = []
            with mock.patch.object(apps, "instalado", return_value=False), \
                    mock.patch.object(apps, "hacer", lambda it, *a: hechos.append(it[1]) or 0), \
                    contextlib.redirect_stdout(io.StringIO()):
                apps.main(["instalar", opcion, "--simular"])
            self.assertTrue(hechos)
            self.assertFalse(set(hechos) & apps.SOLO_POR_NOMBRE)

    def test_el_grupo_proton_son_las_cuatro(self):
        self.assertEqual({it[1] for it in apps.buscar(["proton"])}, apps.SOLO_POR_NOMBRE)

    def test_umu_se_marca_como_de_terceros(self):
        self.assertIn("umu", apps.ALTERNATIVAS)

    def test_simular_no_descarga_nada(self):
        with mock.patch.object(apps, "abrir_https", side_effect=AssertionError("ha salido a la red")), \
                mock.patch.object(apps, "instalado", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(apps.main(["instalar", "proton", "umu", "--simular"]), 0)


if __name__ == "__main__":
    unittest.main()
