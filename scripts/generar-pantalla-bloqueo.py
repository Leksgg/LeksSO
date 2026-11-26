#!/usr/bin/env python3
"""Genera la imagen de la pantalla de bloqueo de LeksSO: un mensaje claro de que está bloqueada y qué hacer.

Se coloca centrada sobre el color de fondo; el anillo de la contraseña de swaylock queda justo debajo.
Uso: python3 generar-pantalla-bloqueo.py [destino] [tema]   (por defecto /usr/share/leksso/bloqueo.png y el tema base, Grafito)
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, "/usr/local/lib/leksso-ui")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "ui"))
from leksso_ui import BASE, tokens  # noqa: E402


def colores(tema):
    """(fondo, acento, texto, apagado) del tema, sacados de sus papeles."""
    t = tokens(tema) or tokens(BASE)
    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return rgb(t["bg"]), rgb(t["acc"]), rgb(t["text"]), rgb(t["muted"])


def fuente(tam, negrita=False):
    nombre = "DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf"
    for base in ("/usr/share/fonts/truetype/dejavu", "C:/Windows/Fonts", "/usr/share/fonts/TTF"):
        ruta = os.path.join(base, nombre)
        if os.path.exists(ruta):
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default()


def centrado(d, y, texto, f, color, ancho):
    caja = d.textbbox((0, 0), texto, font=f)
    d.text(((ancho - (caja[2] - caja[0])) // 2, y), texto, font=f, fill=color)


def main(destino, tema=BASE):
    FONDO, CIAN, TEXTO, APAGADO = colores(tema)
    ancho, alto = 1000, 720
    img = Image.new("RGB", (ancho, alto), FONDO)
    d = ImageDraw.Draw(img)
    centrado(d, 30, "LeksSO", fuente(64, True), CIAN, ancho)
    centrado(d, 118, "Pantalla bloqueada", fuente(30), TEXTO, ancho)
    centrado(d, 164, "Escribe tu contraseña y pulsa Intro", fuente(22), APAGADO, ancho)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    img.save(destino)
    print(f"Imagen creada: {destino}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/leksso/bloqueo.png", sys.argv[2] if len(sys.argv) > 2 else BASE)
