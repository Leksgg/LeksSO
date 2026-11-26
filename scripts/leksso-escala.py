#!/usr/bin/env python3
"""Tamaño de las cifras de la barra (Raxtor) y escala de todo el escritorio, guardados para el usuario.

Raxtor solo dibuja cifras, «:» y «%» (ver 65-leksso-raxtor.conf); las letras de al lado son Montserrat. Sus cifras son
más grandes de diseño que las letras de Montserrat al mismo tamaño, y en la barra se ven desproporcionadas. Aquí se
escalan SOLO esas cifras con una regla de fontconfig del usuario (matriz sobre la familia «Raxtor»): Pango, que dibuja
la barra, los avisos y el lanzador, la respeta. «Raxtor Titulos» (los títulos) es otra familia y no cambia.

La escala del escritorio es la de sway (`output * scale`): agranda todo, ventanas y letras. Ajustes → Pantallas
(wdisplays) también la cambia, pero no la guarda; esta sí, en ~/.config/sway/escala.conf (incluido por la
configuración de sway antes de local.conf, que sigue mandando).

Uso:
  leksso-escala actual                 muestra los dos valores
  leksso-escala cifras 75|85|100       tamaño de las cifras de Raxtor, en %
  leksso-escala escritorio 100|125|150|200
  leksso-escala reaplicar              escribe los archivos según lo guardado (lo usa la instalación)
"""
import json
import os
import subprocess
import sys

CIFRAS = (75, 85, 100)
ESCRITORIO = (100, 125, 150, 200)
DE_SERIE = {"cifras": 85, "escritorio": 100}

CASA = os.path.expanduser("~")
ESTADO = os.path.join(CASA, ".config", "leksso", "escala.json")
REGLA = os.path.join(CASA, ".config", "fontconfig", "conf.d", "66-leksso-cifras.conf")
SWAY = os.path.join(CASA, ".config", "sway", "escala.conf")

PLANTILLA_REGLA = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<!-- LeksSO (leksso-escala): las cifras de Raxtor al {pct} % para que casen con las letras de Montserrat. Se cambia en
     Apariencia; no editar a mano. -->
<fontconfig>
  <match target="font">
    <test name="family"><string>Raxtor</string></test>
    <edit name="matrix" mode="assign">
      <times>
        <name>matrix</name>
        <matrix><double>{f}</double><double>0</double><double>0</double><double>{f}</double></matrix>
      </times>
    </edit>
  </match>
</fontconfig>
"""


def leer():
    try:
        datos = json.load(open(ESTADO, encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    r = dict(DE_SERIE)
    if datos.get("cifras") in CIFRAS:
        r["cifras"] = datos["cifras"]
    if datos.get("escritorio") in ESCRITORIO:
        r["escritorio"] = datos["escritorio"]
    return r


def escribir_atomico(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta + ".nuevo", "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(ruta + ".nuevo", ruta)


def escribir(valores):
    escribir_atomico(ESTADO, json.dumps(valores) + "\n")
    if valores["cifras"] == 100:
        try:
            os.remove(REGLA)                # tamaño original: sin regla
        except FileNotFoundError:
            pass
    else:
        escribir_atomico(REGLA, PLANTILLA_REGLA.format(pct=valores["cifras"], f=valores["cifras"] / 100))
    escribir_atomico(SWAY, "# LeksSO (leksso-escala): escala del escritorio. Se cambia en Apariencia.\n"
                           f"output * scale {valores['escritorio'] / 100:g}\n")


def ejecutar(orden):
    try:
        subprocess.run(orden, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass


def main(a):
    if not a or a[0] in ("-h", "--help"):
        sys.exit(__doc__)
    valores = leer()
    if a[0] == "actual" and len(a) == 1:
        print(f"cifras {valores['cifras']}\nescritorio {valores['escritorio']}")
    elif a[0] == "reaplicar" and len(a) == 1:
        escribir(valores)
    elif a[0] in ("cifras", "escritorio") and len(a) == 2:
        permitidos = CIFRAS if a[0] == "cifras" else ESCRITORIO
        try:
            n = int(a[1].rstrip("%"))
        except ValueError:
            n = None
        if n not in permitidos:
            sys.exit(f"Valor no válido: {a[1]}. Opciones: {', '.join(map(str, permitidos))}")
        valores[a[0]] = n
        escribir(valores)
        if a[0] == "cifras":
            # waybar lee fontconfig al arrancar: se cierra y leksso-barra la vuelve a abrir sola
            ejecutar(["pkill", "-u", str(os.getuid()), "-x", "waybar"])
        else:
            ejecutar(["swaymsg", "output", "*", "scale", f"{n / 100:g}"])
        print(f"{a[0].capitalize()}: {n} %")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
