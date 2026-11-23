#!/usr/bin/env python3
"""Sustituye, en el repositorio sin red, los paquetes que la imagen de Debian ya trae EN OTRA VERSION por la versión de la imagen.

Por qué: el instalador usa a la vez la imagen de Debian (versiones de su fecha) y nuestro repositorio sin red (descargado después,
con versiones más nuevas). Si un mismo paquete está en los dos con versión distinta, apt elige la más nueva y deja el resto del
conjunto en la vieja: por ejemplo `grub-common` nuevo con `grub-efi-amd64-bin` viejo, que pide la versión exacta, y la instalación
de GRUB falla («paquetes con dependencias incumplidas»). Quitando de nuestro repositorio esos paquetes, el sistema se queda con las
versiones coherentes de la imagen y se actualiza solo en cuanto haya red.

Hay que SUSTITUIR y no solo quitar: al final de la instalación, postinstalar.sh deja de usar la imagen como fuente y se queda solo con
este repositorio; un paquete quitado sin reponer daría «no tiene un candidato para la instalación» (pasó con ca-certificates).

Uso: filtrar-repo-offline.py CARPETA_REPO IMAGEN_DEBIAN.iso      (necesita xorriso y dpkg-deb)
"""
import glob
import gzip
import os
import re
import subprocess
import sys
import tempfile


def leer(texto):
    """nombre -> {versión: ruta del .deb dentro de la imagen}"""
    d = {}
    for bloque in texto.split("\n\n"):
        n = re.search(r"^Package: (.+)$", bloque, re.M)
        v = re.search(r"^Version: (.+)$", bloque, re.M)
        f = re.search(r"^Filename: (.+)$", bloque, re.M)
        if n and v:
            d.setdefault(n.group(1), {})[v.group(1)] = f.group(1) if f else None
    return d


def paquetes_de_la_imagen(iso):
    """Nombre -> {versión: ruta del .deb} de todos los paquetes de la imagen (índices de sus componentes)."""
    pool = {}
    with tempfile.TemporaryDirectory() as tmp:
        lista = subprocess.run(["xorriso", "-indev", iso, "-find", "/dists", "-name", "Packages.gz"],
                               capture_output=True, text=True).stdout
        rutas = [l.strip().strip("'") for l in lista.splitlines() if l.strip().startswith("'/dists") and "binary-" in l]
        for i, ruta in enumerate(rutas):
            if "binary-amd64" not in ruta and "binary-all" not in ruta:
                continue
            dst = os.path.join(tmp, f"P{i}.gz")
            subprocess.run(["xorriso", "-osirrox", "on", "-indev", iso, "-extract", ruta, dst], capture_output=True)
            if os.path.exists(dst):
                with gzip.open(dst, "rt", encoding="utf-8", errors="replace") as f:
                    for n, vs in leer(f.read()).items():
                        pool.setdefault(n, {}).update(vs)
    return pool


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    repo, iso = argv[1], argv[2]
    pool = paquetes_de_la_imagen(iso)
    if not pool:
        print("ERROR: no pude leer los índices de paquetes de la imagen; no se filtra nada.", file=sys.stderr)
        return 1
    cambiados = []
    for deb in sorted(glob.glob(os.path.join(repo, "*.deb"))):
        info = subprocess.run(["dpkg-deb", "-f", deb, "Package", "Version"], capture_output=True, text=True).stdout
        n = re.search(r"^Package: (.+)$", info, re.M)
        v = re.search(r"^Version: (.+)$", info, re.M)
        if not (n and v):
            continue
        nombre, version = n.group(1), v.group(1)
        if nombre in pool and version not in pool[nombre]:
            vp = sorted(pool[nombre])[-1]
            ruta = pool[nombre][vp]
            if not ruta:
                print(f"AVISO: {nombre} no tiene ruta en la imagen; se deja el del repositorio.", file=sys.stderr)
                continue
            destino = os.path.join(repo, os.path.basename(ruta))
            r = subprocess.run(["xorriso", "-osirrox", "on", "-indev", iso, "-extract", "/" + ruta, destino], capture_output=True)
            if not os.path.exists(destino):
                print(f"AVISO: no pude sacar {ruta} de la imagen; se deja el del repositorio.", file=sys.stderr)
                continue
            os.remove(deb)
            cambiados.append((nombre, vp, version))
    print(f"Imagen: {len(pool)} paquetes. Sustituidos por la versión de la imagen (estaban en otra versión): {len(cambiados)}")
    for n, vp, vr in cambiados:
        print(f"  {n}: {vr} (repositorio) -> {vp} (imagen)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
