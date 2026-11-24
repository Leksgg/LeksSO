#!/usr/bin/env python3
"""Cambia el tema de color de todo el escritorio de LeksSO, sin reiniciar.

Los temas (Marea, Pizarra...) son archivos de colores por papel en /usr/local/share/leksso/temas. Aquí se
cambian, en la configuración del usuario, los colores del tema actual por los del nuevo (barra, terminal,
menús, avisos, bordes de ventana, bloqueo, colores de Qt) y se recarga lo que se puede recargar al momento.
Las ventanas propias (Archivos, Ajustes...) leen el tema activo cada vez que se abren.

Uso:
  leksso-tema listar            temas disponibles
  leksso-tema actual            el que está activo
  leksso-tema aplicar <tema>    cambia a ese tema
  leksso-tema reaplicar         vuelve a poner el tema elegido (lo usa la instalación tras copiar la configuración base)
  leksso-tema recargar          pide a la barra, los avisos y el compositor que lean de nuevo su configuración
"""
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, "/usr/local/lib/leksso-ui")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "ui"))
from leksso_ui import BASE, _CARPETAS, es_claro, mapa_de_colores, recolorear, tema_activo, tokens  # noqa: E402

CASA = os.path.expanduser("~")
ESTADO = os.path.join(CASA, ".config", "leksso", "tema")
# archivos del usuario que llevan colores (relativos a ~)
ARCHIVOS = [
    ".config/waybar/style.css", ".config/kitty/kitty.conf", ".config/sway/config",
    ".config/mako/config", ".config/fuzzel/fuzzel.ini", ".config/swaylock/config",
    ".config/qt6ct/colors/leksso.conf", ".config/pcmanfm-qt/default/settings.conf",
]


def disponibles():
    nombres = set()
    for carpeta in _CARPETAS:
        try:
            nombres |= {f[:-5] for f in os.listdir(carpeta) if f.endswith(".json") and f[:-5].isalnum()}
        except OSError:
            pass
    return sorted(nombres)


def recolorear_archivos(mapa):
    cambiados = 0
    for rel in ARCHIVOS:
        ruta = os.path.join(CASA, rel)
        try:
            texto = open(ruta, encoding="utf-8", newline="").read()
        except (OSError, UnicodeDecodeError):
            continue
        nuevo = recolorear(texto, mapa)
        if nuevo != texto:
            tmp = ruta + ".nuevo"
            open(tmp, "w", encoding="utf-8", newline="").write(nuevo)
            os.replace(tmp, ruta)
            cambiados += 1
    return cambiados


def entorno_de_sesion():
    """Variables para hablar con la sesión gráfica abierta aunque se llame desde fuera de ella (sudo, instalación)."""
    import glob
    env = dict(os.environ)
    uid = os.getuid()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    carpeta = env["XDG_RUNTIME_DIR"]
    if "SWAYSOCK" not in env:
        socks = sorted(glob.glob(os.path.join(carpeta, "sway-ipc.*.sock")))
        if socks:
            env["SWAYSOCK"] = socks[-1]
    if "WAYLAND_DISPLAY" not in env:
        socks = sorted(s for s in glob.glob(os.path.join(carpeta, "wayland-*")) if not s.endswith(".lock"))
        if socks:
            env["WAYLAND_DISPLAY"] = os.path.basename(socks[0])
    return env


def recargar():
    env = entorno_de_sesion()
    # kitty es un único proceso para todas las ventanas: SIGUSR1 le hace releer kitty.conf sin cerrarlas
    ordenes = [["pkill", "-USR2", "-u", str(os.getuid()), "waybar"], ["pkill", "-USR1", "-u", str(os.getuid()), "-x", "kitty"],
               ["makoctl", "reload"], ["swaymsg", "reload"],
               # el explorador guarda en memoria los iconos del tema anterior: se cierra y se abre de nuevo en su sitio
               ["leksso-zonas", "--explorador"]]
    for o in ordenes:
        try:
            subprocess.run(o, capture_output=True, timeout=30, env=env)
        except (OSError, subprocess.SubprocessError):
            pass


BLOQUEO_BASE = "/usr/share/leksso/bloqueo.png"
BLOQUEO_USUARIO = os.path.join(CASA, ".config", "leksso", "bloqueo.png")


