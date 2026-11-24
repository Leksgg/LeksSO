"""Pruebas del instalador (scripts/instalar.sh): elección de versión y verificación de firma y de rama.

Usan repositorios y claves temporales (LEKSSO_INSTALAR_PRUEBAS=1 solo sirve para sustituirlos).
Requieren bash, git y ssh-keygen. Uso: python3 scripts/test_instalar.py
"""
import os
import subprocess
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(AQUI, "instalar.sh")


def sh(*cmd, cwd=None, env=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, (cmd, r.stderr)
    return r.stdout.strip()


def posix(ruta):
    """Ruta usable dentro de bash (en Windows con Git Bash, C:\\x → /c/x)."""
    ruta = os.path.abspath(ruta).replace("\\", "/")
    if len(ruta) > 1 and ruta[1] == ":":
        ruta = "/" + ruta[0].lower() + ruta[2:]
    return ruta


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="leksso-inst-")
        self.oficial = self.clave("oficial")
        self.otra = self.clave("otra")
        self.pub = open(self.oficial + ".pub").read().split()[:2]
        self.linea = f'leksso-release namespaces="git" {self.pub[0]} {self.pub[1]}'
        self.huella = sh("ssh-keygen", "-lf", self.oficial + ".pub").split()[1]
        self.repo = os.path.join(self.d, "repo")
        os.makedirs(self.repo)
        sh("git", "init", "-q", "-b", "main", cwd=self.repo)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            sh("git", "config", k, v, cwd=self.repo)
        open(os.path.join(self.repo, "VERSION"), "w").write("0.1.0-alpha\n")
        sh("git", "add", "VERSION", cwd=self.repo)
        sh("git", "commit", "-q", "-m", "uno", cwd=self.repo)

    def clave(self, nombre):
        ruta = os.path.join(self.d, nombre)
        sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", nombre, "-f", ruta)
        return ruta

    def etiqueta(self, nombre, clave=None, ref="HEAD"):
        if clave:
            sh("git", "-c", "gpg.format=ssh", "-c", f"user.signingkey={clave}", "tag", "-s", nombre, "-m", "v", ref, cwd=self.repo)
        else:
            sh("git", "tag", "-a", nombre, "-m", "v", ref, cwd=self.repo)

    def bash(self, codigo, huella=None):
        env = dict(os.environ, LEKSSO_INSTALAR_PRUEBAS="1", LEKSSO_INSTALAR_SOLO_FUNCIONES="1",
                   LEKSSO_PRUEBA_REPO=posix(self.repo), LEKSSO_PRUEBA_CLON=posix(os.path.join(self.d, "clon")),
                   LEKSSO_PRUEBA_CLAVE=self.linea, LEKSSO_PRUEBA_HUELLA=huella or self.huella, LEKSSO_PRUEBA_RAMA="origin/main")
        return subprocess.run(["bash", "-c", f'source "{posix(SCRIPT)}"; set +e; {codigo}'],
                              env=env, capture_output=True, text=True)

    def publicar(self):
        """El «origen» es el repositorio de prueba; el clon es la copia de trabajo del instalador."""
        sh("git", "-C", self.repo, "branch", "-M", "main")


class Version(Base):
    def test_elige_la_mas_alta_y_ignora_basura(self):
        # Orden por número (0.10.0 > 0.9.9), y a igual número alpha < beta < la versión normal (sin sufijo, desde la 0.1.47).
        # Lo que no es una etiqueta de versión (vX, con punto y coma) se ignora.
        for t in ("v0.1.0-alpha", "v0.9.0-alpha", "v0.9.9", "v0.10.0-alpha", "v0.10.0-beta", "v0.10.0", "vX", "v1.0.0-alpha;id"):
            sh("git", "tag", t, cwd=self.repo)
        r = self.bash("elegir_version ''")
        self.assertEqual(r.stdout.strip(), "v0.10.0", r.stderr)

    def test_version_pedida_se_valida(self):
        self.assertEqual(self.bash("elegir_version v0.1.4-alpha").stdout.strip(), "v0.1.4-alpha")
        self.assertEqual(self.bash("elegir_version v0.1.4").stdout.strip(), "v0.1.4")    # sin sufijo: válida desde la 0.1.47
        for malo in ("0.1.4", "v0.1.4;id", "v0.1.4-alpha; rm -rf /", "../x", "v0.1.4-alpha\n"):
            r = self.bash(f"elegir_version $'{malo.encode('unicode_escape').decode()}'")
            self.assertNotEqual(r.returncode, 0, malo)


