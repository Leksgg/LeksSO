"""Controladores y firmware de LeksSO: detecta el hardware, avisa de novedades y las instala.

Se usa desde `leksso-actualizar hardware ...` (no hay otra herramienta que aprender):

  leksso-actualizar hardware detectar          qué hardware hay y qué controlador le corresponde
  leksso-actualizar hardware comprobar         mira si hay novedades (no instala nada)
  sudo leksso-actualizar hardware aplicar      instala NVIDIA y firmware de dispositivos, con confirmación
  sudo leksso-actualizar hardware sistema      pone al día TODO: los paquetes del sistema (apt) y después lo de «aplicar»
  sudo leksso-actualizar hardware quitar-nvidia  vuelve al controlador libre (nouveau)
  leksso-actualizar hardware auto              (lo lanza el temporizador, como root) instala solo
                                              microcódigo y firmware de apt, y avisa del resto

Reglas de seguridad:
- Solo se instalan solos el microcódigo y el firmware que ya trae Debian (paquetes firmados por apt) y que
  ya estaban instalados. El controlador de NVIDIA y el firmware de dispositivos piden confirmación.
- Los nombres de paquete pasan siempre por una lista cerrada (SEGURO / NVIDIA); nada llega a un shell.
- Con Secure Boot activo no se instala NVIDIA: el módulo sin firmar no cargaría y quedaría sin imagen.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import sys
import time

ESTADO = "/var/lib/leksso/hardware.json"
AVISADO = "/var/lib/leksso/hardware-avisado"
MODPROBE = "/etc/modprobe.d/leksso-nvidia.conf"

# Lista cerrada de lo que puede instalarse sin preguntar, y de lo que solo se instala con confirmación.
SEGURO = re.compile(r"^(firmware-[a-z0-9][a-z0-9.+-]*|intel-microcode|amd64-microcode)\Z")
NVIDIA = re.compile(r"^(nvidia-[a-z0-9][a-z0-9.+-]*|libnvidia-[a-z0-9][a-z0-9.+-]*|xserver-xorg-video-nvidia)\Z")
PAQUETE = re.compile(r"^[a-z0-9][a-z0-9.+-]*\Z")

VENDEDORES = {"10de": "nvidia", "1002": "amd", "8086": "intel"}
ESPACIO_MINIMO = 3 * 1024 ** 3     # bytes libres en / antes de instalar NVIDIA


def ejecutar(cmd, tiempo=60, entrada=None):
    """Ejecuta una orden (lista, sin shell). Devuelve (código, salida). Sin traducir, para poder leerla.
    «entrada» va por la entrada estándar: lo secreto no debe ir en los argumentos (se ven con ps)."""
    env = dict(os.environ, LC_ALL="C", DEBIAN_FRONTEND="noninteractive")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tiempo, env=env, input=entrada)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 127, ""


# ---------- lectura del hardware (solo lectura, sin permisos) ----------
def parsear_gpus(salida):
    res = []
    for linea in salida.splitlines():
        if not re.search(r"VGA compatible controller|3D controller|Display controller", linea) or ": " not in linea:
            continue
        ids = re.findall(r"\[([0-9a-f]{4}):[0-9a-f]{4}\]", linea)
        nombre = linea.split(": ", 1)[1]
        nombre = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\].*$", "", nombre).strip()
        res.append({"vendedor": VENDEDORES.get(ids[-1] if ids else "", "otro"), "nombre": nombre})
    return res


def gpus():
    return parsear_gpus(ejecutar(["lspci", "-nn"])[1])


def es_maquina_virtual():
    rc, sal = ejecutar(["systemd-detect-virt"])
    return rc == 0 and sal.strip() not in ("", "none")


def secure_boot():
    """True / False, o None si no se puede saber."""
    rc, sal = ejecutar(["mokutil", "--sb-state"])
    t = sal.lower()
    if "enabled" in t:
        return True
    if "disabled" in t or "not supported" in t:
        return False
    return None


def recomendado_por_nvidia_detect(salida):
    m = re.search(r"recommended to install the\s+(\S+)\s+package", salida)
    return m.group(1) if m and NVIDIA.match(m.group(1)) else None


def paquete_nvidia():
    """Paquete que recomienda nvidia-detect; si no está instalado, el genérico."""
    rc, sal = ejecutar(["nvidia-detect"])
    return (recomendado_por_nvidia_detect(sal) if rc == 0 else None) or "nvidia-driver"


def version_instalada(nombre):
    rc, sal = ejecutar(["dpkg-query", "-W", "-f", "${db:Status-Abbrev} ${Version}", nombre])
    if rc == 0 and sal.startswith("ii "):
        return sal[3:].strip()
    return None


def version_candidata(nombre):
    rc, sal = ejecutar(["apt-cache", "policy", nombre])
    m = re.search(r"Candidate:\s*(\S+)", sal)
    return m.group(1) if rc == 0 and m and m.group(1) != "(none)" else None


def parsear_pendientes(salida):
    """Líneas `Inst paquete [vieja] (nueva ...)` de `apt-get -s upgrade`."""
    res = []
    for linea in salida.splitlines():
        m = re.match(r"^Inst (\S+)(?: \[([^\]]*)\])? \((\S+)", linea)
        if m and PAQUETE.match(m.group(1)):
            res.append({"nombre": m.group(1), "de": (m.group(2) or "").strip(), "a": m.group(3)})
    return res


def hosts_de_fuente(texto):
    """Los servidores que usa un archivo de fuentes de apt (formato clásico «deb …» o deb822 «URIs: …»)."""
    hosts = set()
    en_uris = False                      # deb822: «URIs:» puede seguir en las líneas siguientes (con sangría)
    for bruta in texto.splitlines():
        linea = bruta.strip()
        if linea.startswith("#") or not linea:
            en_uris = en_uris and bool(linea.startswith("#"))
            continue
        if en_uris and bruta[:1] in (" ", "\t"):
            urls = linea.split()
        elif linea.lower().startswith("uris:"):
            en_uris = True
            urls = linea.split(":", 1)[1].split()
        elif re.match(r"^deb(-src)?\s", linea):
            en_uris = False
            urls = [p for p in linea.split() if "://" in p]
        else:
            en_uris = False
            continue
        for u in urls:
            m = re.match(r"^(?:[a-z+]+)://(?:[^/@]*@)?([^/:]+)", u)
            hosts.add(m[1].lower() if m else u.lower())
    return hosts


def es_fuente_de_debian(texto):
    hosts = hosts_de_fuente(texto)
    return bool(hosts) and all(h == "debian.org" or h.endswith(".debian.org") for h in hosts)


def fuentes_debian():
    """Carpeta temporal con una copia de las fuentes de apt que son SOLO de debian.org (las demás quedan fuera)."""
    carpeta = tempfile.mkdtemp(prefix="leksso-fuentes-")
    candidatos = ["/etc/apt/sources.list"] + [os.path.join("/etc/apt/sources.list.d", n)
                                              for n in sorted(os.listdir("/etc/apt/sources.list.d"))
                                              if n.endswith((".list", ".sources"))] if os.path.isdir("/etc/apt/sources.list.d") else ["/etc/apt/sources.list"]
    for i, ruta in enumerate(candidatos):
        try:
            texto = open(ruta, encoding="utf-8").read()
        except OSError:
            continue
        if es_fuente_de_debian(texto):
            ext = ".sources" if ruta.endswith(".sources") else ".list"
            with open(os.path.join(carpeta, f"debian-{i}{ext}"), "w", encoding="utf-8") as f:
                f.write(texto)
    return carpeta


def pendientes_apt():
    return parsear_pendientes(ejecutar(["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"], 120)[1])


def parsear_firmware(salida):
    try:
        datos = json.loads(salida)
    except ValueError:
        return []
    res = []
    for d in datos.get("Devices", []) if isinstance(datos, dict) else []:
        rel = (d.get("Releases") or [{}])[0]
        res.append({"dispositivo": str(d.get("Name", "Dispositivo"))[:80], "version": str(rel.get("Version", ""))[:40]})
    return res


def firmware_pendiente():
    if not shutil.which("fwupdmgr"):
        return []
    rc, sal = ejecutar(["fwupdmgr", "get-updates", "--json", "--no-metadata-check"], 90)
    return parsear_firmware(sal) if rc == 0 else []


def en_bateria():
    """True si hay batería y el equipo no está enchufado."""
    base = "/sys/class/power_supply"
    try:
        nombres = os.listdir(base)
    except OSError:
        return False
    hay_bat, enchufado = False, False
    for n in nombres:
        try:
            tipo = open(f"{base}/{n}/type", encoding="utf-8").read().strip()
            if tipo == "Battery":
                hay_bat = True
            elif tipo == "Mains" and open(f"{base}/{n}/online", encoding="utf-8").read().strip() == "1":
                enchufado = True
        except OSError:
            continue
    return hay_bat and not enchufado


def datos_bios():
    """Fabricante, placa y versión de BIOS tal como las da el equipo (/sys/class/dmi/id). Vacío si no hay."""
    def lee(n):
        try:
            return open(f"/sys/class/dmi/id/{n}", encoding="utf-8").read().strip()
        except OSError:
            return ""
    placa = " ".join(x for x in (lee("board_vendor"), lee("board_name")) if x) or " ".join(x for x in (lee("sys_vendor"), lee("product_name")) if x)
    bios = " ".join(x for x in (lee("bios_vendor"), lee("bios_version")) if x)
    fecha = lee("bios_date")
    return f"{placa} · BIOS {bios}" + (f" ({fecha})" if fecha else "") if (placa or bios) else ""


def parsear_bios_fwupd(salida):
    """Salida de `fwupdmgr get-devices --json` -> True si el fabricante publica la BIOS de este equipo por fwupd,
    False si fwupd contesta y no la lista, None si no se sabe."""
    try:
        datos = json.loads(salida)
    except ValueError:
        return None
    disp = datos.get("Devices") if isinstance(datos, dict) else None
    if not isinstance(disp, list):
        return None
    for d in disp:
        nombre = str(d.get("Name", "")).lower()
        if "system firmware" in nombre or "uefi" in nombre and "dbx" not in nombre:
            return "updatable" in [str(x).lower() for x in d.get("Flags", [])] or None
    return False


def bios_por_fwupd():
    if not shutil.which("fwupdmgr"):
        return None
    rc, sal = ejecutar(["fwupdmgr", "get-devices", "--json", "--no-metadata-check"], 60)
    return parsear_bios_fwupd(sal) if rc == 0 else None


def estado_actual():
    """Foto de lo que hay y lo que está pendiente. Solo lectura."""
    g = gpus()
    pend = pendientes_apt()
    est = {"comprobado": int(time.time()), "virtual": es_maquina_virtual(), "secure_boot": secure_boot(),
           "gpus": g, "seguro": [p for p in pend if SEGURO.match(p["nombre"])], "nvidia": None,
           "firmware": firmware_pendiente(),
           # todo lo que apt tiene pendiente (no solo firmware), y la BIOS: qué hay y si llega por fwupd
           "paquetes": len(pend), "bios": {"texto": datos_bios(), "por_fwupd": bios_por_fwupd()}}
    if any(x["vendedor"] == "nvidia" for x in g):
        paq = paquete_nvidia()
        inst, cand = version_instalada(paq), version_candidata(paq)
        subida = [p for p in pend if NVIDIA.match(p["nombre"])]
        accion = None
        nf = non_free_activo()
        if not inst and (cand or not nf):       # sin non-free apt no lo ve: se ofrece y se activa al instalar
            accion = "instalar"
        elif inst and subida:
            accion = "actualizar"
        est["nvidia"] = {"paquete": paq, "instalado": inst, "candidato": cand, "accion": accion, "non_free": nf}
    return est


# ---------- orígenes de apt ----------
CON_NON_FREE = re.compile(r"(?<![\w-])non-free(?![\w-])")


def fuentes_apt():
    rutas = ["/etc/apt/sources.list"]
    try:
        rutas += [f"/etc/apt/sources.list.d/{n}" for n in sorted(os.listdir("/etc/apt/sources.list.d")) if n.endswith((".list", ".sources"))]
    except OSError:
        pass
    return [r for r in rutas if os.path.isfile(r)]


def non_free_activo():
    for r in fuentes_apt():
        try:
            for linea in open(r, encoding="utf-8"):
                s = linea.strip()
                if s.startswith(("deb ", "Components:")) and CON_NON_FREE.search(s):
                    return True
        except OSError:
            continue
    return False


def con_non_free(texto):
    """Añade la sección non-free a las líneas `deb ...` y `Components: ...` que tienen main."""
    salida = []
    for linea in texto.split("\n"):
        s = linea.lstrip()
        if (s.startswith(("deb ", "deb-src ")) or s.startswith("Components:")) and not CON_NON_FREE.search(s):
            linea = re.sub(r"(?<![\w-])main(?![\w-])", "main non-free", linea, count=1)
        salida.append(linea)
    return "\n".join(salida)


def activar_non_free():
    for r in fuentes_apt():
        try:
            antes = open(r, encoding="utf-8").read()
        except OSError:
            continue
        despues = con_non_free(antes)
        if despues != antes:
            shutil.copy2(r, r + ".leksso-bak")          # apt ignora esta extensión
            with open(r, "w", encoding="utf-8") as f:
                f.write(despues)


# ---------- avisos ----------
def textos_aviso(est, aplicados=()):
    """Lista de (clave, título, texto) en lenguaje llano. La clave evita repetir el mismo aviso."""
    av = []
    n = est.get("nvidia")
    if n and n["accion"] == "instalar":
        av.append((f"nvidia:instalar:{n['candidato']}", "Tu tarjeta NVIDIA puede usar el controlador oficial",
                   "Da más rendimiento en los juegos. Instálalo desde Ajustes → Actualizaciones: te pedirá confirmación y un reinicio."))
    elif n and n["accion"] == "actualizar":
        av.append((f"nvidia:actualizar:{n['candidato']}", "Hay un controlador NVIDIA más nuevo",
                   f"Versión {n['candidato']}. Instálalo desde Ajustes → Actualizaciones."))
    for f in est.get("firmware", []):
        av.append((f"fw:{f['dispositivo']}:{f['version']}", "Hay una actualización de firmware",
                   f"{f['dispositivo']} {f['version']}. Instálala desde Ajustes → Actualizaciones, con el equipo enchufado."))
    if aplicados:
        av.append(("auto:" + ",".join(sorted(aplicados)), "LeksSO actualizó el firmware del equipo",
                   f"Se actualizaron {len(aplicados)} paquetes de microcódigo y firmware. Se aplican del todo al reiniciar."))
    return av


def notificar_a_todos(titulo, texto):
    """Como root: envía la notificación a cada sesión de usuario abierta."""
    import pwd
    try:
        uids = [int(d) for d in os.listdir("/run/user") if d.isdigit() and int(d) >= 1000]
    except OSError:
        return
    for uid in uids:
        bus = f"/run/user/{uid}/bus"
        if not os.path.exists(bus):
            continue
        try:
            nombre = pwd.getpwuid(uid).pw_name
        except KeyError:
            continue
        ejecutar(["runuser", "-u", nombre, "--", "env", f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}",
                  "notify-send", "-a", "leksso-actualizar", "-t", "15000", titulo, texto], 15)


def escribir_atomico(ruta, contenido):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(contenido)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ruta)


def avisar(est, aplicados=()):
    try:
        ya = set(open(AVISADO, encoding="utf-8").read().split("\n"))
    except OSError:
        ya = set()
    nuevos = [a for a in textos_aviso(est, aplicados) if a[0] not in ya]
    for _, titulo, texto in nuevos:
        notificar_a_todos(titulo, texto)
    claves = {a[0] for a in textos_aviso(est, aplicados)}
    escribir_atomico(AVISADO, "\n".join(sorted(claves | (ya & {c for c in ya if c.startswith("auto:")}))))
    return len(nuevos)


# ---------- órdenes ----------
def raiz_o_salir():
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        sys.exit("Este paso necesita permisos de administrador: sudo leksso-actualizar hardware ...")


def auto():
    """Temporizador (root): actualiza solo microcódigo y firmware de apt ya instalados; avisa del resto."""
    raiz_o_salir()
    ejecutar(["apt-get", "update", "-qq", "-o", "DPkg::Lock::Timeout=120"], 300)   # sin red no pasa nada
    pend = pendientes_apt()
    nombres = sorted({p["nombre"] for p in pend if SEGURO.match(p["nombre"]) and version_instalada(p["nombre"])})
    aplicados = []
    if nombres:
        carpeta = fuentes_debian()      # solo los repositorios de Debian: un repositorio externo no puede colar un «candidato»
        try:
            rc, _ = ejecutar(["apt-get", "install", "-y", "-qq", "--only-upgrade", "-o", "DPkg::Lock::Timeout=120",
                              "-o", "Dir::Etc::SourceList=/dev/null", "-o", f"Dir::Etc::SourceParts={carpeta}", "--"] + nombres, 900)
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)
        if rc == 0:
            aplicados = nombres
    est = estado_actual()
    escribir_atomico(ESTADO, json.dumps(est, ensure_ascii=False, indent=1))
    avisar(est, aplicados)
    return 0


def detectar():
    est = estado_actual()
    print("Tarjetas gráficas:")
    for g in est["gpus"] or [{"vendedor": "?", "nombre": "ninguna detectada"}]:
        print(f"  · {g['nombre']} ({g['vendedor']})")
    print("Máquina virtual:", "sí" if est["virtual"] else "no")
    b = datos_bios()
    if b:
        print(f"Placa y BIOS: {b}")
        print("  (La BIOS solo se actualiza desde aquí si el fabricante la publica en fwupd; si no sale en la lista de")
        print("   firmware, hay que mirar su web de soporte.)")
    sb = est["secure_boot"]
    print("Secure Boot:", "activo" if sb else "no activo" if sb is False else "no se pudo comprobar")
    n = est["nvidia"]
    if n:
        print(f"NVIDIA: paquete {n['paquete']} · instalado {n['instalado'] or 'no'} · disponible {n['candidato'] or 'no (¿non-free?)'}"
              f" · non-free {'activo' if n['non_free'] else 'sin activar'}")
        print("  →", {"instalar": "puede instalarse", "actualizar": "hay versión nueva", None: "nada que hacer"}[n["accion"]])
    print(f"Microcódigo y firmware de apt pendientes: {len(est['seguro'])}")
    for p in est["seguro"]:
        print(f"  · {p['nombre']} {p['de']} → {p['a']}")
    print(f"Firmware de dispositivos pendiente: {len(est['firmware'])}")
    for f in est["firmware"]:
        print(f"  · {f['dispositivo']} {f['version']}")
    return 0


def comprobar():
    return detectar()


def preguntar(texto, si=False):
    if si:
        return True
    try:
        return input(f"{texto} [s/N] ").strip().lower() in ("s", "si", "sí", "y", "yes")
    except EOFError:
        return False


MOK_PUB = "/var/lib/dkms/mok.pub"      # certificado con el que DKMS firma los módulos (lo crea `dkms generate_mok`)


def interpretar_mok(existe, test_salida, nuevas_salida):
    """Estado de la clave de firma de módulos: sin-clave, registrada, pendiente (pedida, falta reiniciar) o sin-registrar."""
    if not existe:
        return "sin-clave"
    if "already enrolled" in test_salida.lower():
        return "registrada"
    nuevas = nuevas_salida.lower()
    if "[key" in nuevas and "empty" not in nuevas:
        return "pendiente"
    return "sin-registrar"


MOK_CONTRASENA = "/var/lib/leksso/mok-contrasena"       # contraseña de un solo uso (0600, solo root); se consulta en Ajustes
ALFABETO_MOK = "abcdefghjkmnpqrstuvwxyz23456789"        # sin letras que se confundan; el teclado de la pantalla azul es inglés


def generar_contrasena(n=8):
    import secrets
    return "".join(secrets.choice(ALFABETO_MOK) for _ in range(n))


def guardar_secreto(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texto)


def mok_contrasena():
    """Para Ajustes → Secure Boot (root): imprime la contraseña de un solo uso guardada, si la hay."""
    raiz_o_salir()
    try:
        print(open(MOK_CONTRASENA, encoding="utf-8").read().strip())
        return 0
    except OSError:
        print("No hay ninguna contraseña guardada: este equipo no ha necesitado registrar una clave.")
        return 1


def mok_resumen():
    """Estado para el panel de Ajustes (sin secretos), en JSON."""
    sb = secure_boot()
    return {"secure_boot": sb, "clave": mok_estado() if sb else "no-necesaria", "hay_contrasena": os.path.exists(MOK_CONTRASENA)}


def mok_estado():
    existe = os.path.exists(MOK_PUB)
    if not existe:
        return "sin-clave"
    return interpretar_mok(True, ejecutar(["mokutil", "--test-key", MOK_PUB])[1], ejecutar(["mokutil", "--list-new"])[1])


def preparar_mok(si=False):
    """Con Secure Boot, el módulo de NVIDIA solo carga si está firmado con una clave registrada en el equipo.
    Se hace ANTES de instalar el controlador, para no quedarse sin imagen. Devuelve 0 si ya se puede instalar,
    1 si algo falló o no se aceptó, 2 si hay que reiniciar para terminar el registro."""
    estado = mok_estado()
    if estado == "registrada":
        return 0
    if estado == "pendiente":
        print("La clave ya está pedida. Reinicia el equipo: en la pantalla azul elige «Enroll MOK», «Continue»,")
        print("«Yes», escribe la contraseña que elegiste y «Reboot». Después vuelve a ejecutar esta instalación.")
        return 2
    print("Tu equipo tiene Secure Boot activo. Para que el controlador de NVIDIA cargue, hay que registrar una clave")
    print("de firma en este equipo (una sola vez). La clave y la contraseña de un solo uso se crean solas: tú no")
    print("inventas nada. Solo tendrás que escribir esa contraseña, corta, en una pantalla azul al reiniciar.")
    print("Nada se instala hasta que la clave esté registrada.")
    if not preguntar("¿Registrar la clave ahora?", si):
        return 1
    ejecutar(["apt-get", "install", "-y", "-qq", "dkms", "openssl", "mokutil"], 600)
    if not os.path.exists(MOK_PUB):
        ejecutar(["dkms", "generate_mok"], 120)
    if not os.path.exists(MOK_PUB):
        print("✕ No se pudo crear la clave de firma. Revisa que dkms esté instalado.")
        return 1
    clave = generar_contrasena()
    hash_pw = ejecutar(["openssl", "passwd", "-6", "-stdin"], entrada=clave + "\n")[1].strip()     # formato crypt, el que acepta mokutil
    if not hash_pw.startswith("$6$"):
        print("✕ No se pudo preparar la contraseña de un solo uso.")
        return 1
    ruta_hash = MOK_CONTRASENA + ".hash"
    guardar_secreto(ruta_hash, hash_pw + "\n")
    rc = subprocess.run(["mokutil", "--import", MOK_PUB, "--hash-file", ruta_hash]).returncode
    os.remove(ruta_hash)
    if rc != 0:
        print("✕ No se pudo pedir el registro de la clave.")
        return 1
    guardar_secreto(MOK_CONTRASENA, clave + "\n")     # para poder consultarla luego en Ajustes → Secure Boot
    print("\n" + "=" * 46)
    print(f"  CONTRASEÑA DE UN SOLO USO:   {clave}")
    print("=" * 46)
    print("Apúntala o hazle una foto: la necesitarás en la pantalla azul. Más tarde también estará en")
    print("Ajustes → Secure Boot (oculta hasta que pulses «Ver»).\n")
    print("Reinicia el equipo. En la pantalla azul («MOK Manager») elige «Enroll MOK», «Continue», «Yes»,")
    print("escribe la contraseña y «Reboot». (El teclado de esa pantalla es el inglés: la contraseña solo")
    print("lleva letras y números.) Cuando el equipo arranque, vuelve a pulsar «Instalar controladores y")
    print("firmware»: esta vez instalará el de NVIDIA.")
    return 2


def problemas_antes_de_nvidia(est, ignorar_sb=False):
    p = []
    libre = shutil.disk_usage("/").free
    if libre < ESPACIO_MINIMO:
        p.append(f"Hay poco espacio libre ({libre // 1024 ** 2} MB); hacen falta unos {ESPACIO_MINIMO // 1024 ** 3} GB.")
    if en_bateria():
        p.append("Conecta el cargador antes de seguir.")
    return p


def instalar_nvidia(est, si=False, ignorar_sb=False, si_mok=False):
    n = est["nvidia"]
    problemas = problemas_antes_de_nvidia(est, ignorar_sb)
    for linea in problemas:
        print("✕", linea)
    if problemas:
        return 1
    if est["secure_boot"] and not ignorar_sb:
        r = preparar_mok(si or si_mok)
        if r:
            return r                # 1: falló o no se aceptó; 2: hay que reiniciar y volver a ejecutar
    if not n["non_free"]:
        print("El controlador de NVIDIA es software propietario (no libre) y está en la sección «non-free» de Debian.")
        if not preguntar("¿Activar esa sección en este equipo?", si):
            print("No se ha cambiado nada.")
            return 1
        activar_non_free()
        ejecutar(["apt-get", "update", "-qq"], 300)
    if not shutil.which("nvidia-detect"):
        ejecutar(["apt-get", "install", "-y", "-qq", "nvidia-detect"], 300)
    paq = paquete_nvidia()
    if not NVIDIA.match(paq) or not version_candidata(paq):
        print(f"✕ No hay un controlador disponible para tu tarjeta ({paq}).")
        return 1
    print(f"Se va a instalar {paq} {version_candidata(paq)} y las herramientas para compilarlo.")
    print("Se mantiene el núcleo anterior. Si tras reiniciar no hay imagen, en una consola (Ctrl+Alt+F3) escribe:")
    print("  sudo leksso-actualizar hardware quitar-nvidia")
    if not preguntar("¿Instalar ahora?", si):
        return 1
    arq = ejecutar(["dpkg", "--print-architecture"])[1].strip() or "amd64"
    rc, _ = ejecutar(["apt-get", "install", "-y", f"linux-headers-{arq}", paq], 1800)
    if rc != 0:
        print("✕ La instalación falló. No reinicies hasta revisar: sudo apt-get -f install")
        return 1
    escribir_atomico(MODPROBE, "# LeksSO: sway necesita el modo DRM del controlador de NVIDIA\noptions nvidia-drm modeset=1\n")
    # Decodificación de vídeo con la NVIDIA (VA-API). Va aparte: si falla, el controlador queda igualmente instalado.
    if ejecutar(["apt-get", "install", "-y", "-qq", "nvidia-vaapi-driver"], 600)[0] != 0:
        print("⚠ Sin nvidia-vaapi-driver: el vídeo no usará la NVIDIA. Después: sudo apt install nvidia-vaapi-driver")
    dk = ejecutar(["dkms", "status"])[1]
    if "nvidia" not in dk or "installed" not in dk:
        print("⚠ El módulo no aparece compilado en «dkms status». No reinicies hasta revisarlo.")
        return 1
    print("Listo. Reinicia el equipo para estrenar el controlador.")
    return 0


def aplicar(args):
    raiz_o_salir()
    si, ignorar_sb = "--si" in args, "--ignorar-secure-boot" in args
    est = estado_actual()
    hecho = False
    if est["nvidia"] and est["nvidia"]["accion"] in ("instalar", "actualizar"):
        hecho = True
        r = instalar_nvidia(est, si, ignorar_sb, "--si-mok" in args)
        if r == 2:
            return 0                # clave pedida: se reinicia y se vuelve a ejecutar; nada más que hacer ahora
        if r:
            return 1
    if est["seguro"]:
        hecho = True
        nombres = sorted({p["nombre"] for p in est["seguro"]})
        ejecutar(["apt-get", "install", "-y", "-qq", "--only-upgrade", "--"] + nombres, 900)
    if est["firmware"]:
        hecho = True
        if est["virtual"]:
            print("Es una máquina virtual: el firmware de dispositivos no se toca.")
        elif en_bateria():
            print("Conecta el cargador para actualizar el firmware de dispositivos.")
        else:
            for f in est["firmware"]:
                print(f"  · {f['dispositivo']} {f['version']}")
            print("Actualizar firmware de dispositivos no se puede deshacer. No apagues el equipo durante el proceso.")
            if preguntar("¿Actualizar ahora?", si):
                subprocess.run(["fwupdmgr", "update", "--assume-yes"])
    if not hecho:
        print("No hay nada que instalar.")
    escribir_atomico(ESTADO, json.dumps(estado_actual(), ensure_ascii=False, indent=1))
    return 0


def sistema(args):
    """Pone al día todo: paquetes del sistema (apt, de todos los repositorios configurados) y después NVIDIA y firmware."""
    raiz_o_salir()
    print("Buscando actualizaciones del sistema…", flush=True)
    subprocess.run(["apt-get", "update", "-o", "DPkg::Lock::Timeout=120"])
    print("\nInstalando las actualizaciones del sistema…", flush=True)
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    rc = subprocess.run(["apt-get", "-y", "--with-new-pkgs", "-o", "DPkg::Lock::Timeout=120",
                         "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold", "upgrade"], env=env).returncode
    if rc != 0:
        print("\nAVISO: apt ha terminado con errores; mira las líneas de arriba.", flush=True)
    print("\nControladores y firmware:", flush=True)
    r = aplicar(args)
    subprocess.run(["pkill", "-RTMIN+13", "waybar"], capture_output=True)      # el botón del raíl
    if os.path.exists("/var/run/reboot-required"):
        print("\nHay que REINICIAR el equipo para terminar (se ha actualizado el núcleo u otra pieza base).")
    return r or (1 if rc else 0)


def quitar_nvidia(args):
    raiz_o_salir()
    rc, sal = ejecutar(["dpkg-query", "-W", "-f", "${Package}\\n", "nvidia-*", "libnvidia-*"])
    nombres = [x for x in sal.split() if NVIDIA.match(x)]
    if not nombres:
        print("No hay controlador de NVIDIA instalado.")
        return 0
    print("Se quitará:", ", ".join(nombres))
    if not preguntar("¿Volver al controlador libre?", "--si" in args):
        return 1
    ejecutar(["apt-get", "purge", "-y", "--"] + nombres, 900)
    try:
        os.remove(MODPROBE)
    except OSError:
        pass
    print("Hecho. Reinicia el equipo: volverá el controlador libre (nouveau).")
    return 0


def main(a):
    c = a[0] if a else ""
    if c == "detectar":
        return detectar()
    if c == "comprobar":
        return comprobar()
    if c == "auto":
        return auto()
    if c == "aplicar":
        return aplicar(a[1:])
    if c == "sistema":
        return sistema(a[1:])
    if c == "quitar-nvidia":
        return quitar_nvidia(a[1:])
    if c == "mok":
        print(json.dumps(mok_resumen(), ensure_ascii=False))
        return 0
    if c == "mok-contrasena":
        return mok_contrasena()
    print(__doc__)
    return 2
