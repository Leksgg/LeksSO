#!/usr/bin/env python3
"""Codex dentro de la caja de IA (leksso-codex.sh): sin intérprete de órdenes propio, sin búsqueda web. Hallazgo 10 de la revisión
de la 0.1.52. Usa un «caja» y un «codex» de mentira que solo anotan con qué argumentos se les llama. Solo Linux.
Uso: python3 scripts/test_codex.py"""
import os
import subprocess
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(AQUI, "leksso-codex.sh")


@unittest.skipIf(os.name == "nt", "usa sh y programas falsos")
class LanzadorDeCodex(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        b = os.path.join(self.t, "bin")
        os.makedirs(b)
        with open(os.path.join(b, "caja"), "w") as f:                      # imprime un argumento por línea
            f.write('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n')
        with open(os.path.join(b, "codex"), "w") as f:                     # «codex login status» sale bien
            f.write("#!/bin/sh\nexit 0\n")
        for n in ("caja", "codex"):
            os.chmod(os.path.join(b, n), 0o755)
        self.env = dict(os.environ, PATH=b + os.pathsep + os.environ["PATH"], HOME=self.t, LEKSSO_CODEX_CASA=self.t + "/casa")
        self.env.pop("LEKSSO_CODEX_CON_SHELL", None)

    def lanzar(self, **extra):
        r = subprocess.run(["sh", SCRIPT], capture_output=True, text=True, env=dict(self.env, **extra))
        return r, r.stdout.splitlines()

    def test_por_defecto_arranca_sin_shell_propio(self):
        r, args = self.lanzar()
        self.assertEqual(r.returncode, 0, r.stderr)
        i = args.index("--disable")
        self.assertEqual(args[i + 1], "shell_tool")                         # equivale a -c features.shell_tool=false
        self.assertLess(args.index("codex"), i)                             # va como opción de codex, no de la caja
        self.assertEqual(r.stderr.strip(), "")                              # y sin avisos: es lo normal

    def test_sigue_dentro_de_la_caja_de_ia_con_red_pero_sin_los_archivos_del_usuario(self):
        _, args = self.lanzar()
        for esperado in ("--ia-asistente", "codex", "--red", "--rw"):
            self.assertIn(esperado, args)
        self.assertIn("danger-full-access", args)                           # su sandbox interno no funciona anidado en la caja
        self.assertEqual(args[args.index("--rw") + 1], self.t + "/casa")    # lo único que ve de su usuario
        self.assertNotIn("--search", args)                                  # sin búsqueda web propia

    def test_conecta_con_el_servidor_del_permisor_y_no_con_otro(self):
        _, args = self.lanzar()
        self.assertIn('mcp_servers.leksso.command="python3"', args)
        self.assertIn('mcp_servers.leksso.args=["/usr/local/lib/leksso-ia/mcp_permisor.py"]', args)

    def test_la_nota_para_codex_dice_que_no_tiene_interprete(self):
        _, args = self.lanzar()
        nota = [a for a in args if a.startswith("developer_instructions=")][0]
        self.assertIn("no tienes intérprete de órdenes propio", nota)
        self.assertIn("servidor MCP", nota)

    def test_quien_lo_pide_expresamente_recupera_el_shell_y_se_le_avisa(self):
        r, args = self.lanzar(LEKSSO_CODEX_CON_SHELL="1")
        self.assertNotIn("--disable", args)
        self.assertNotIn("shell_tool", args)
        self.assertIn("AVISO", r.stderr)
        self.assertIn("podría salir a cualquier servidor", r.stderr)

    def test_otro_valor_de_la_variable_no_lo_activa(self):
        for v in ("0", "si", "true", ""):
            _, args = self.lanzar(LEKSSO_CODEX_CON_SHELL=v)
            self.assertIn("--disable", args, v)

    def test_la_cabecera_explica_la_decision(self):
        t = open(SCRIPT, encoding="utf-8").read()
        self.assertIn("--disable shell_tool", t)
        self.assertIn("hallazgo 10", t)


if __name__ == "__main__":
    unittest.main()