class Verificacion(Base):
    def preparar(self):
        """Clona el repositorio de prueba como lo haría el instalador y devuelve el comando de verificación."""
        r = self.bash("preparar_clon")
        self.assertEqual(r.returncode, 0, r.stderr)

    def verificar(self, tag, huella=None):
        self.preparar()
        return self.bash(f"verificar_version {tag}", huella)

    def test_firma_buena(self):
        self.etiqueta("v0.1.1-alpha", self.oficial)
        r = self.verificar("v0.1.1-alpha")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Firma válida", r.stdout)

    def test_nombre_firmado_distinto_del_usado(self):
        self.etiqueta("v0.1.1-alpha", self.oficial)
        objeto = sh("git", "rev-parse", "v0.1.1-alpha", cwd=self.repo)
        sh("git", "update-ref", "refs/tags/v0.9.0-alpha", objeto, cwd=self.repo)     # firma buena, nombre ajeno
        r = self.verificar("v0.9.0-alpha")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("mismo nombre", r.stdout + r.stderr)

    def test_firmada_con_otra_clave(self):
        self.etiqueta("v0.1.1-alpha", self.otra)
        r = self.verificar("v0.1.1-alpha")
        self.assertNotEqual(r.returncode, 0)

    def test_sin_firmar(self):
        self.etiqueta("v0.1.1-alpha")
        self.assertNotEqual(self.verificar("v0.1.1-alpha").returncode, 0)

    def test_etiqueta_ligera(self):
        sh("git", "tag", "v0.1.1-alpha", cwd=self.repo)
        self.assertNotEqual(self.verificar("v0.1.1-alpha").returncode, 0)

    def test_la_clave_del_script_no_coincide_con_la_huella_esperada(self):
        self.etiqueta("v0.1.1-alpha", self.oficial)
        r = self.verificar("v0.1.1-alpha", huella="SHA256:" + "A" * 43)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("huella", r.stdout + r.stderr)

    def test_fuera_de_la_rama_principal(self):
        sh("git", "checkout", "-q", "-b", "ajena", cwd=self.repo)
        open(os.path.join(self.repo, "x"), "w").write("2")
        sh("git", "add", "x", cwd=self.repo)
        sh("git", "commit", "-q", "-m", "ajeno", cwd=self.repo)
        self.etiqueta("v0.1.2-alpha", self.oficial)
        sh("git", "checkout", "-q", "main", cwd=self.repo)
        r = self.verificar("v0.1.2-alpha")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rama principal", r.stdout + r.stderr)

    def test_la_clave_viene_del_script_no_del_repositorio(self):
        """Un atacante puede meter su propio config/allowed_signers en el repositorio: no debe servirle."""
        otra_pub = open(self.otra + ".pub").read().split()[:2]
        os.makedirs(os.path.join(self.repo, "config"))
        open(os.path.join(self.repo, "config", "allowed_signers"), "w").write(
            f'leksso-release namespaces="git" {otra_pub[0]} {otra_pub[1]}\n')
        sh("git", "add", "-A", cwd=self.repo)
        sh("git", "commit", "-q", "-m", "clave del atacante", cwd=self.repo)
        self.etiqueta("v0.1.3-alpha", self.otra)
        self.assertNotEqual(self.verificar("v0.1.3-alpha").returncode, 0)


if __name__ == "__main__":
    unittest.main()
