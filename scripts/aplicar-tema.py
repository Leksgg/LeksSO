#!/usr/bin/env python3
"""Aplica un tema de color de LeksSO a los archivos de configuración del repo.

Los colores se definen una sola vez, por papel (fondo, panel, acento, aviso...), y se
calculan en OKLCH para que acentos y estados tengan el mismo peso visual en todos los
matices. Este script cambia, en cada archivo, los colores del tema activo por los del
nuevo tema, y apunta cuál queda activo en config/tema/activo.

Temas: marea (la base con la que está pintado el repo), grafito (el de serie en los equipos), pizarra, waves, grisrosa
y purpura (oscuros), alba, blancorosa y blancopurpura (claros).

Uso:
  python3 aplicar-tema.py marea            aplica y deja los .json de tokens al día
  python3 aplicar-tema.py pizarra
  python3 aplicar-tema.py --comprobar      verifica contrastes y matices de todos los temas
  python3 aplicar-tema.py --json           escribe config/tema/<tema>.json de todos los temas sin tocar nada más
"""
import json
import math
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config"
ACTIVO = CONFIG / "tema" / "activo"

# Colores de antes de los temas (cian sobre azul grisáceo). Sirven de punto de partida.
HEREDADO = {
    "bg": "10151b", "s1": "171e27", "s2": "1c2530", "soft": "16384a", "line": "2a3644",
    "text": "dfe6ee", "muted": "8a98a8", "faint": "5a6877",
    "acc": "4cc3e0", "acc_hi": "7fd6ec", "acc_dim": "2f7f95", "sec": "8fa7ff", "magenta": "b59cf0",
    "ok": "58c987", "ok_soft": "173a26", "warn": "f0b24a", "warn_soft": "3a2d12", "warn_soft2": "2a2210",
    "bad": "f08a82", "bad_soft": "3a1d1d",
    "mid": "222c38", "dark": "0b0f14", "base2": "161d26", "alt": "151b23", "off": "141b23",
}

# nh/nc: matiz y croma de los neutros. ah: acento. sh: secundario.
# estados: matices candidatos; se elige el más lejano a acento y secundario.
TEMAS = {
    "marea":   {"nh": 205, "nc": .022, "ah": 192, "sh": 245, "magenta": 320},
    "pizarra": {"nh": 75,  "nc": .010, "ah": 238, "sh": 195, "magenta": 320},
    "waves":   {"nh": 265, "nc": .050, "ah": 240, "sh": 200, "magenta": 320},
    # claro: neutros casi blancos con un punto cálido, texto oscuro; los acentos bajan de luminosidad en vez de subir
    "alba":    {"nh": 85,  "nc": .012, "ah": 250, "sh": 195, "magenta": 320, "claro": True},
    # rosa: neutros grises con un punto rosado y acento rosa; el secundario va hacia el lila para no confundirse con el acento
    "grisrosa":   {"nh": 350, "nc": .008, "ah": 355, "sh": 295, "magenta": 310},
    "blancorosa": {"nh": 355, "nc": .008, "ah": 355, "sh": 295, "magenta": 310, "claro": True},
    # grafito (el de serie): neutros grises casi sin color, con un punto frío y algo más claros que los demás oscuros
    # (nl: cuánto suben); acento azul acero apagado (ac: croma del acento) y secundario lila, nada que tire a verde
    "grafito": {"nh": 255, "nc": .006, "ah": 245, "sh": 290, "magenta": 340, "ac": .09, "nl": .045},
    # púrpura: el de marca es #340091 (índigo profundo, matiz 284). En el claro es el acento tal cual (acc_hex). En el
    # oscuro no se leería como texto (1,4:1), así que es el relleno de selección y foco (soft_hex), los neutros se tiñen
    # de ese violeta y el acento de texto empieza oscuro (al) y sube solo hasta leerse (4,5:1). Colores vivos (vivo):
    # secundario azul eléctrico, magenta fucsia y estados radiantes. En el claro el aviso tira a ámbar (estados): un
    # amarillo puro solo se lee sobre blanco si se oscurece hasta el oliva.
    "purpura":       {"nh": 284, "nc": .045, "ah": 284, "sh": 235, "magenta": 345, "ac": .22, "al": .55, "soft_hex": "340091",
                      "vivo": True, "estados": {"warn": 100}},
    "blancopurpura": {"nh": 284, "nc": .012, "ah": 284, "sh": 235, "magenta": 345, "acc_hex": "340091", "claro": True,
                      "vivo": True, "estados": {"warn": 62}},
}
ESTADOS = {"ok": (138, 148, 158), "warn": (80, 88, 96), "bad": (20, 26, 32)}