def imagen_de_bloqueo(nombre):
    """La imagen de la pantalla de bloqueo lleva los colores del tema: para Marea sirve la del sistema; para los
    demás se genera una en la carpeta del usuario y swaylock apunta a ella."""
    ruta = os.path.join(CASA, ".config", "swaylock", "config")
    destino = BLOQUEO_BASE
    if nombre != BASE:
        generador = next((g for g in ("/usr/local/lib/leksso/generar-pantalla-bloqueo.py",
                                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "generar-pantalla-bloqueo.py"))
                          if os.path.exists(g)), None)
        r = subprocess.run(["python3", generador, BLOQUEO_USUARIO, nombre], capture_output=True) if generador else None
        if r is not None and r.returncode == 0:
            destino = BLOQUEO_USUARIO
    try:
        texto = open(ruta, encoding="utf-8", newline="").read()
    except OSError:
        return
    nuevo = "".join(("image=" + destino + ("\r\n" if l.endswith("\r\n") else "\n") if l.startswith("image=") else l)
                    for l in texto.splitlines(keepends=True))
    if nuevo != texto:
        open(ruta + ".nuevo", "w", encoding="utf-8", newline="").write(nuevo)
        os.replace(ruta + ".nuevo", ruta)


ICONOS_SISTEMA = "/usr/share/icons/LeksSO"
ICONOS_USUARIO = os.path.join(CASA, ".local", "share", "icons", "LeksSO")


def blanco_brillante(nombre):
    """kitty lleva el «blanco brillante» (color15) como blanco puro, que no es un papel del tema: en un tema claro sería
    invisible sobre el fondo, así que allí se pone el color del texto."""
    ruta = os.path.join(CASA, ".config", "kitty", "kitty.conf")
    try:
        texto = open(ruta, encoding="utf-8", newline="").read()
    except OSError:
        return
    color = "#" + tokens(nombre)["text"] if es_claro(nombre) else "#ffffff"
    nuevo = re.sub(r"(?m)^(color15\s+)#[0-9a-fA-F]{6}", lambda m: m.group(1) + color, texto)
    if nuevo != texto:
        open(ruta + ".nuevo", "w", encoding="utf-8", newline="").write(nuevo)
        os.replace(ruta + ".nuevo", ruta)


def iconos(nombre):
    """Los iconos llevan los colores del tema (cuerpo de archivo, carpeta, marcos). Con Marea sirven los del sistema; con
    otro tema se hace una copia en la carpeta del usuario, que tiene prioridad, con los colores cambiados. En un tema claro
    el texto de las etiquetas (que va sobre un color de tipo de archivo) pasa a ser oscuro."""
    if os.path.isdir(ICONOS_USUARIO):
        shutil.rmtree(ICONOS_USUARIO, ignore_errors=True)
    if nombre == BASE:
        return
    origen = next((d for d in (ICONOS_SISTEMA, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "iconos", "LeksSO"))
                   if os.path.isdir(d)), None)
    if not origen:
        return
    mapa = mapa_de_colores(BASE, nombre)
    if es_claro(nombre):
        mapa[tokens(BASE)["bg"]] = tokens(nombre)["text"]
    shutil.copytree(origen, ICONOS_USUARIO)
    for raiz, _, archivos in os.walk(ICONOS_USUARIO):
        for f in archivos:
            if f.endswith(".svg"):
                ruta = os.path.join(raiz, f)
                texto = open(ruta, encoding="utf-8", newline="").read()
                nuevo = recolorear(texto, mapa)
                if nuevo != texto:
                    open(ruta, "w", encoding="utf-8", newline="").write(nuevo)


def guardar(nombre):
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    # atómico (archivo nuevo + renombrar): así las ventanas abiertas, que vigilan la carpeta, se enteran del cambio
    open(ESTADO + ".nuevo", "w", encoding="utf-8").write(nombre + "\n")
    os.replace(ESTADO + ".nuevo", ESTADO)


def aplicar(destino, desde):
    if destino not in disponibles() or not tokens(destino):
        sys.exit(f"Tema desconocido: {destino}. Disponibles: {', '.join(disponibles())}")
    mapa = {} if desde == destino else mapa_de_colores(desde, destino)
    n = recolorear_archivos(mapa) if mapa else 0
    imagen_de_bloqueo(destino)
    blanco_brillante(destino)
    iconos(destino)
    guardar(destino)
    if n:
        recargar()
    return n


def main(a):
    if not a or a[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if a[0] == "listar":
        print("\n".join(disponibles()))
    elif a[0] == "actual":
        print(tema_activo())
    elif a[0] == "aplicar" and len(a) == 2:
        n = aplicar(a[1], tema_activo())
        print(f"Tema {a[1]} aplicado ({n} archivos). Las ventanas ya abiertas lo estrenan al abrirlas de nuevo.")
    elif a[0] == "recargar":
        recargar()
    elif a[0] == "reaplicar":
        # la instalación acaba de copiar la configuración base (colores de Marea): se vuelve a poner el tema elegido
        elegido = tema_activo()
        n = aplicar(elegido, BASE) if elegido != BASE else 0
        print(f"Tema {elegido} puesto de nuevo ({n} archivos).")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
