#!/usr/bin/env python3
"""Pruebas de mutación del permisor: rompe una defensa a propósito en una copia temporal y comprueba
que las pruebas lo detectan. Un mutante «vivo» es una defensa que ninguna prueba vigila.

Uso: python3 mutar.py [filtro]      (por ejemplo: python3 mutar.py firma)
El código real nunca se toca: todo ocurre en un directorio temporal.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).parent
PRUEBAS = ["test_nucleo", "test_ataques", "test_revision", "test_ejecutar"]   # las dos últimas tardan ~1 s

# (nombre, archivo, texto original, texto mutado)
MUTANTES = [
    ("sin O_NOFOLLOW al recorrer carpetas", "nucleo.py",
     "FLAGS_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW", "FLAGS_DIR = os.O_RDONLY | os.O_DIRECTORY"),
    ("acepta '..' en la ruta de cada acceso", "nucleo.py",
     'if not os.path.isabs(ruta) or ".." in Path(ruta).parts:', "if not os.path.isabs(ruta):"),
    ("acepta '..' al crear una carpeta nueva", "nucleo.py",
     'or "/" in nombre or ".." in Path(ruta).parts', 'or "/" in nombre'),
    ("deja usar archivos ocultos", "nucleo.py",
     'if any(x.startswith(".") for x in partes):', "if False:"),
    ("ignora los permisos r/w/d", "nucleo.py",
     'if perm not in info["perms"]:', "if False:"),
    ("una carpeta hermana cuenta como dentro", "nucleo.py",
     'p.startswith(raiz + "/")', "p.startswith(raiz)"),
    ("no comprueba la firma del registro", "nucleo.py",
     "if not isinstance(r, dict) or not hmac.compare_digest(str(r.get(\"firma\", \"\")), self._firma(r)):",
     "if not isinstance(r, dict):"),
    ("deshacer sin validar las rutas del registro", "nucleo.py",
     "self._validar_para_deshacer(a)", "pass"),
    ("acepta '..' como nombre en el registro", "nucleo.py",
     'x not in ("", ".", "..")', 'x not in ("", ".")'),
    ("deshacer pisa cambios posteriores sin avisar", "nucleo.py",
     "if cambio and not forzar:", "if False:"),
    ("permite conceder carpetas demasiado amplias", "nucleo.py",
     "if real in PROHIBIDAS or real == str(self.casa):", "if False:"),
    ("las tareas no caducan ni se cierran", "nucleo.py",
     "if t.cerrada or time.time() > t.expira:", "if False:"),
    ("lee archivos de cualquier tamaño", "nucleo.py",
     "or st.st_size > MAX_LEER:", ":"),
    ("los archivos nuevos salen ejecutables", "nucleo.py",
     "else 0o644", "else 0o755"),
    ("no quita caracteres invisibles", "nucleo.py",
     '_OCULTOS.subn("", texto)', "(texto, 0)"),
    ("escribe sobre algo que no es archivo normal", "nucleo.py",
     "if existia and not stat.S_ISREG(st.st_mode):", "if False:"),
    ("sin tope global de peticiones pendientes", "permisor.py",
     "if len(self.pendientes) >= MAX_PENDIENTES or self._del_canal(destino, asistente) >= MAX_PENDIENTES_CANAL:",
     "if self._del_canal(destino, asistente) >= MAX_PENDIENTES_CANAL:"),
    ("sin tope de peticiones pendientes por asistente", "permisor.py",
     "if len(self.pendientes) >= MAX_PENDIENTES or self._del_canal(destino, asistente) >= MAX_PENDIENTES_CANAL:",
     "if len(self.pendientes) >= MAX_PENDIENTES:"),
    ("sin tope de órdenes pendientes", "permisor.py",
     'if len(self.pendientes) >= MAX_PENDIENTES or self._del_canal("nube", asistente) >= MAX_PENDIENTES_CANAL:',
     "if False:"),
    ("sin tope de tareas abiertas", "permisor.py",
     "if len(self.n.tareas) >= MAX_TAREAS:", "if False:"),
    ("el destino lo declara la IA en el mensaje", "permisor.py",
     'self.pedir(m["titulo"], m["carpetas"], destino, asistente)',
     'self.pedir(m["titulo"], m["carpetas"], m.get("destino", "local"), asistente)'),
    ("la nube usa carpetas recordadas sin preguntar", "permisor.py",
     'if self._cubre_recordada(carpetas) and destino == "local":', "if self._cubre_recordada(carpetas):"),
    ("se recuerda el permiso de borrar", "permisor.py",
     '- {"d"}))', "))"),
    ("títulos con caracteres de control", "nucleo.py",
     'not in ("Cc", "Cf", "Cs", "Co", "Cn")', 'not in ("Co",)'),
    ("no resuelve las carpetas al pedirlas", "permisor.py",
     'carpetas = {k: "".join(sorted(v["perms"])) for k, v in raices.items()}', "pass"),
    ("sin tope de tamaño de escritura", "permisor.py",
     'or len(m["texto"]) > MAX_ESCRIBIR:', "or False:"),
    ("sin tope de tamaño de mensaje", "permisor.py",
     "if len(linea) > MAX_LINEA:", "if False:"),
]


def correr(carpeta):
    # un proceso por archivo de pruebas: test_revision y test_ejecutar fijan el entorno al importarse y no conviven
    # con test_ataques en el mismo proceso
    for prueba in PRUEBAS:
        try:
            r = subprocess.run([sys.executable, "-m", "unittest", prueba], cwd=carpeta, timeout=180,
                               env={**os.environ, "PYTHONPATH": str(carpeta), "LEKSSO_SIN_AVISOS": "1"}, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            return False                   # un mutante que cuelga el sistema también se detecta
        if r.returncode:
            return False
    return True


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    elegidos = [m for m in MUTANTES if filtro in m[0]]
    base = Path(tempfile.mkdtemp(prefix="leksso-mut-"))
    shutil.copytree(AQUI, base / "base", ignore=shutil.ignore_patterns("__pycache__", "*.sh"))
    if not correr(base / "base"):
        sys.exit("Las pruebas ya fallan sin mutar: arréglalas antes.")
    vivos, t0 = [], time.time()
    print(f"{len(elegidos)} mutantes, pruebas: {', '.join(PRUEBAS)}\n")
    for nombre, archivo, viejo, nuevo in elegidos:
        d = base / "m"
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(base / "base", d)
        texto = (d / archivo).read_text(encoding="utf-8")
        if texto.count(viejo) != 1:
            print(f"?? {nombre}: el texto original aparece {texto.count(viejo)} veces (mutante mal definido)")
            vivos.append((nombre, "mal definido"))
            continue
        (d / archivo).write_text(texto.replace(viejo, nuevo), encoding="utf-8")
        detectado = not correr(d)
        print(("detectado " if detectado else "VIVO      ") + nombre)
        if not detectado:
            vivos.append((nombre, "vivo"))
    shutil.rmtree(base, ignore_errors=True)
    print(f"\n{len(elegidos) - len(vivos)} de {len(elegidos)} detectados en {time.time() - t0:.0f} s")
    if vivos:
        print("Sin vigilar:\n- " + "\n- ".join(n for n, _ in vivos))
        sys.exit(1)


if __name__ == "__main__":
    main()