# Archivos donde se cambian colores (relativos a la raíz). Los iconos van aparte: sus colores
# distinguen tipos de archivo, no son el tema.
EXTRA = ["scripts/generar-pantalla-bloqueo.py", "scripts/generar-iconos.py"]
SALTAR = {"iconos", "__pycache__"}


# ---------- OKLCH ----------
def _lineal(L, C, H):
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l = (L + .3963377774 * a + .2158037573 * b) ** 3
    m = (L - .1055613458 * a - .0638541728 * b) ** 3
    s = (L - .0894841775 * a - 1.291485548 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + .2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s,
            -.0041960863 * l - .7034186147 * m + 1.707614701 * s)


def _dentro(v):
    return all(-.0005 <= x <= 1.0005 for x in v)


def rgb(L, C, H):
    """OKLCH → (r,g,b) 0-255; si se sale de gamut baja el croma."""
    v = _lineal(L, C, H)
    if not _dentro(v):
        lo, hi = 0.0, C
        for _ in range(22):
            mid = (lo + hi) / 2
            if _dentro(_lineal(L, mid, H)):
                lo = mid
            else:
                hi = mid
        v = _lineal(L, lo, H)
    def cod(x):
        x = min(1.0, max(0.0, x))
        x = 12.92 * x if x <= .0031308 else 1.055 * x ** (1 / 2.4) - .055
        return round(x * 255)
    return tuple(cod(x) for x in v)


def hexa(c):
    return "%02x%02x%02x" % c


def lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2])


def contraste(a, b):
    x, y = lum(a), lum(b)
    return (max(x, y) + .05) / (min(x, y) + .05)


def dist_matiz(a, b):
    x = abs(a - b) % 360
    return min(x, 360 - x)


def ajustar(L, C, H, contra, minimo, paso=.01, sentido=1):
    """Cambia la luminosidad (sube con sentido=1, baja con -1) hasta que el color alcance `minimo` de contraste con `contra`."""
    c = rgb(L, C, H)
    while contraste(c, contra) < minimo and .02 < L < .99:
        L += paso * sentido
        c = rgb(L, C, H)
    return c


