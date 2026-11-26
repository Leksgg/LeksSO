#!/usr/bin/env python3
"""Genera el tema de iconos LeksSO (SVG pequeños, uno por tipo de archivo).

Cada icono es una hoja con la esquina doblada y una banda de color por familia
(código, datos, imagen, vídeo...) con unas letras. El color es lo que distingue
a tamaño pequeño; las letras ayudan a tamaño grande. Hereda de Adwaita para todo
lo que no se define aquí.

Uso: python3 generar-iconos.py [carpeta_destino]   (por defecto config/iconos/LeksSO)
"""
import os
import sys

# familia: (color, [(etiqueta, [nombres de icono freedesktop que la usan])])
FAMILIAS = {
    "codigo": ("#5aa9e0", [
        ("PY", ["text-x-python", "text-x-python3", "application-x-python-bytecode"]),
        ("JS", ["text-javascript", "application-javascript", "text-x-javascript"]),
        ("TS", ["text-x-typescript", "application-typescript", "text-vnd.trolltech.linguist"]),
        ("C", ["text-x-csrc", "text-x-chdr"]),
        ("C++", ["text-x-c++src", "text-x-c++hdr"]),
        ("C#", ["text-x-csharp"]),
        ("JAVA", ["text-x-java", "application-x-java-archive"]),
        ("GO", ["text-x-go"]),
        ("RS", ["text-rust", "text-x-rust"]),
        ("PHP", ["application-x-php", "text-x-php"]),
        ("SH", ["application-x-shellscript", "text-x-script", "text-x-shellscript"]),
        ("GD", ["application-x-godot-script", "text-x-gdscript", "application-x-gdscript"]),
        ("TSCN", ["application-x-godot-scene"]),
        ("SQL", ["text-x-sql", "application-sql"]),
    ]),
    "web": ("#e8743b", [
        ("HTML", ["text-html", "application-xhtml+xml"]),
        ("CSS", ["text-css"]),
    ]),
    "datos": ("#e0a43a", [
        ("JSON", ["application-json", "application-x-json"]),
        ("XML", ["text-xml", "application-xml"]),
        ("YAML", ["application-x-yaml", "text-x-yaml", "application-yaml"]),
        ("TOML", ["application-toml", "text-x-toml"]),
        ("INI", ["text-x-ini", "application-x-desktop", "text-x-properties"]),
        ("CSV", ["text-csv", "text-x-csv"]),
    ]),
    "texto": ("#9aa8b8", [
        ("MD", ["text-markdown", "text-x-markdown"]),
        ("TXT", ["text-plain"]),
        ("LOG", ["text-x-log", "application-x-log"]),
    ]),
    "documento": ("#e05a5a", [
        ("PDF", ["application-pdf", "application-x-pdf"]),
        ("DOC", ["application-msword", "application-vnd.oasis.opendocument.text",
                 "application-vnd.openxmlformats-officedocument.wordprocessingml.document"]),
        ("XLS", ["application-vnd.ms-excel", "application-vnd.oasis.opendocument.spreadsheet",
                 "application-vnd.openxmlformats-officedocument.spreadsheetml.sheet"]),
        ("PPT", ["application-vnd.ms-powerpoint", "application-vnd.oasis.opendocument.presentation",
                 "application-vnd.openxmlformats-officedocument.presentationml.presentation"]),
    ]),
    "imagen": ("#5ac98f", [
        ("PNG", ["image-png"]),
        ("JPG", ["image-jpeg"]),
        ("SVG", ["image-svg+xml", "image-svg+xml-compressed"]),
        ("GIF", ["image-gif"]),
        ("WEBP", ["image-webp"]),
        ("IMG", ["image-x-generic", "image-bmp", "image-tiff", "image-x-icon", "image-vnd.microsoft.icon"]),
    ]),
    "video": ("#c46fd1", [
        ("MP4", ["video-mp4"]),
        ("MKV", ["video-x-matroska"]),
        ("VID", ["video-x-generic", "video-webm", "video-quicktime", "video-x-msvideo"]),
    ]),
    "audio": ("#e07fa8", [
        ("MP3", ["audio-mpeg"]),
        ("WAV", ["audio-x-wav", "audio-wav"]),
        ("AUD", ["audio-x-generic", "audio-ogg", "audio-flac", "audio-x-flac", "audio-aac", "audio-mp4"]),
    ]),
    "paquete": ("#d4a05a", [
        ("ZIP", ["application-zip", "application-x-zip"]),
        ("TAR", ["application-x-tar", "application-x-compressed-tar", "application-x-xz-compressed-tar"]),
        ("7Z", ["application-x-7z-compressed"]),
        ("RAR", ["application-vnd.rar", "application-x-rar"]),
        ("PKG", ["package-x-generic", "application-gzip", "application-x-xz", "application-x-bzip",
                 "application-x-bzip2", "application-x-deb", "application-vnd.debian.binary-package"]),
        ("ISO", ["application-x-cd-image", "application-x-iso9660-image", "application-vnd.efi.iso", "media-optical"]),
    ]),
    "programa": ("#7a86d9", [
        ("EXE", ["application-x-ms-dos-executable", "application-x-msdownload",
                 "application-vnd.microsoft.portable-executable", "application-x-dosexec"]),
        ("MSI", ["application-x-msi"]),
        ("BIN", ["application-x-executable", "application-x-sharedlib", "application-x-pie-executable",
                 "application-octet-stream"]),
        ("APP", ["application-vnd.appimage", "application-x-appimage"]),
    ]),
    "generico": ("#7d8896", [
        ("", ["text-x-generic", "text-x-generic-template", "application-x-generic", "unknown"]),
    ]),
}

