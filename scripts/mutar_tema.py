#!/usr/bin/env python3
"""Pruebas de mutación de los temas de color: rompe a propósito una pieza de leksso-tema, del generador de
temas (aplicar-tema.py), de leksso_ui o del tema de serie de la instalación, en una copia temporal del
repositorio, y comprueba que las pruebas lo detectan. Un mutante «vivo» es una pieza que ninguna prueba vigila.

Mismo diseño que leksso-ia/mutar.py.
Uso: python3 scripts/mutar_tema.py [filtro]      (por ejemplo: python3 scripts/mutar_tema.py contraste)
El código real nunca se toca: todo ocurre en un directorio temporal.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PRUEBAS = ["scripts/test_tema.py", "scripts/test_ui_correcciones.py"]
UI, TEMA, GEN, PROV = "config/ui/leksso_ui.py", "scripts/leksso-tema.py", "scripts/aplicar-tema.py", "scripts/provision-base.sh"

# (nombre, archivo, texto original, texto mutado)
MUTANTES = [
    # leksso_ui: lo que usan las ventanas y leksso-tema
    ("acepta cualquier nombre de tema (rutas incluidas)", UI,
     "return nombre if nombre.isalnum() else BASE", "return nombre"),
    ("no cambia los colores ARGB de Qt (ffRRGGBB)", UI,
     'if minus[:2] == "ff" and minus[2:] in mapa:', "if False:"),
    ("no cambia los colores con alfa al final (RRGGBBaa)", UI,
     "if minus[:6] in mapa:", "if False:"),
    ("las ventanas propias no siguen el tema", UI,
     "return recolorear(texto, mapa_de_colores(BASE, activo))", "return texto"),
    ("confunde temas claros y oscuros", UI,
     '.get("modo") == "claro"', '.get("modo") == "oscuro"'),
    ("se olvida un papel al cambiar de tema (relleno de selección)", UI,
     "return {a[k]: b[k] for k in a if k in b}", 'return {a[k]: b[k] for k in a if k in b and k != "soft"}'),
    # leksso-tema
    ("acepta un tema que no existe", TEMA,
     "if destino not in disponibles() or not tokens(destino):", "if False:"),
    ("reaplicar no vuelve a poner el tema elegido", TEMA,
     "n = aplicar(elegido, BASE) if elegido != BASE else 0", "n = 0"),
    ("el blanco de la terminal no se oscurece en temas claros", TEMA,
     'if es_claro(nombre) else "#ffffff"', 'if False else "#ffffff"'),
    ("las etiquetas de los iconos siguen claras en temas claros", TEMA,
     'mapa[tokens(BASE)["bg"]] = tokens(nombre)["text"]', "pass"),
    ("quedan iconos del tema anterior", TEMA,
     "shutil.rmtree(ICONOS_USUARIO, ignore_errors=True)", "pass"),
    ("la pantalla de bloqueo no cambia de tema", TEMA,
     "imagen_de_bloqueo(destino)", "pass"),
    # aplicar-tema.py: el generador de los archivos de colores
    ("las variantes del acento cambian en los temas de siempre", GEN,
     ".13 if ac == .17 else ac * .76", "ac * .76"),
    ("ignora el acento fijo (#340091 en Blanco y púrpura)", GEN,
     'if "acc_hex" in t:', "if False:"),
    ("ignora el relleno fijo (#340091 en Púrpura)", GEN,
     'if "soft_hex" in t:', "if False:"),
    ("Grafito no aclara sus grises", GEN,
     'nl = 0 if claro else t.get("nl", 0)', "nl = 0"),
    ("no sube la luminosidad hasta alcanzar el contraste", GEN,
     "while contraste(c, contra) < minimo and .02 < L < .99:", "while False:"),
    ("elige el matiz de los estados sin mirar los acentos", GEN,
     "return max(cands, key=lambda h: min(dist_matiz(x, h) for x in cerca))", "return cands[0]"),
    ("la comprobación no mira el contraste", GEN,
     "if contraste(c[k], c[fondo]) < 4.5:", "if contraste(c[k], c[fondo]) < 1.0:"),
    ("la comprobación no mira que los estados se distingan del acento", GEN,
     "if dist_matiz(a, mt[e]) < 30:", "if False:"),
    ("la comprobación no mira los colores repetidos", GEN,
     "if len(set(p.values())) != len(p):", "if False:"),
    ("los púrpura pierden los colores vivos", GEN,
     'if t.get("vivo"):\n        # vivo:', 'if False:\n        # vivo:'),
    ("la comprobación no mira el texto de un estado sobre su relleno", GEN,
     'if contraste(c[e], c[e + "_soft"]) < 4.5:', "if False:"),
    # instalación
    ("el tema de serie no es Grafito", PROV,
     "echo grafito | U tee", "echo marea | U tee"),
    ("el tema de serie pisa el que eligió el usuario", PROV,
     'if [ ! -e "$HOME_USR/.config/leksso/tema" ]; then', "if true; then"),
]


def correr(carpeta):
    for prueba in PRUEBAS:
        try:
            r = subprocess.run([sys.executable, prueba], cwd=carpeta, timeout=180, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            return False                   # un mutante que cuelga también se detecta
        if r.returncode:
            return False
    return True


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    elegidos = [m for m in MUTANTES if filtro in m[0]]
    base = Path(tempfile.mkdtemp(prefix="leksso-mut-tema-"))
    ignorar = shutil.ignore_patterns(".git", "__pycache__", "leksso-ia")
    shutil.copytree(RAIZ, base / "base", ignore=ignorar)
    if not correr(base / "base"):
        shutil.rmtree(base, ignore_errors=True)
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
            vivos.append(nombre)
            continue
        (d / archivo).write_text(texto.replace(viejo, nuevo), encoding="utf-8")
        detectado = not correr(d)
        print(("detectado " if detectado else "VIVO      ") + nombre)
        if not detectado:
            vivos.append(nombre)
    shutil.rmtree(base, ignore_errors=True)
    print(f"\n{len(elegidos) - len(vivos)} de {len(elegidos)} detectados en {time.time() - t0:.0f} s")
    if vivos:
        print("Sin vigilar:\n- " + "\n- ".join(vivos))
        sys.exit(1)


if __name__ == "__main__":
    main()