# ---------- tokens ----------
def tokens(nombre):
    t = TEMAS[nombre]
    nh, nc, ah, sh = t["nh"], t["nc"], t["ah"], t["sh"]
    claro = t.get("claro", False)
    nl = 0 if claro else t.get("nl", 0)
    N = lambda L, k=1: rgb(L + nl, nc * k, nh)
    if claro:
        r = {
            "bg": N(.955, .8), "s1": rgb(.995, nc * .3, nh), "s2": N(.925, .9), "line": N(.80, .9),
            "off": N(.97, .7), "alt": N(.945, .8), "base2": N(.935, .8), "mid": N(.90, .9), "dark": N(.98, .5),
            "text": rgb(.22, nc * 1.2, nh), "faint": rgb(.62, nc, nh),
            "soft": rgb(.90, .05, ah),
        }
        peor, sentido = r["mid"], -1   # fondo más oscuro sobre el que debe leerse todo; los colores bajan de luminosidad
    else:
        r = {
            "bg": N(.16), "s1": N(.20), "s2": N(.235), "line": N(.33, 1.2),
            "off": N(.18), "alt": N(.185), "base2": N(.195), "mid": N(.265), "dark": N(.115),
            "text": rgb(.94, nc * .5, nh), "faint": rgb(.55 + nl, nc * .8, nh),
            "soft": rgb(.30 + nl, .07, ah),
        }
        peor, sentido = r["s2"], 1
    luz = (lambda oscuro, claro_: claro_) if claro else (lambda oscuro, claro_: oscuro)
    r["muted"] = ajustar(luz(.70, .50), nc * .7, nh, peor, 4.5, sentido=sentido)
    ac = t.get("ac", .17)   # croma del acento; las variantes se escalan con él (con el de serie, .13 y .09 exactos)
    r["acc"] = ajustar(t.get("al", luz(.74, .55)), ac, ah, peor, 4.5, sentido=sentido)
    if "acc_hex" in t:
        r["acc"] = tuple(int(t["acc_hex"][i:i + 2], 16) for i in (0, 2, 4))
    if "soft_hex" in t:
        r["soft"] = tuple(int(t["soft_hex"][i:i + 2], 16) for i in (0, 2, 4))
    r["acc_hi"] = rgb(luz(.82, .45), .13 if ac == .17 else ac * .76, ah)
    r["acc_dim"] = rgb(luz(.55, .72), .09 if ac == .17 else ac * .53, ah)
    cerca = (ah, sh)
    def elegir(cands):
        return max(cands, key=lambda h: min(dist_matiz(x, h) for x in cerca))
    mt = {k: elegir(v) for k, v in ESTADOS.items()}
    mt.update(t.get("estados", {}))   # matices de estado fijados por el tema
    if t.get("vivo"):
        # vivo: secundario, magenta y estados al máximo croma que cabe en la pantalla (rgb() lo recorta al gamut),
        # empezando en la luminosidad más luminosa que se sigue leyendo: amarillo, rojo y verde radiantes, no mates
        V = .32
        r["sec"] = ajustar(luz(.74, .56), V, sh, peor, 4.5, sentido=sentido)
        r["magenta"] = ajustar(luz(.74, .56), V, t["magenta"], peor, 4.5, sentido=sentido)
        r["ok"] = ajustar(luz(.86, .62), V, mt["ok"], peor, 4.5, sentido=sentido)
        r["warn"] = ajustar(luz(.92, .70), V, mt["warn"], peor, 4.5, sentido=sentido)
        r["bad"] = ajustar(luz(.70, .60), V, mt["bad"], peor, 4.5, sentido=sentido)
    else:
        r["sec"] = ajustar(luz(.76, .55), .11, sh, peor, 4.5, sentido=sentido)
        r["magenta"] = ajustar(luz(.76, .52), .12, t["magenta"], peor, 4.5, sentido=sentido)
        r["ok"] = ajustar(luz(.78, .55), .15, mt["ok"], peor, 4.5, sentido=sentido)
        r["warn"] = ajustar(luz(.85, .60), .14, mt["warn"], peor, 4.5, sentido=sentido)
        r["bad"] = ajustar(luz(.72, .55), .18, mt["bad"], peor, 4.5, sentido=sentido)
    if t.get("vivo") and claro:
        # rellenos radiantes (el aviso, amarillo puro de fondo) con el texto del estado oscuro encima
        r["ok_soft"], r["warn_soft"] = rgb(.92, .20, mt["ok"]), rgb(.93, .20, 100)
        r["warn_soft2"], r["bad_soft"] = rgb(.89, .20, 100), rgb(.90, .10, mt["bad"])
    elif t.get("vivo"):
        r["ok_soft"], r["warn_soft"] = rgb(.28, .08, mt["ok"]), rgb(.28, .08, mt["warn"])
        r["warn_soft2"], r["bad_soft"] = rgb(.25, .07, mt["warn"]), rgb(.28, .10, mt["bad"])
    elif claro:
        r["ok_soft"], r["warn_soft"] = rgb(.92, .05, mt["ok"]), rgb(.93, .05, mt["warn"])
        r["warn_soft2"], r["bad_soft"] = rgb(.89, .045, mt["warn"]), rgb(.92, .05, mt["bad"])
    else:
        r["ok_soft"], r["warn_soft"] = rgb(.27, .05, mt["ok"]), rgb(.27, .05, mt["warn"])
        r["warn_soft2"], r["bad_soft"] = rgb(.25, .045, mt["warn"]), rgb(.27, .06, mt["bad"])
    return {k: hexa(v) for k, v in r.items()}, mt


def paleta(nombre):
    return HEREDADO if nombre == "heredado" else tokens(nombre)[0]


