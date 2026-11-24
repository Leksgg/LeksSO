#!/usr/bin/env python3
"""leksso-actualizar: versión de LeksSO y actualizaciones desde GitHub, con firma y con tu permiso.

  leksso-actualizar version [--detalle]  muestra la versión instalada (con --detalle, su commit y firma)
  leksso-actualizar comprobar [--avisar] mira si hay una versión nueva (y avisa con una notificación)
  leksso-actualizar barra                estado para la barra (lee lo ya comprobado, sin red)
  leksso-actualizar cambios [VERSIÓN]    qué trae la versión nueva
  sudo leksso-actualizar aplicar [VERSIÓN]   instala la versión nueva (solo si su firma es válida)
  sudo leksso-actualizar volver          vuelve a la versión anterior
  leksso-actualizar hardware ...         controladores y firmware (detectar, comprobar, aplicar...): ver `hardware`

Seguridad: solo se instalan versiones con etiqueta (vX.Y.Z, o vX.Y.Z-alpha/-beta/-rc las de prueba) firmadas con la clave de LeksSO que
ya está instalada en /etc/leksso/allowed_signers. Sin firma válida no se toca nada. Una subida normal
al repositorio nunca llega a un equipo: solo las versiones publicadas.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

REPO_URL = "https://github.com/Leksgg/LeksSO.git"
RAW_URL = "https://raw.githubusercontent.com/Leksgg/LeksSO/{tag}/CHANGELOG.md"
FICHERO_VERSION = "/etc/leksso-release"
FIRMANTES = "/etc/leksso/allowed_signers"
CLON = "/var/lib/leksso/repo"
ANTERIOR = "/var/lib/leksso/version-anterior"
SIN_FIRMA = "/etc/leksso/sin-firma"                # fase de pruebas: si existe, no se exige firma (lo crea el USB de pruebas)
INSTALADA = "/var/lib/leksso/instalada.json"      # versión, commit y firmante de lo instalado
RAMA_PRINCIPAL = "origin/main"
BLOQUEO = "/run/leksso-actualizar.lock"       # /run solo lo escribe root (en /run/lock cualquiera puede crear el archivo y bloquear)
CACHE = os.path.expanduser("~/.cache/leksso/actualizacion.json")
AVISADO = os.path.expanduser("~/.cache/leksso/avisado")

# Sin sufijo es una versión normal (la de todos los días); -alpha, -beta y -rc son las de prueba y van por debajo.
ETIQUETA = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc))?\Z")   # \Z: sin salto de línea final
RANGO = {"alpha": 0, "beta": 1, "rc": 2, None: 3}
NOMBRE = {"alpha": "Alpha", "beta": "Beta", "rc": "RC"}


def clave(v):
    """'0.1.1-alpha' o '0.1.48' → tupla ordenable. None si no es una versión válida."""
    m = ETIQUETA.match("v" + v) if v and not v.startswith("v") else ETIQUETA.match(v or "")
    if not m:
        return None
    return (int(m[1]), int(m[2]), int(m[3]), RANGO[m[4]])


def bonita(v):
    """'0.1.0-alpha' → 'Alpha 0.1.0'; '0.1.48' → '0.1.48'."""
    m = ETIQUETA.match("v" + v) if v and not v.startswith("v") else ETIQUETA.match(v or "")
    if not m:
        return v or "desconocida"
    numero = f"{m[1]}.{m[2]}.{m[3]}"
    return f"{NOMBRE[m[4]]} {numero}" if m[4] else numero


def version_actual():
    for ruta in (FICHERO_VERSION, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "VERSION")):
        try:
            v = open(ruta, encoding="utf-8").read().strip()
            if clave(v):
                return v
        except OSError:
            pass
    return None


def git(*args, cwd=None, entrada=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


def etiquetas_remotas():
    """Versiones publicadas en GitHub (solo nombres; la firma se comprueba al aplicar)."""
    r = git("ls-remote", "--tags", "--refs", REPO_URL, "refs/tags/v*")
    if r.returncode != 0:
        raise RuntimeError("No se pudo consultar GitHub (¿hay conexión?)")
    out = []
    for linea in r.stdout.splitlines():
        nombre = linea.split("refs/tags/")[-1].strip()
        if ETIQUETA.match(nombre):
            out.append(nombre[1:])
    return sorted(out, key=clave)


def ultima_mayor(actual):
    tags = etiquetas_remotas()
    ca = clave(actual) if actual else None
    nuevas = [t for t in tags if ca is None or clave(t) > ca]
    return nuevas[-1] if nuevas else None


def leer_cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def notificar(titulo, texto):
    try:
        subprocess.run(["notify-send", "-a", "leksso-actualizar", "-t", "15000", titulo, texto], timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def comprobar(avisar=False):
    actual = version_actual()
    disponible = ultima_mayor(actual)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"actual": actual, "disponible": disponible, "comprobado": int(time.time())}, f)
    # la barra solo lee esta caché: se le avisa al momento (si no, al iniciar sesión se quedaba con la caché vieja hasta el siguiente ciclo)
    subprocess.run(["pkill", "-RTMIN+11", "waybar"], capture_output=True)
    subprocess.run(["pkill", "-RTMIN+13", "waybar"], capture_output=True)      # el botón del raíl
    if not disponible:
        print(f"Estás al día: LeksSO {bonita(actual)}.")
        return 0
    print(f"Hay una versión nueva: LeksSO {bonita(disponible)} (instalada: {bonita(actual)}).")
    if avisar:
        ya = ""
        try:
            ya = open(AVISADO, encoding="utf-8").read().strip()
        except OSError:
            pass
        if ya != disponible:        # un solo aviso por versión
            notificar("Hay una versión nueva de LeksSO",
                      f"LeksSO {bonita(disponible)} está disponible (tienes {bonita(actual)}). "
                      "Pulsa el aviso de la barra de abajo o abre Ajustes para ver qué cambia.")
            with open(AVISADO, "w", encoding="utf-8") as f:
                f.write(disponible)
    return 0


def pendiente():
    """(versión nueva o None, versión instalada). La instalada se lee AHORA, no de la caché: tras actualizar, la caché
    aún guarda la versión de antes y el aviso se quedaba puesto aunque ya estuvieras por delante."""
    c = leer_cache()
    actual = version_actual() or c.get("actual")
    nueva = c.get("disponible")
    if nueva and clave(nueva) and actual and clave(actual) and clave(nueva) > clave(actual):
        return nueva, actual
    return None, actual


def sistema_pendiente(ruta="/var/lib/leksso/hardware.json"):
    """Cuántas cosas del sistema hay por instalar según la última comprobación diaria: paquetes de apt, NVIDIA y
    firmware de dispositivos. 0 si no hay nada o no se ha comprobado."""
    try:
        est = json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(est, dict):
        return 0
    n = est.get("paquetes") if isinstance(est.get("paquetes"), int) else len(est.get("seguro") or [])
    if (est.get("nvidia") or {}).get("accion"):
        n += 1
    return max(0, n) + len(est.get("firmware") or [])


def barra():
    nueva, actual = pendiente()
    if nueva:
        print(json.dumps({"text": f"↑ {bonita(nueva)}", "class": "hay",
                          "tooltip": f"Versión nueva: LeksSO {bonita(nueva)}\nInstalada: {bonita(actual)}\nClic para ver qué cambia."}))
    else:
        print(json.dumps({"text": "", "class": "al-dia"}))
    return 0


def riel():
    """El botón del raíl: siempre visible; se marca cuando hay una versión nueva."""
    nueva, actual = pendiente()
    icono = chr(0xF021)                 # flechas en círculo (Font Awesome)
    if nueva:
        ayuda = ["Versión nueva: LeksSO " + bonita(nueva), "Clic para ver qué cambia e instalarla."]
    else:
        ayuda = ["Actualizaciones"]
        if actual and clave(actual):
            ayuda.append("Tienes LeksSO " + bonita(actual) + ".")
    del_sistema = sistema_pendiente()
    if del_sistema:
        ayuda.append(f"Sistema y controladores: {del_sistema} por instalar.")
    print(json.dumps({"text": icono, "class": "hay" if (nueva or del_sistema) else "al-dia", "tooltip": chr(10).join(ayuda)}))
    return 0


_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")


def limpiar_para_terminal(texto):
    """Quita de un texto que viene de fuera lo que una terminal interpretaría como órdenes (secuencias con ESC, retrocesos,
    caracteres de control, marcas que cambian el sentido de lectura). Se queda con letras, símbolos, saltos de línea y
    tabuladores. El CHANGELOG se imprime ANTES de verificar ninguna firma, así que no puede ser de fiar."""
    return _CONTROL.sub("", (texto or "").replace("\r\n", "\n").replace("\r", "\n"))


def cambios(tag=None):
    c = leer_cache()
    v = tag or c.get("disponible")
    if not v or not clave(v):
        print("No hay una versión nueva que mostrar.")
        return 1
    url = RAW_URL.format(tag="v" + v.lstrip("v"))
    req = urllib.request.Request(url, headers={"User-Agent": "leksso-actualizar"})
    with urllib.request.urlopen(req, timeout=20) as r:
        texto = r.read(300000).decode("utf-8", "replace")
    # solo la parte más reciente: hasta la segunda cabecera de versión o de fecha
    lineas, vistas, dentro = [], 0, False
    for linea in texto.splitlines():
        if linea.startswith("## "):
            dentro = True
            vistas += 1
            if vistas > 2:
                break
        if dentro:
            lineas.append(linea)
    print(limpiar_para_terminal("\n".join(lineas[:80])))
    return 0


def raiz_o_salir():
    if os.geteuid() != 0:
        sys.exit("Este paso necesita permisos de administrador: sudo leksso-actualizar ...")


def preparar_clon():
    os.makedirs(os.path.dirname(CLON), exist_ok=True)
    if not os.path.isdir(os.path.join(CLON, ".git")):
        r = git("clone", "--no-checkout", REPO_URL, CLON)
        if r.returncode != 0:
            sys.exit("No se pudo descargar el repositorio: " + r.stderr.strip()[:200])
    # la copia de un equipo instalado desde USB apunta al paquete del USB: siempre se baja del repositorio oficial
    git("remote", "set-url", "origin", REPO_URL, cwd=CLON)
    r = git("fetch", "--tags", "--force", "origin", cwd=CLON)
    if r.returncode != 0:
        sys.exit("No se pudo actualizar la copia local: " + r.stderr.strip()[:200])


def verificar(tag):
    """Comprueba que la versión es legítima y devuelve (commit, huella de la firma). Si algo falla, no se sigue.

    1. La etiqueta está firmada con una clave de /etc/leksso/allowed_signers (la que ya hay instalada).
    2. El commit al que apunta pertenece a la rama principal del repositorio oficial.
    """
    if git("rev-parse", "-q", "--verify", f"refs/tags/{tag}", cwd=CLON).returncode != 0:
        sys.exit(f"No encuentro la versión {tag} en la copia descargada del repositorio (¿falló la descarga?).")
    sin_firma = os.path.exists(SIN_FIRMA)
    salida = ""
    if sin_firma:
        print("AVISO: equipo en FASE DE PRUEBAS (/etc/leksso/sin-firma): no se comprueba la firma de la versión.")
    else:
        if not os.path.exists(FIRMANTES):
            sys.exit(f"Falta {FIRMANTES}: no hay clave con la que comprobar la firma.")
        r = git("-c", f"gpg.ssh.allowedSignersFile={FIRMANTES}", "verify-tag", tag, cwd=CLON)
        salida = (r.stderr + r.stdout)
        if r.returncode != 0 or "Good \"git\" signature for " not in salida:   # «for»: la firma coincide con un firmante autorizado
            sys.exit(f"La versión {tag} NO tiene una firma válida. No se instala nada.\n{salida.strip()[:300]}")
    c = git("rev-list", "-n", "1", tag, cwd=CLON)
    commit = c.stdout.strip()
    if c.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        sys.exit(f"No se pudo identificar el commit de {tag}.")
    # El nombre que lleva DENTRO la etiqueta firmada debe ser el de la etiqueta que se usa: si no, alguien con
    # acceso al repositorio podría poner una versión antigua firmada bajo el nombre de una más nueva.
    cab = git("cat-file", "tag", tag, cwd=CLON)
    campos = dict(l.split(" ", 1) for l in cab.stdout.split("\n\n", 1)[0].splitlines() if " " in l)
    if cab.returncode != 0 or campos.get("tag") != tag or campos.get("type") != "commit" or campos.get("object") != commit:
        sys.exit(f"La etiqueta {tag} no es una etiqueta firmada con ese mismo nombre. No se instala nada.")
    anc = git("merge-base", "--is-ancestor", commit, RAMA_PRINCIPAL, cwd=CLON)
    if anc.returncode != 0:
        sys.exit(f"La versión {tag} no pertenece a la rama principal del repositorio. No se instala nada.")
    m = re.search(r"key (\S+:\S+)", salida)
    huella = m[1] if m else ""
    if sin_firma:
        print(f"Versión {tag} (commit {commit[:7]}, rama principal) SIN comprobar firma.")
        return commit, "sin-comprobar"
    print(f"Firma válida de la versión {tag} (commit {commit[:7]}, rama principal).")
    return commit, huella


def instalar_version(tag, usuario, commit="", huella=""):
    # Se instala EXACTAMENTE el commit que se verificó, no lo que el nombre de la etiqueta señale ahora.
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        sys.exit("Falta el commit verificado: no se instala.")
    r = git("checkout", "--force", "--detach", commit, cwd=CLON)
    if r.returncode != 0:
        sys.exit("No se pudo preparar la versión: " + r.stderr.strip()[:200])
    git("clean", "-fdx", cwd=CLON)
    if git("rev-parse", "HEAD", cwd=CLON).stdout.strip() != commit or git("status", "--porcelain", cwd=CLON).stdout.strip():
        sys.exit("La copia preparada no coincide con la versión verificada. No se instala nada.")
    script = os.path.join(CLON, "scripts", "provision-base.sh")
    print(f"Instalando LeksSO {bonita(tag.lstrip('v'))} (puede tardar unos minutos)…")
    p = subprocess.run(["bash", script, usuario])
    if p.returncode != 0:
        sys.exit("La instalación terminó con errores. Puedes volver con: sudo leksso-actualizar volver")
    tmp = FICHERO_VERSION + ".nuevo"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(tag.lstrip("v") + "\n")
    os.replace(tmp, FICHERO_VERSION)
    with open(INSTALADA + ".nuevo", "w", encoding="utf-8") as f:
        json.dump({"version": tag.lstrip("v"), "commit": commit, "firma": huella}, f)
    os.replace(INSTALADA + ".nuevo", INSTALADA)


def usuario_real():
    u = os.environ.get("SUDO_USER")
    if not u or u == "root":
        sys.exit("Ejecuta con sudo desde tu usuario: sudo leksso-actualizar aplicar")
    return u


def bloquear():
    """Una sola instalación o actualización a la vez: dos a la vez compartirían la misma copia del repositorio."""
    import fcntl
    os.makedirs(os.path.dirname(BLOQUEO), exist_ok=True)
    f = open(BLOQUEO, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Ya hay otra instalación o actualización de LeksSO en marcha.")
    return f


def aplicar(tag=None):
    raiz_o_salir()
    _cerrojo = bloquear()
    usuario = usuario_real()
    actual = version_actual()
    destino = (tag or "").lstrip("v") or ultima_mayor(actual)
    if not destino or not clave(destino):
        print("No hay ninguna versión nueva.")
        return 0
    if actual and clave(destino) <= clave(actual):
        sys.exit(f"{bonita(destino)} no es más nueva que la instalada ({bonita(actual)}).")
    etiqueta = "v" + destino
    preparar_clon()
    commit, huella = verificar(etiqueta)
    os.makedirs(os.path.dirname(ANTERIOR), exist_ok=True)
    with open(ANTERIOR, "w", encoding="utf-8") as f:
        f.write((actual or "") + "\n")
    instalar_version(etiqueta, usuario, commit, huella)
    print(f"\nListo: LeksSO {bonita(destino)}. Cierra la sesión y vuelve a entrar para estrenar todo.")
    return 0


def volver():
    raiz_o_salir()
    _cerrojo = bloquear()
    usuario = usuario_real()
    try:
        previa = open(ANTERIOR, encoding="utf-8").read().strip()
    except OSError:
        sys.exit("No hay una versión anterior guardada.")
    if not clave(previa):
        sys.exit("La versión anterior guardada no es válida.")
    preparar_clon()
    commit, huella = verificar("v" + previa)
    actual = version_actual()
    instalar_version("v" + previa, usuario, commit, huella)
    with open(ANTERIOR, "w", encoding="utf-8") as f:
        f.write((actual or "") + "\n")
    print(f"\nVuelves a LeksSO {bonita(previa)}. Cierra la sesión y vuelve a entrar.")
    return 0


def reinstalar():
    """Vuelve a instalar la versión que ya tienes (repara archivos de LeksSO dañados o cambiados), con su firma comprobada."""
    raiz_o_salir()
    _cerrojo = bloquear()
    usuario = usuario_real()
    actual = version_actual()
    if not actual or not clave(actual):
        sys.exit("No consta qué versión de LeksSO hay instalada.")
    preparar_clon()
    commit, huella = verificar("v" + actual)
    instalar_version("v" + actual, usuario, commit, huella)
    print(f"\nLeksSO {bonita(actual)} reinstalada. Cierra la sesión y vuelve a entrar.")
    return 0


def modulo_hardware():
    """Carga leksso_hardware.py, instalado junto a las bibliotecas de LeksSO o al lado de este script."""
    for carpeta in ("/usr/local/lib/leksso", os.path.dirname(os.path.abspath(__file__))):
        if os.path.exists(os.path.join(carpeta, "leksso_hardware.py")):
            sys.path.insert(0, carpeta)
            break
    import leksso_hardware
    return leksso_hardware


def main(a):
    if not a or a[0] in ("-h", "--help", "ayuda"):
        print(__doc__)
        return 0
    c = a[0]
    try:
        if c == "version":
            v = a[1] if len(a) > 1 and clave(a[1]) else version_actual()   # con un argumento, solo le da nombre
            texto = f"LeksSO {bonita(v)}" if v else "LeksSO (versión desconocida)"
            if "--detalle" in a:
                try:
                    d = json.load(open(INSTALADA, encoding="utf-8"))
                    if d.get("commit"):
                        texto += f" · commit {d['commit'][:7]} · firmada {d.get('firma', '')}".rstrip()
                except (OSError, ValueError):
                    pass
            print(texto)
            return 0
        if c == "comprobar":
            return comprobar("--avisar" in a)
        if c == "barra":
            return barra()
        if c == "riel":
            return riel()
        if c == "cambios":
            return cambios(a[1] if len(a) > 1 else None)
        if c == "aplicar":
            return aplicar(a[1] if len(a) > 1 else None)
        if c == "volver":
            return volver()
        if c == "reinstalar":
            return reinstalar()
        if c == "hardware":
            return modulo_hardware().main(a[1:])
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
