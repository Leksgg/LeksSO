"""Pruebas de leksso-actualizar: nombres de versión y, sobre todo, la verificación de firma y de rama.

Usan repositorios y claves temporales. Requieren git y ssh-keygen. Uso: python3 scripts/test_actualizar.py
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
_l = importlib.machinery.SourceFileLoader("leksso_actualizar", os.path.join(AQUI, "leksso-actualizar.py"))
act = importlib.util.module_from_spec(importlib.util.spec_from_loader("leksso_actualizar", _l))
_l.exec_module(act)


def sh(*cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (cmd, r.stderr)
    return r.stdout.strip()


def clave_nueva(carpeta, nombre):
    ruta = os.path.join(carpeta, nombre)
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", nombre, "-f", ruta)
    return ruta


class Versiones(unittest.TestCase):
    def test_el_texto_de_fuera_se_limpia_antes_de_enseñarlo(self):
        sucio = "## 0.1.99\n\x1b[2J\x1b]0;titulo\x07texto\x08\x08normal\r\notra \u202eatrás\u200b\x00fin\ttab\x7f\x9b31m"
        limpio = act.limpiar_para_terminal(sucio)
        for malo in ("\x1b", "\x07", "\x08", "\r", "\u202e", "\u200b", "\x00", "\x7f", "\x9b"):
            self.assertNotIn(malo, limpio)
        self.assertIn("## 0.1.99\n", limpio)
        self.assertIn("\ttab", limpio)                                                   # tabuladores y saltos de línea se conservan
        self.assertIn("texto", limpio)
        self.assertEqual(act.limpiar_para_terminal("Ñandú · áéíóú ¿qué? «sí» ✓"), "Ñandú · áéíóú ¿qué? «sí» ✓")   # el español no se toca
        self.assertEqual(act.limpiar_para_terminal(None), "")

    def test_nombres_y_orden(self):
        self.assertEqual(act.bonita("0.1.0-alpha"), "Alpha 0.1.0")
        self.assertEqual(act.bonita("v1.2.3-rc"), "RC 1.2.3")
        self.assertLess(act.clave("0.1.0-alpha"), act.clave("0.1.1-alpha"))
        self.assertLess(act.clave("0.9.9-rc"), act.clave("0.10.0-alpha"))
        self.assertLess(act.clave("1.0.0-alpha"), act.clave("1.0.0-beta"))
        # sin sufijo es la versión normal: por encima de las de prueba del mismo número y por debajo del siguiente
        self.assertLess(act.clave("1.0.0-rc"), act.clave("1.0.0"))
        self.assertLess(act.clave("0.1.47-beta"), act.clave("0.1.48"))
        self.assertLess(act.clave("0.1.48"), act.clave("0.1.49-alpha"))
        self.assertEqual(act.bonita("0.1.48"), "0.1.48")
        self.assertEqual(act.bonita("v0.1.48"), "0.1.48")

    def test_nombres_hostiles_no_son_versiones(self):
        for malo in ("v1.0.0-alpha; rm -rf /", "v1.0.0-", "v1.0", "v1.0.0.0", "v1.0.0-final", "../../etc", "v1.0.0-alpha\n", "v01.0.0-evil", "", None, "v1.0.0-alpha$(id)"):
            self.assertIsNone(act.clave(malo) if malo is not None else act.clave(""), repr(malo))
            self.assertIsNone(act.ETIQUETA.match(malo or ""), repr(malo))


def escribir_y_ok(lista, cmd, original, *a, **k):
    if cmd and cmd[0] == "bash":                  # solo la provisión se simula; git sigue siendo git
        lista.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)
    return original(cmd, *a, **k)


class Verificacion(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="leksso-act-")
        self.oficial = clave_nueva(self.d, "oficial")
        self.otra = clave_nueva(self.d, "otra")
        pub = open(self.oficial + ".pub").read().split()[:2]
        self.firmantes = os.path.join(self.d, "allowed_signers")
        open(self.firmantes, "w").write(f'leksso-release namespaces="git" {pub[0]} {pub[1]}\n')
        self.repo = os.path.join(self.d, "repo")
        os.makedirs(self.repo)
        sh("git", "init", "-q", "-b", "main", cwd=self.repo)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            sh("git", "config", k, v, cwd=self.repo)
        open(os.path.join(self.repo, "a"), "w").write("1")
        sh("git", "add", "a", cwd=self.repo)
        sh("git", "commit", "-q", "-m", "uno", cwd=self.repo)
        self._viejos = (act.FIRMANTES, act.CLON, act.RAMA_PRINCIPAL)
        act.FIRMANTES, act.CLON, act.RAMA_PRINCIPAL = self.firmantes, self.repo, "main"

    def tearDown(self):
        act.FIRMANTES, act.CLON, act.RAMA_PRINCIPAL = self._viejos

    def etiqueta(self, nombre, clave=None, ref="HEAD"):
        if clave:
            sh("git", "-c", "gpg.format=ssh", "-c", f"user.signingkey={clave}", "tag", "-s", nombre, "-m", "v", ref, cwd=self.repo)
        else:
            sh("git", "tag", "-a", nombre, "-m", "v", ref, cwd=self.repo)

    def test_firma_buena_y_en_la_rama_principal(self):
        self.etiqueta("v0.1.1-alpha", self.oficial)
        commit, huella = act.verificar("v0.1.1-alpha")
        self.assertEqual(commit, sh("git", "rev-parse", "HEAD", cwd=self.repo))
        self.assertTrue(huella.startswith("SHA256:"))

    def test_version_antigua_firmada_con_nombre_de_otra_mas_nueva(self):
        """Una etiqueta firmada v0.1.1 que alguien publica como v0.9.0: la firma es válida pero el nombre no coincide."""
        self.etiqueta("v0.1.1-alpha", self.oficial)
        objeto = sh("git", "rev-parse", "v0.1.1-alpha", cwd=self.repo)
        sh("git", "update-ref", "refs/tags/v0.9.0-alpha", objeto, cwd=self.repo)
        with self.assertRaises(SystemExit) as e:
            act.verificar("v0.9.0-alpha")
        self.assertIn("mismo nombre", str(e.exception))
        act.verificar("v0.1.1-alpha")                      # la verdadera sigue pasando

    def test_se_instala_el_commit_verificado_aunque_la_etiqueta_se_mueva(self):
        self.etiqueta("v0.1.1-alpha", self.oficial)
        commit, huella = act.verificar("v0.1.1-alpha")
        open(os.path.join(self.repo, "a"), "w").write("2")
        sh("git", "commit", "-qam", "dos", cwd=self.repo)
        sh("git", "tag", "-f", "v0.1.1-alpha", "HEAD", cwd=self.repo)        # la etiqueta ahora señala otro commit
        escrito = []
        viejos = (act.subprocess.run, act.FICHERO_VERSION, act.INSTALADA)
        tmp = tempfile.mkdtemp()
        act.FICHERO_VERSION, act.INSTALADA = os.path.join(tmp, "v"), os.path.join(tmp, "i")
        act.subprocess.run = lambda cmd, *a, **k: escribir_y_ok(escrito, cmd, viejos[0], *a, **k)
        try:
            act.instalar_version("v0.1.1-alpha", "u", commit, huella)
        finally:
            act.subprocess.run, act.FICHERO_VERSION, act.INSTALADA = viejos
        self.assertEqual(sh("git", "rev-parse", "HEAD", cwd=self.repo), commit)
        self.assertEqual(open(os.path.join(self.repo, "a")).read(), "1")

    def test_sin_commit_verificado_no_instala(self):
        with self.assertRaises(SystemExit):
            act.instalar_version("v0.1.1-alpha", "u", "", "")

    def test_firmada_con_otra_clave(self):
        self.etiqueta("v0.1.1-alpha", self.otra)
        with self.assertRaises(SystemExit):
            act.verificar("v0.1.1-alpha")

    def test_sin_firmar(self):
        self.etiqueta("v0.1.1-alpha")
        with self.assertRaises(SystemExit):
            act.verificar("v0.1.1-alpha")

    def test_etiqueta_ligera_no_vale(self):
        sh("git", "tag", "v0.1.1-alpha", cwd=self.repo)
        with self.assertRaises(SystemExit):
            act.verificar("v0.1.1-alpha")

    def test_no_existe(self):
        with self.assertRaises(SystemExit):
            act.verificar("v9.9.9-alpha")

    def test_firmada_bien_pero_fuera_de_la_rama_principal(self):
        sh("git", "checkout", "-q", "-b", "ajena", cwd=self.repo)
        open(os.path.join(self.repo, "b"), "w").write("2")
        sh("git", "add", "b", cwd=self.repo)
        sh("git", "commit", "-q", "-m", "ajeno", cwd=self.repo)
        self.etiqueta("v0.1.2-alpha", self.oficial)
        sh("git", "checkout", "-q", "main", cwd=self.repo)
        with self.assertRaises(SystemExit) as e:
            act.verificar("v0.1.2-alpha")
        self.assertIn("rama principal", str(e.exception))

    def test_sin_fichero_de_firmantes(self):
        os.remove(self.firmantes)
        self.etiqueta("v0.1.1-alpha", self.oficial)
        with self.assertRaises(SystemExit):
            act.verificar("v0.1.1-alpha")

    def test_firmantes_vacio(self):
        open(self.firmantes, "w").write("")
        self.etiqueta("v0.1.1-alpha", self.oficial)
        with self.assertRaises(SystemExit):
            act.verificar("v0.1.1-alpha")


if __name__ == "__main__":
    unittest.main()