# ---------- comprobación ----------
def comprobar():
    fallos = 0
    for nombre, t in TEMAS.items():
        p, mt = tokens(nombre)
        c = {k: tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)) for k, v in p.items()}
        for k in ("text", "muted", "acc", "sec", "magenta", "ok", "warn", "bad"):
            for fondo in ("bg", "s1", "s2"):
                if contraste(c[k], c[fondo]) < 4.5:
                    print(f"CONTRASTE {nombre}: {k} sobre {fondo} = {contraste(c[k], c[fondo]):.2f}"); fallos += 1
        for e in ("ok", "warn", "bad"):
            if contraste(c[e], c[e + "_soft"]) < 4.5:
                print(f"CONTRASTE {nombre}: {e} sobre {e}_soft = {contraste(c[e], c[e + '_soft']):.2f}"); fallos += 1
            for a in (t["ah"], t["sh"]):
                if dist_matiz(a, mt[e]) < 30:
                    print(f"MATIZ {nombre}: {e} a {dist_matiz(a, mt[e])}° de un acento"); fallos += 1
        if len(set(p.values())) != len(p):
            print(f"REPETIDOS {nombre}: dos papeles con el mismo color"); fallos += 1
    print("Comprobación:", "sin problemas" if not fallos else f"{fallos} problemas")
    return fallos


# ---------- aplicar ----------
HEX = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{6,8}(?![0-9A-Za-z])")


def archivos():
    for ruta in sorted(CONFIG.rglob("*")):
        partes = ruta.relative_to(CONFIG).parts
        if ruta.is_file() and not (SALTAR & set(partes)) and partes[0] != "tema":
            yield ruta
    for e in EXTRA:
        yield RAIZ / e


def convertir(texto, mapa):
    def cambia(m):
        s, minus = m.group(0), m.group(0).lower()
        if len(s) == 6:
            return mapa.get(minus, s)
        if len(s) == 8:
            # ARGB de Qt (ffRRGGBB) o RGBA con alfa final (RRGGBBaa)
            if minus[:2] == "ff" and minus[2:] in mapa:
                return "ff" + mapa[minus[2:]]
            if minus[:6] in mapa:
                return mapa[minus[:6]] + minus[6:]
        return s
    texto = HEX.sub(cambia, texto)
    # tuplas RGB con su hex en el comentario: (16, 21, 27)  # #10151b. El comentario ya se
    # cambió arriba; la tupla se pone al día con él.
    def tupla(m):
        n = tuple(int(m.group(6)[i:i + 2], 16) for i in (0, 2, 4))
        return f"{m.group(1)}({n[0]}, {n[1]}, {n[2]}){m.group(5)}#{m.group(6)}"
    return re.sub(r"([A-Z_]+ = )\((\d+), (\d+), (\d+)\)(\s+# )#([0-9a-fA-F]{6})", tupla, texto)


def aplicar(destino):
    if destino not in TEMAS:
        sys.exit(f"Tema desconocido: {destino}. Opciones: {', '.join(TEMAS)}")
    actual = ACTIVO.read_text().strip() if ACTIVO.exists() else "heredado"
    viejo, nuevo = paleta(actual), paleta(destino)
    if len(set(viejo.values())) != len(viejo):
        sys.exit(f"El tema activo ({actual}) repite colores entre papeles; no se puede revertir con seguridad.")
    mapa = {viejo[k]: nuevo[k] for k in viejo}
    cambiados = 0
    for ruta in archivos():
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        salida = convertir(texto, mapa)
        if salida != texto:
            ruta.write_text(salida, encoding="utf-8", newline="")
            cambiados += 1
    ACTIVO.parent.mkdir(parents=True, exist_ok=True)
    ACTIVO.write_text(destino + "\n")
    for nombre in TEMAS:
        (ACTIVO.parent / f"{nombre}.json").write_text(
            json.dumps({"tema": nombre, "modo": "claro" if TEMAS[nombre].get("claro") else "oscuro", "colores": {k: "#" + v for k, v in tokens(nombre)[0].items()}},
                       indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Tema {destino} aplicado (antes: {actual}); {cambiados} archivos cambiados.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--json":
        for nombre in TEMAS:
            (ACTIVO.parent / f"{nombre}.json").write_text(
                json.dumps({"tema": nombre, "modo": "claro" if TEMAS[nombre].get("claro") else "oscuro", "colores": {k: "#" + v for k, v in tokens(nombre)[0].items()}},
                           indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        sys.exit(0)
    if sys.argv[1] == "--comprobar":
        sys.exit(1 if comprobar() else 0)
    aplicar(sys.argv[1])