HOJA = ('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
        '<path d="M10 4h20l10 10v28a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" fill="#27292c"/>'
        '<path d="M10 4h20l10 10v28a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" fill="none" '
        'stroke="{c}" stroke-width="1.5"/>'
        '<path d="M30 4v8a2 2 0 0 0 2 2h8z" fill="{c}" opacity=".55"/>'
        '{banda}</svg>\n')


def icono(etiqueta, color):
    if not etiqueta:
        banda = f'<path d="M15 24h18M15 29h18M15 34h12" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
    else:
        t = len(etiqueta)
        tam = 11 if t <= 3 else 8.5
        banda = (f'<rect x="8" y="24" width="32" height="13" fill="{color}"/>'
                 f'<text x="24" y="33.6" text-anchor="middle" font-family="DejaVu Sans,sans-serif" '
                 f'font-weight="700" font-size="{tam}" fill="#15171a">{etiqueta}</text>')
    return HOJA.format(c=color, banda=banda)


CARPETA = ('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
           '<path d="M4 10a2 2 0 0 1 2-2h12l4 5h20a2 2 0 0 1 2 2v25a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" fill="#2c6f86"/>'
           '<path d="M4 18a2 2 0 0 1 2-2h36a2 2 0 0 1 2 2v22a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" fill="#79b1e0"/>'
           '</svg>\n')

MARCO = ('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
         '<rect x="4" y="7" width="40" height="34" rx="3" fill="#27292c" stroke="#79b1e0" stroke-width="2"/>{dentro}</svg>\n')
APPS = {
    "utilities-terminal": MARCO.format(dentro='<path d="M12 18l8 6-8 6" fill="none" stroke="#79b1e0" stroke-width="3" '
                                      'stroke-linecap="round" stroke-linejoin="round"/>'
                                      '<path d="M24 32h12" stroke="#eaebed" stroke-width="3" stroke-linecap="round"/>'),
    "system-file-manager": MARCO.format(dentro='<path d="M4 15h40" stroke="#79b1e0" stroke-width="2"/>'
                                       '<path d="M17 15v26" stroke="#79b1e0" stroke-width="2"/>'
                                       '<path d="M8 21h6M8 27h6M8 33h6" stroke="#9d9ea1" stroke-width="2" stroke-linecap="round"/>'
                                       '<rect x="22" y="21" width="9" height="7" rx="1" fill="#79b1e0"/>'
                                       '<rect x="34" y="21" width="6" height="7" rx="1" fill="#2c6f86"/>'
                                       '<rect x="22" y="31" width="9" height="7" rx="1" fill="#2c6f86"/>'),
    "leksso-ia": MARCO.format(dentro='<path d="M24 13l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" fill="#79b1e0"/>'
                                    '<circle cx="35" cy="14" r="2" fill="#eaebed"/>'),
}

INDEX = """[Icon Theme]
Name=LeksSO
Comment=Iconos de tipos de archivo, ligeros y por colores
Inherits=Adwaita,hicolor
Directories=scalable/mimetypes,scalable/places,scalable/apps

[scalable/mimetypes]
Context=MimeTypes
Size=48
MinSize=16
MaxSize=512
Type=Scalable

[scalable/apps]
Context=Applications
Size=48
MinSize=16
MaxSize=512
Type=Scalable

[scalable/places]
Context=Places
Size=48
MinSize=16
MaxSize=512
Type=Scalable
"""


def main():
    raiz = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                           os.path.join(os.path.dirname(__file__), "..", "config", "iconos", "LeksSO"))
    mime = os.path.join(raiz, "scalable", "mimetypes")
    lugares = os.path.join(raiz, "scalable", "places")
    os.makedirs(mime, exist_ok=True)
    os.makedirs(lugares, exist_ok=True)
    n = 0
    for color, tipos in FAMILIAS.values():
        for etiqueta, nombres in tipos:
            svg = icono(etiqueta, color)
            for nombre in nombres:
                with open(os.path.join(mime, nombre + ".svg"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(svg)
                n += 1
    for nombre, destino in (("folder", lugares), ("user-home", lugares), ("inode-directory", mime)):
        with open(os.path.join(destino, nombre + ".svg"), "w", encoding="utf-8", newline="\n") as f:
            f.write(CARPETA)
        n += 1
    os.makedirs(os.path.join(raiz, "scalable", "apps"), exist_ok=True)
    for nombre, svg in APPS.items():
        with open(os.path.join(raiz, "scalable", "apps", nombre + ".svg"), "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        n += 1
    with open(os.path.join(raiz, "index.theme"), "w", encoding="utf-8", newline="\n") as f:
        f.write(INDEX)
    print(f"{n} iconos en {raiz}")


if __name__ == "__main__":
    main()
