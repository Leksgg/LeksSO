#!/usr/bin/env python3
"""leksso-apps: instala en LeksSO los equivalentes de las aplicaciones habituales de Windows.

  leksso-apps                       lista por grupos, con lo que ya está instalado
  leksso-apps instalar NOMBRE...    instala por nombre (de Linux o de Windows) o por grupo
  leksso-apps instalar --todo       instala todo lo automático y oficial (pide confirmación)
  leksso-apps instalar --completo   igual, pero incluye también las alternativas de terceros (LibreOffice, Heroic...)
  leksso-apps pendientes            lo que no se puede instalar con un comando y por qué
  Opciones: --simular (solo muestra lo que haría), --si (no pregunta)

Fuentes: paquetes de Debian, repositorios firmados del proveedor (Brave, VS Code),
descargas directas .deb del proveedor (Discord, Obsidian, Heroic, r2modman),
descargas comprobadas por su suma (Proton, umu-launcher) y npm (Claude Code, Codex). Nada se ejecuta sin que lo pidas.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

# (grupo, id, equivale a (Windows), tipo, objetivo, comprobación, nota)
# tipos: apt, repo-brave, repo-vscode, steam, deb-url, deb-github, deb-proton, vpn-proton, umu, npm, script, vscode-ext, manual
CATALOGO = [
    # Desarrollo
    ("Desarrollo", "git", "Git", "apt", "git", "git", ""),
    ("Desarrollo", "gh", "GitHub CLI", "apt", "gh", "gh", ""),
    ("Desarrollo", "nodejs", "Node.js", "apt", "nodejs npm", "nodejs", "Versión de Debian (20)."),
    ("Desarrollo", "python", "Python", "apt", "python3 python3-pip python3-venv", "python3-pip", ""),
    ("Desarrollo", "rustup", "Rustup", "apt", "rustup", "rustup", "Después: rustup default stable"),
    ("Desarrollo", "ripgrep", "RipGrep", "apt", "ripgrep", "ripgrep", ""),
    ("Desarrollo", "compilador", "Visual Studio Build Tools", "apt", "build-essential", "build-essential", "gcc, make, etc."),
    ("Desarrollo", "docker", "Docker Desktop", "docker", "docker.io docker-compose docker-buildx", "docker.io",
     "Docker Engine con compose y buildx. Te añade al grupo docker (equivale a permisos de administrador); cierra sesión después."),
    ("Desarrollo", "code", "Visual Studio Code", "repo-vscode", "code", "code", "Repositorio firmado de Microsoft."),
    ("Desarrollo", "playwright", "Playwright", "playwright", "playwright", "playwright",
     "Automatización y pruebas de navegador. Instala Node, las librerías del sistema y Chromium."),
    ("Desarrollo", "tesseract", "Tesseract-OCR", "apt", "tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng", "tesseract-ocr", ""),
    ("Desarrollo", "filezilla", "FileZilla", "apt", "filezilla", "filezilla", ""),
    # Extensiones de VS Code (se instalan para el usuario, no para root; hace falta VS Code)
    ("Extensiones de VS Code", "vscode-ia", "Extensiones: IA y asistentes", "vscode-ext", "anthropic.claude-code continue.continue openai.chatgpt openai.codex-audio ollama.ollama", "anthropic.claude-code continue.continue openai.chatgpt openai.codex-audio ollama.ollama", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-python", "Extensiones: Python y datos", "vscode-ext", "ms-python.python ms-python.debugpy ms-python.vscode-pylance ms-python.vscode-python-envs ms-toolsai.jupyter ms-toolsai.jupyter-keymap ms-toolsai.jupyter-renderers ms-toolsai.vscode-jupyter-cell-tags ms-toolsai.vscode-jupyter-slideshow mechatroner.rainbow-csv nespinozacr.mysql-autocomplete", "ms-python.python ms-python.debugpy ms-python.vscode-pylance ms-python.vscode-python-envs ms-toolsai.jupyter ms-toolsai.jupyter-keymap ms-toolsai.jupyter-renderers ms-toolsai.vscode-jupyter-cell-tags ms-toolsai.vscode-jupyter-slideshow mechatroner.rainbow-csv nespinozacr.mysql-autocomplete", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-js", "Extensiones: JavaScript y Node", "vscode-ext", "dbaeumer.vscode-eslint esbenp.prettier-vscode orta.vscode-jest connor4312.nodejs-testing ms-playwright.playwright msjsdiag.vscode-react-native astro-build.astro-vscode wallabyjs.quokka-vscode wix.vscode-import-cost pflannery.vscode-versionlens mikestead.dotenv afractal.node-essentials chris-noring.node-snippets swellaby.node-pack christian-kohler.npm-intellisense christian-kohler.path-intellisense ionutvmi.path-autocomplete jasonnutter.search-node-modules leizongmin.node-module-intellisense tgreen7.vs-code-node-require", "dbaeumer.vscode-eslint esbenp.prettier-vscode orta.vscode-jest connor4312.nodejs-testing ms-playwright.playwright msjsdiag.vscode-react-native astro-build.astro-vscode wallabyjs.quokka-vscode wix.vscode-import-cost pflannery.vscode-versionlens mikestead.dotenv afractal.node-essentials chris-noring.node-snippets swellaby.node-pack christian-kohler.npm-intellisense christian-kohler.path-intellisense ionutvmi.path-autocomplete jasonnutter.search-node-modules leizongmin.node-module-intellisense tgreen7.vs-code-node-require", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-cpp-net", "Extensiones: C, C++ y .NET", "vscode-ext", "ms-vscode.cpptools ms-vscode.cpptools-extension-pack ms-vscode.cpptools-themes ms-vscode.cpp-devtools ms-vscode.cmake-tools ms-dotnettools.csharp ms-dotnettools.csdevkit ms-dotnettools.vscode-dotnet-pack ms-dotnettools.vscode-dotnet-runtime ionide.ionide-fsharp", "ms-vscode.cpptools ms-vscode.cpptools-extension-pack ms-vscode.cpptools-themes ms-vscode.cpp-devtools ms-vscode.cmake-tools ms-dotnettools.csharp ms-dotnettools.csdevkit ms-dotnettools.vscode-dotnet-pack ms-dotnettools.vscode-dotnet-runtime ionide.ionide-fsharp", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-java", "Extensiones: Java", "vscode-ext", "redhat.java vscjava.vscode-java-pack vscjava.vscode-java-debug vscjava.vscode-java-dependency vscjava.vscode-java-test vscjava.vscode-maven vscjava.vscode-gradle", "redhat.java vscjava.vscode-java-pack vscjava.vscode-java-debug vscjava.vscode-java-dependency vscjava.vscode-java-test vscjava.vscode-maven vscjava.vscode-gradle", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-git", "Extensiones: Git y GitHub", "vscode-ext", "eamodio.gitlens donjayamanne.githistory github.vscode-pull-request-github github.vscode-github-actions github.codespaces github.remotehub ms-vscode.remote-repositories ms-vscode.azure-repos", "eamodio.gitlens donjayamanne.githistory github.vscode-pull-request-github github.vscode-github-actions github.codespaces github.remotehub ms-vscode.remote-repositories ms-vscode.azure-repos", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-markdown", "Extensiones: Markdown y notas", "vscode-ext", "yzhang.markdown-all-in-one shd101wyy.markdown-preview-enhanced davidanson.vscode-markdownlint bierner.markdown-mermaid bierner.markdown-checkbox bierner.markdown-emoji bierner.markdown-footnotes bierner.github-markdown-preview bierner.markdown-preview-github-styles bierner.markdown-yaml-preamble bierner.emojisense darkriszty.markdown-table-prettify csholmq.excel-to-markdown-table marchiore.csvtomarkdown mdickin.markdown-shortcuts telesoho.vscode-markdown-paste-image goessner.mdmath gauravpatidar.obsidian-graph-in-vscode", "yzhang.markdown-all-in-one shd101wyy.markdown-preview-enhanced davidanson.vscode-markdownlint bierner.markdown-mermaid bierner.markdown-checkbox bierner.markdown-emoji bierner.markdown-footnotes bierner.github-markdown-preview bierner.markdown-preview-github-styles bierner.markdown-yaml-preamble bierner.emojisense darkriszty.markdown-table-prettify csholmq.excel-to-markdown-table marchiore.csvtomarkdown mdickin.markdown-shortcuts telesoho.vscode-markdown-paste-image goessner.mdmath gauravpatidar.obsidian-graph-in-vscode", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-nube", "Extensiones: contenedores y nube", "vscode-ext", "ms-azuretools.vscode-containers ms-vscode-remote.remote-containers ms-kubernetes-tools.vscode-kubernetes-tools redhat.vscode-yaml redhat.vscode-commons redhat.fabric8-analytics", "ms-azuretools.vscode-containers ms-vscode-remote.remote-containers ms-kubernetes-tools.vscode-kubernetes-tools redhat.vscode-yaml redhat.vscode-commons redhat.fabric8-analytics", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    ("Extensiones de VS Code", "vscode-otros", "Extensiones: otras", "vscode-ext", "ms-vsliveshare.vsliveshare ms-vscode.powershell ms-edgedevtools.vscode-edge-devtools editorconfig.editorconfig be5invis.vscode-icontheme-nomo-dark tomoki1207.pdf imgildev.vscode-json-flow visualstudiotoolsforunity.vstuc", "ms-vsliveshare.vsliveshare ms-vscode.powershell ms-edgedevtools.vscode-edge-devtools editorconfig.editorconfig be5invis.vscode-icontheme-nomo-dark tomoki1207.pdf imgildev.vscode-json-flow visualstudiotoolsforunity.vstuc", "Se instalan para tu usuario con `code --install-extension`; necesita VS Code (grupo Desarrollo)."),
    # Inteligencia artificial
    ("IA", "claude-code", "Claude Code", "npm", "@anthropic-ai/claude-code", "claude", "Ejecútalo dentro de `caja --ia-nube`."),
    ("IA", "codex", "Codex CLI", "npm", "@openai/codex", "codex", "Ejecútalo dentro de `caja --ia-nube`."),
    ("IA", "ollama", "Ollama", "script", "https://ollama.com/install.sh", "ollama",
     "Script oficial del proveedor; pide --si porque se ejecuta con permisos de administrador."),
    # Navegadores
    ("Navegadores", "brave", "Brave", "repo-brave", "brave-browser", "brave-browser", "Repositorio firmado de Brave."),
    # Comunicación y notas
    ("Comunicación", "discord", "Discord", "deb-url",
     "https://discord.com/api/download?platform=linux&format=deb", "discord", "No se actualiza solo; vuelve a ejecutar el comando."),
    ("Notas", "obsidian", "Obsidian", "deb-github", "obsidianmd/obsidian-releases|amd64\\.deb$", "obsidian", ""),
    # Multimedia y directo
    ("Multimedia", "obs", "OBS Studio", "apt", "obs-studio", "obs-studio", "El plugin move-transition se instala dentro de OBS."),
    ("Multimedia", "lsp-plugins", "Plugins de audio LSP", "apt", "lsp-plugins-vst lsp-plugins-lv2", "lsp-plugins-vst",
     "Gratis y de código abierto: compresor, gate, ecualizadores, multibanda, limitador. Sirven en OBS (filtro «VST 2.x» del micrófono), en Easy Effects (audio de todo el sistema) y en otros programas de audio."),
    ("Multimedia", "audacity", "Audacity", "apt", "audacity", "audacity", ""),
    ("Multimedia", "vlc", "VLC media player", "apt", "vlc", "vlc", ""),
    ("Multimedia", "streamdeck", "Elgato Stream Deck", "apt", "streamdeck-ui", "streamdeck-ui", "Ya viene con LeksSO."),
    ("Ofimática", "libreoffice", "Microsoft Office (Word, Excel, PowerPoint)", "apt",
     "libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-l10n-es libreoffice-help-es", "libreoffice-writer",
     "Funciona sin conexión. En el menú también tienes Word, Excel y PowerPoint en su versión web (gratis, con cuenta de Microsoft)."),
    ("Multimedia", "pdf", "Wondershare PDFelement", "apt", "okular", "okular", "Leer y anotar. Edición avanzada de PDF: sin equivalente directo."),
    # Utilidades
    ("Utilidades", "compresores", "WinRAR", "apt", "7zip unrar-free", "7zip", "Ya viene con LeksSO. Zip, 7z, rar y tar."),
    ("Utilidades", "discos", "Administración de discos (Windows: Administración de discos)", "apt", "gparted gnome-disk-utility smartmontools", "gparted", "GParted (particiones), Discos de GNOME (formatear, montar, salud) y smartmontools. Para el disco del propio sistema, ver Ajustes, Discos."),
    ("Utilidades", "monitor", "CPUID HWMonitor / SIV", "apt", "btop lm-sensors", "btop", ""),
    ("Utilidades", "logitech", "Logi Options+", "apt", "solaar", "solaar", ""),
    ("Utilidades", "copias", "Smart Backup", "apt", "timeshift", "timeshift", "Las copias de tus archivos ya vienen con LeksSO (Ajustes, Copias). Esto añade Timeshift, para puntos de restauración del sistema; es avanzado."),
    ("Utilidades", "antivirus", "Malwarebytes", "apt", "clamav", "clamav", "Opcional. En Linux con la caja y sin ejecución por doble clic suele sobrar."),
    ("Utilidades", "vpn", "ExpressVPN", "apt", "wireguard", "wireguard", "WireGuard con la configuración de tu proveedor."),
    # Proton AG (la empresa de correo y VPN; no es la capa Proton de Steam). Piden cuenta: se instalan por nombre o grupo.
    ("Proton", "proton-pass", "Proton Pass", "deb-proton", "https://proton.me/download/pass/linux/x64/version.json",
     "proton-pass", "Gestor de contraseñas. Repite el comando para actualizar."),
    ("Proton", "proton-authenticator", "Proton Authenticator", "deb-proton",
     "https://proton.me/download/authenticator/linux/version.json", "proton-authenticator",
     "Códigos de verificación en dos pasos. Repite el comando para actualizar."),
    ("Proton", "proton-mail", "Proton Mail", "deb-proton", "https://proton.me/download/mail/linux/version.json",
     "proton-mail", "Correo y calendario. Repite el comando para actualizar."),
    ("Proton", "proton-vpn", "Proton VPN", "vpn-proton", "proton-vpn-gnome-desktop", "proton-vpn-gnome-desktop",
     "Repositorio firmado de Proton. Proton solo la soporta con GNOME: en LeksSO, sin garantía."),
    # Juegos
    ("Juegos", "umu", "Programas de Windows con Proton", "umu", "1.4.4", "umu-launcher",
     "umu-launcher. Se usa con `leksso-proton programa.exe`, dentro de la caja."),
    ("Juegos", "steam", "Steam", "steam", "steam-installer", "steam-installer", "Activa la arquitectura de 32 bits y el repositorio contrib."),
    ("Juegos", "heroic", "Epic Games Launcher / Amazon Games", "deb-github",
     "Heroic-Games-Launcher/HeroicGamesLauncher|linux-amd64\\.deb$", "heroic", "Heroic abre Epic, GOG y Amazon."),
    ("Juegos", "minigalaxy", "GOG GALAXY", "apt", "minigalaxy", "minigalaxy", "Alternativa: Heroic."),
    ("Juegos", "lutris", "Ubisoft Connect (vía Wine)", "apt", "lutris", "lutris", "Ubisoft Connect corre con Lutris o Steam; sin garantía."),
    ("Juegos", "r2modman", "Thunderstore Mod Manager", "deb-github",
     "ebkr/r2modmanPlus|amd64\\.deb$", "r2modman", ""),
    ("Juegos", "wine", "Programas de Windows", "apt", "wine", "wine", "Se abren siempre dentro de la caja."),
]

# Entradas que NO son el programa del fabricante para Linux, sino otro programa de terceros que hace una función
# parecida (o que da acceso a tu cuenta desde fuera). La lista lo dice siempre: nadie instala una alternativa
# creyendo que es la versión oficial.
ALTERNATIVAS = {
    "libreoffice": "No hay Microsoft Office de escritorio para Linux; LibreOffice abre y guarda .docx, .xlsx y .pptx (algunas macros y animaciones pueden verse distintas).",
    "streamdeck": "Elgato no publica su programa para Linux; este es de terceros.",
    "pdf": "No hay PDFelement para Linux; es otro lector, solo leer y anotar.",
    "compresores": "No hay WinRAR con ventana para Linux; son compresores libres.",
    "monitor": "No hay HWMonitor ni SIV para Linux; son otras herramientas.",
    "logitech": "Logitech no publica Options+ para Linux; es de terceros.",
    "copias": "No hay Smart Backup para Linux; LeksSO trae sus propias copias en Ajustes.",
    "antivirus": "No hay Malwarebytes de escritorio para Linux; es otro antivirus.",
    "vpn": "ExpressVPN tiene aplicación oficial para Linux (en su web, con tu cuenta); esto es WireGuard genérico.",
    "heroic": "Epic, Amazon y GOG no publican su lanzador para Linux. Heroic es de terceros: entra con tu cuenta y ejecuta tus juegos.",
    "minigalaxy": "GOG no publica Galaxy para Linux; es de terceros.",
    "lutris": "Ubisoft no publica Connect para Linux; Lutris ejecuta el de Windows con Wine, sin garantía.",
    "r2modman": "No es el gestor de Thunderstore (ese depende de Overwolf); es otro gestor que usa sus mods.",
    "wine": "No es un programa de Windows: es la capa que permite ejecutarlos.",
    "umu": "No es de Valve ni de Proton AG: umu-launcher es de terceros y ejecuta programas con Proton fuera de Steam.",
}

# Programas oficiales que piden una cuenta propia: ni --todo ni --completo los instalan; se piden por nombre o grupo.
SOLO_POR_NOMBRE = {"proton-pass", "proton-authenticator", "proton-mail", "proton-vpn"}

# Lo que no se puede instalar con un comando. (Windows, motivo, alternativa)
PENDIENTES = [
    ("Software con licencia propia", "Se descarga del proveedor", "Instalador de Linux en la web del fabricante."),
    ("Instaladores sin dirección fija de descarga", "No se puede automatizar", "Descargar de la web del proveedor y ejecutar."),
    ("Aplicaciones sin cliente oficial para Linux", "Notion, Teams y similares", "Usar su versión web."),
    ("Navegadores adicionales", "No se instalan: el único navegador es Brave", "—"),
    ("Aplicaciones solo de Windows", "Overlays de juegos, gestores de mods de Nexus, utilidades de fabricante", "Sin equivalente."),
    ("Software de RGB, periféricos y placas base", "Específico de cada fabricante", "RGB: OpenRGB (no está en Debian)."),
    ("Controladores de NVIDIA", "Necesitan el repositorio non-free", "Se tratan al instalar en el equipo con tarjeta NVIDIA."),
    ("Plugins de audio y DAW", "Dependen de cada plugin", "Muchos tienen versión VST3 para Linux; requieren un DAW."),
    ("Juegos", "Se instalan desde su launcher", "Comprobar cada uno en ProtonDB; los que llevan antitrampas, sin verificar."),
]

COLOR = sys.stdout.isatty()


def c(t, k):
    return f"\033[{k}m{t}\033[0m" if COLOR else t


def usuario_real():
    """El usuario al que pertenecen las extensiones: el que lanzó sudo, o el actual."""
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or ""


def cmd_code(*args):
    """Orden de VS Code ejecutada como el usuario real (si esto corre con sudo, no como root)."""
    usuario = usuario_real()
    if getattr(os, "geteuid", lambda: 1)() == 0 and usuario and usuario != "root":
        return ["sudo", "-u", usuario, "-H", "code", *args]
    return ["code", *args]


_EXT = {}


def extensiones_instaladas():
    """Extensiones de VS Code ya instaladas para el usuario (en minúsculas). Vacío si no hay VS Code."""
    if "v" not in _EXT:
        if shutil.which("code") is None:
            return set()
        r = subprocess.run(cmd_code("--list-extensions"), capture_output=True, text=True, timeout=120)
        _EXT["v"] = {x.strip().lower() for x in r.stdout.splitlines() if x.strip()} if r.returncode == 0 else set()
    return _EXT["v"]


def instalado(tipo, comprobar):
    if tipo == "vscode-ext":
        return all(i.lower() in extensiones_instaladas() for i in comprobar.split())
    if tipo in ("npm", "script", "playwright"):
        return shutil.which(comprobar) is not None
    r = subprocess.run(["dpkg-query", "-W", "-f=${Status}", comprobar], capture_output=True, text=True)
    return r.returncode == 0 and "install ok installed" in r.stdout


def correr(cmd, simular, **kw):
    print(c("  $ ", "2") + (" ".join(cmd) if isinstance(cmd, list) else cmd), flush=True)
    if simular:
        return 0
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    return subprocess.run(cmd, env=env, **kw).returncode


NPM_FIJADO = os.environ.get("LEKSSO_NPM_FIJADO") or "/usr/local/share/leksso/versiones-npm"


def npm_fijado(paquete):
    """True si el paquete tiene versión y suma fijadas en versiones-npm (se instala con leksso-npm-fijado)."""
    try:
        with open(NPM_FIJADO, encoding="utf-8") as f:
            for linea in f:
                partes = linea.split()
                if len(partes) >= 3 and not linea.startswith("#") and partes[0] == paquete:
                    return True
    except OSError:
        pass
    return False


def sudo(cmd, simular):
    return correr(["sudo", "--preserve-env=DEBIAN_FRONTEND"] + cmd, simular)


def apt(paquetes, simular):
    return sudo(["apt-get", "install", "-y"] + paquetes.split(), simular)


class _SoloHttps(urllib.request.HTTPRedirectHandler):
    """Una redirección a http:// (u otro esquema) se rechaza: HTTPS también después de redirigir."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise SystemExit(f"Redirección a una dirección no HTTPS rechazada: {newurl[:80]}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def abrir_https(req, timeout=60):
    return urllib.request.build_opener(_SoloHttps).open(req, timeout=timeout)


def descargar(url, destino):
    if not url.startswith("https://"):
        raise SystemExit("Solo se descarga por HTTPS")
    req = urllib.request.Request(url, headers={"User-Agent": "leksso-apps"})
    with abrir_https(req) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f)


def instalar_deb(url, simular, suma=None):
    """Descarga el .deb, lo lee UNA vez a memoria, enseña su SHA-256 y lo entrega a root desde esa copia: lo que se
    instala es exactamente lo que se descargó (un proceso del usuario no puede cambiar el archivo entre medias)."""
    print(c("  descarga directa del proveedor (sin firma verificada por apt): ", "33") + url)
    if simular:
        return sudo(["apt-get", "install", "-y", "/var/cache/leksso-descargas/paquete.deb"], simular)
    return instalar_datos([bajar_comprobado(url, suma)])


def bajar_comprobado(url, suma=None):
    """Descarga a memoria. suma = (algoritmo, valor en hexadecimal): si no coincide, no se instala nada."""
    d = tempfile.mkdtemp(prefix="leksso-apps-")
    try:
        ruta = os.path.join(d, "paquete.deb")
        descargar(url, ruta)
        with open(ruta, "rb") as f:
            datos = f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if suma is None:
        print(c("  SHA-256 del paquete: ", "2") + hashlib.sha256(datos).hexdigest())
    else:
        algoritmo, esperada = suma
        real = hashlib.new(algoritmo, datos).hexdigest()
        if real != esperada.lower():
            raise SystemExit(f"La suma {algoritmo} de {url} no es la esperada (es {real}). No se instala nada.")
        print(c(f"  paquete comprobado por su suma {algoritmo}", "2"))
    return datos


def instalar_datos(paquetes):
    """Entrega a root cada paquete desde la copia en memoria y los instala en una sola orden de apt."""
    if sudo(["install", "-d", "-m", "0755", "-o", "root", "-g", "root", "/var/cache/leksso-descargas"], False) != 0:
        return 1
    # Cada instalación, su propio archivo (nombre único creado por root): dos a la vez no se pisan.
    destinos = []
    try:
        for datos in paquetes:
            m = subprocess.run(["sudo", "mktemp", "/var/cache/leksso-descargas/paquete.XXXXXXXX.deb"], capture_output=True, text=True)
            destino = m.stdout.strip()
            if m.returncode != 0 or not destino.startswith("/var/cache/leksso-descargas/"):
                return 1
            destinos.append(destino)
            if subprocess.run(["sudo", "tee", destino], input=datos, stdout=subprocess.DEVNULL).returncode != 0:
                return 1
            sudo(["chmod", "0644", destino], False)
        return sudo(["apt-get", "install", "-y"] + destinos, False)
    finally:
        if destinos:
            sudo(["rm", "-f"] + destinos, False)


def url_github(repo, patron):
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                 headers={"User-Agent": "leksso-apps"})
    with urllib.request.urlopen(req, timeout=30) as r:
        datos = json.load(r)
    for a in datos.get("assets", []):
        if re.search(patron, a["name"]):
            return a["browser_download_url"]
    raise SystemExit(f"No hay un .deb que encaje en {repo}")


def version_proton(datos):
    """(versión, url, sha512) de la versión estable más alta ya repartida a todo el mundo, según el version.json de Proton."""
    candidatas = []
    for r in datos.get("Releases", []):
        reparto = r.get("RolloutPercentage", r.get("RolloutProportion", 0))
        if r.get("CategoryName") != "Stable" or not isinstance(reparto, (int, float)) or reparto < 1:
            continue
        version = str(r.get("Version", ""))
        if not re.fullmatch(r"\d+(\.\d+)+", version):
            continue
        for f in r.get("File", []):
            url, suma = str(f.get("Url", "")), str(f.get("Sha512CheckSum", ""))
            if url.startswith("https://proton.me/download/") and url.endswith(".deb") and re.fullmatch(r"[0-9a-fA-F]{128}", suma):
                candidatas.append((tuple(int(x) for x in version.split(".")), version, url, suma))
    if not candidatas:
        raise SystemExit("Proton no ofrece una versión estable con su suma. No se instala nada.")
    return max(candidatas)[1:]


def version_instalada(paquete):
    r = subprocess.run(["dpkg-query", "-W", "-f=${Version}", paquete], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


# Sin llavero, estas aplicaciones no pueden guardar la sesión cifrada.
LLAVERO = "gnome-keyring libpam-gnome-keyring"


def usar_llavero(paquete, origen="/usr/share/applications", destino="/usr/local/share/applications"):
    """Las aplicaciones Electron no detectan el llavero bajo sway: se les indica en una copia del lanzador, que tiene
    preferencia sobre el del paquete y sobrevive a sus actualizaciones."""
    with open(os.path.join(origen, paquete + ".desktop"), encoding="utf-8") as f:
        texto = f.read()
    texto = re.sub(rf"^(Exec={re.escape(paquete)})(?=\s|$)", r"\1 --password-store=gnome-libsecret", texto, flags=re.M)
    sudo(["install", "-d", "-m", "0755", destino], False)
    ruta = os.path.join(destino, paquete + ".desktop")
    if subprocess.run(["sudo", "tee", ruta], input=texto.encode(), stdout=subprocess.DEVNULL).returncode != 0:
        return 1
    return sudo(["chmod", "0644", ruta], False)


def instalar_proton(paquete, url_versiones, simular):
    r = apt(LLAVERO, simular)
    if r != 0:
        return r
    if simular:
        return instalar_deb(f"(última versión estable según {url_versiones})", simular)
    if not url_versiones.startswith("https://"):
        raise SystemExit("Solo se descarga por HTTPS")
    with abrir_https(urllib.request.Request(url_versiones, headers={"User-Agent": "leksso-apps"})) as resp:
        version, url, suma = version_proton(json.loads(resp.read(5_000_000)))
    if version_instalada(paquete) == version:
        print(f"  ya está la última versión: {version}")
    else:
        r = instalar_deb(url, simular, ("sha512", suma))
    if r == 0 and paquete in ("proton-pass", "proton-mail"):   # las dos son Electron
        r = usar_llavero(paquete)
    return r


# Paquete que añade el repositorio firmado de Proton VPN, con su suma fijada (si Proton publica otro, se cambia a propósito).
VPN_REPO = ("https://repo.protonvpn.com/debian/dists/stable/main/binary-all/protonvpn-stable-release_1.0.10_all.deb",
            "c8a9fffb4ebdd63db08ce7f11c9b0ac394064ae6a210feb9ab63a0f7d8d060a7")

# umu-launcher: versión y sumas fijadas. Son dos paquetes que solo se instalan juntos.
UMU_BASE = "https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.4.4/"
UMU = (("python3-umu-launcher_1.4.4-1_amd64_debian-13.deb", "602c4ac7210a54b835530f927b10c2781e51e294b1cf46448006e48fae66f232"),
       ("umu-launcher_1.4.4-1_all_debian-13.deb", "11a22c8125787e861355bf93953783f61420840fae6e9c0fd43c28dc01e0a947"))


# Huellas de las claves de los repositorios de terceros. Se descarga la clave, se calcula su huella y solo se
# instala si TODAS las claves del archivo están en esta lista: una clave sustituida o añadida no pasa.
# (Si el proveedor rota su clave, hay que actualizar esta lista a propósito.)
HUELLAS = {
    "brave-browser": {"DBF1A116C220B8C7164F98230686B78420038257",
                      "47D32A74E9A9E013A4B4926C68D513D36A73CD96",
                      "B2A3DCA350E67256740DF904DE4EC67BE4B0DCA0"},
    "microsoft": {"BC528686B50D79E339D3721CEB3E94ADBE1229CF"},
}


def huellas_de(datos):
    """Huellas de las claves PRINCIPALES de un archivo de claves (binario o armado), con gpg --show-keys."""
    r = subprocess.run(["gpg", "--show-keys", "--with-colons", "--fingerprint"], input=datos, capture_output=True, timeout=30)
    if r.returncode != 0:
        return None
    huellas, esperando = set(), False
    for linea in r.stdout.decode("utf-8", "replace").splitlines():
        campos = linea.split(":")
        if campos[0] == "pub":
            esperando = True
        elif campos[0] == "sub":
            esperando = False
        elif campos[0] == "fpr" and esperando:
            huellas.add(campos[9].upper())
            esperando = False
    return huellas


def repo_clave(nombre, url_clave, linea, simular, dearmor=False):
    llave = f"/usr/share/keyrings/{nombre}.gpg"
    if not simular:
        sudo(["apt-get", "install", "-y", "gnupg"], False)
        req = urllib.request.Request(url_clave, headers={"User-Agent": "leksso-apps"})
        with abrir_https(req) as r:
            clave = r.read(1_000_000)
        huellas = huellas_de(clave)
        esperadas = HUELLAS.get(nombre)
        if not esperadas or not huellas or not huellas <= esperadas:
            raise SystemExit(f"La clave del repositorio {nombre} no es la esperada (huellas: {sorted(huellas or [])}). No se instala nada.")
        print(c("  clave comprobada por su huella: ", "2") + ", ".join(sorted(huellas)))
        if dearmor:
            d = subprocess.run(["gpg", "--dearmor"], input=clave, capture_output=True, timeout=30)
            if d.returncode != 0 or not d.stdout:
                raise SystemExit("No se pudo preparar la clave del repositorio.")
            clave = d.stdout
        sudo(["install", "-d", "-m", "0755", "/usr/share/keyrings"], False)
        if subprocess.run(["sudo", "tee", llave], input=clave, stdout=subprocess.DEVNULL).returncode != 0:
            raise SystemExit("No se pudo guardar la clave del repositorio.")
        sudo(["chmod", "0644", llave], False)
    else:
        print(c("  $ ", "2") + f"(descargar la clave, comprobar su huella e instalarla en {llave})")
    correr(f"echo '{linea.format(llave=llave)}' | sudo tee /etc/apt/sources.list.d/{nombre}.list >/dev/null",
           simular, shell=True)
    return sudo(["apt-get", "update"], simular)


def configurar_code():
    """VS Code con Wayland y sin telemetría, si el usuario no tiene ya sus propios ajustes."""
    cfg = os.path.expanduser("~/.config")
    os.makedirs(os.path.join(cfg, "Code", "User"), exist_ok=True)
    flags = os.path.join(cfg, "code-flags.conf")
    if not os.path.exists(flags):
        with open(flags, "w") as f:
            f.write("--ozone-platform-hint=auto\n--password-store=basic\n")
    ajustes = os.path.join(cfg, "Code", "User", "settings.json")
    if not os.path.exists(ajustes):
        with open(ajustes, "w") as f:
            json.dump({"telemetry.telemetryLevel": "off", "update.mode": "none",
                       "workbench.enableExperiments": False}, f, indent=2)
            f.write("\n")


def anotar(nombre, modo, rc, simular):
    """Lo que no pasa por apt no lo ve el gancho de apt: se anota en el registro de instalaciones (sin impedir nada si falla)."""
    if rc == 0 and not simular:
        try:
            subprocess.run(["sudo", "-n", "leksso-auditoria", "anotar", "--nombre", nombre, "--modo", modo, "--origen", "catalogo"],
                           capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    return rc


def proteger_audio(simular):
    """Algunos programas traen fluidsynth, que abre la tarjeta de sonido directamente y deja a PipeWire sin audio:
    su servicio de usuario se enmascara en cuanto aparece."""
    if os.path.exists("/usr/bin/fluidsynth") or simular:
        sudo(["ln", "-sf", "/dev/null", "/etc/systemd/user/fluidsynth.service"], simular)


def hacer(item, simular, si):
    grupo, ident, win, tipo, objetivo, comprobar, nota = item
    print(c(f"\n▶ {ident}", "1;36") + f"  ({win})")
    if tipo == "apt":
        rc = apt(objetivo, simular)
        if rc == 0:
            proteger_audio(simular)
        return rc
    if tipo == "vscode-ext":
        if shutil.which("code") is None and not simular:
            print(c("  Falta VS Code: instálalo primero (leksso-apps instalar code).", "33"))
            return 1
        ya = extensiones_instaladas()
        fallos = []
        for ext in objetivo.split():
            if ext.lower() in ya:
                continue
            if correr(cmd_code("--install-extension", ext), simular) != 0:
                fallos.append(ext)
        _EXT.clear()
        if fallos:
            print(c("  No se pudieron instalar: " + ", ".join(fallos), "31"))
        return anotar(ident, "extensiones de VS Code (catálogo)", 1 if fallos else 0, simular) if not fallos else 1
    if tipo == "repo-brave":
        repo_clave("brave-browser", "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg",
                   "deb [signed-by={llave}] https://brave-browser-apt-release.s3.brave.com/ stable main", simular)
        return apt(objetivo, simular)
    if tipo == "repo-vscode":
        repo_clave("microsoft", "https://packages.microsoft.com/keys/microsoft.asc",
                   "deb [arch=amd64 signed-by={llave}] https://packages.microsoft.com/repos/code stable main",
                   simular, dearmor=True)
        r = apt(objetivo, simular)
        if r == 0 and not simular:
            configurar_code()
        return r
    if tipo == "docker":
        r = apt(objetivo, simular)
        if r == 0:
            # Bajo demanda: Docker no arranca con el equipo (retrasaba el inicio unos 6 s esperando la red y ocupaba
            # memoria siempre). Queda escuchando su socket y se pone en marcha solo con la primera orden `docker`.
            sudo(["systemctl", "disable", "--now", "docker.service", "containerd.service"], simular)
            sudo(["systemctl", "enable", "--now", "docker.socket"], simular)
        usuario = os.environ.get("SUDO_USER") or os.environ.get("USER") or ""
        if r == 0 and usuario:
            sudo(["usermod", "-aG", "docker", usuario], simular)
            if not simular:
                print(c("  Te he añadido al grupo docker: cierra sesión y vuelve a entrar para usarlo sin sudo.", "33"))
        return r
    if tipo == "playwright":
        r = apt("nodejs npm", simular)
        if r == 0:
            r = sudo(["npm", "install", "-g", "playwright"], simular)
        if r == 0:
            r = sudo(["playwright", "install-deps", "chromium"], simular)
        if r == 0:
            r = correr(["playwright", "install", "chromium"], simular)  # como usuario: va a ~/.cache/ms-playwright
        return r
    if tipo == "steam":
        sudo(["dpkg", "--add-architecture", "i386"], simular)
        sudo(["apt-get", "update"], simular)
        r = apt(objetivo, simular)
        # Con el controlador de NVIDIA, Steam necesita también sus librerías de 32 bits: sin ellas falta libGL.so.1 (i386) y los
        # juegos no arrancan (código 127, «reaper: libGL.so.1: cannot open shared object file»).
        if r == 0 and subprocess.run(["dpkg", "-s", "libglx-nvidia0"], capture_output=True).returncode == 0:
            r = apt("nvidia-driver-libs:i386", simular)
        return r
    if tipo == "deb-proton":
        return instalar_proton(comprobar, objetivo, simular)
    if tipo == "vpn-proton":
        r = instalar_deb(VPN_REPO[0], simular, ("sha256", VPN_REPO[1]))
        if r == 0:
            r = sudo(["apt-get", "update"], simular)
        if r == 0:   # el último paquete es el del icono en la bandeja
            r = apt(f"{objetivo} {LLAVERO} gir1.2-ayatanaappindicator3-0.1", simular)
        if r == 0:
            # El túnel dividido necesita las cabeceras del núcleo para compilar su programa BPF: sin ellas el servicio
            # falla en cada arranque. Se deja apagado; la VPN no depende de él.
            sudo(["systemctl", "disable", "--now", "me.proton.vpn.split_tunneling.service"], simular)
            sudo(["systemctl", "reset-failed", "me.proton.vpn.split_tunneling.service"], simular)
        return r
    if tipo == "umu":
        sudo(["dpkg", "--add-architecture", "i386"], simular)   # umu depende de librerías de 32 bits
        r = sudo(["apt-get", "update"], simular)
        if r != 0:
            return r
        if simular:
            return sudo(["apt-get", "install", "-y"] + [n for n, _ in UMU], simular)
        return instalar_datos([bajar_comprobado(UMU_BASE + n, ("sha256", s)) for n, s in UMU])
    if tipo == "deb-url":
        return instalar_deb(objetivo, simular)
    if tipo == "deb-github":
        repo, patron = objetivo.split("|")
        return instalar_deb(url_github(repo, patron) if not simular else f"(último .deb de github.com/{repo})", simular)
    if tipo == "npm":
        if npm_fijado(objetivo):          # versión y suma fijadas por LeksSO (Claude Code, Codex)
            rc = sudo(["leksso-npm-fijado", objetivo], simular)
            return anotar(item[2], "leksso-npm-fijado " + objetivo, rc, simular)
        rc = sudo(["npm", "install", "-g", objetivo], simular)
        return anotar(item[2], "npm install -g " + objetivo, rc, simular)
    if tipo == "script":
        if not si and not simular:
            print(c("  Este paso ejecuta un script del proveedor con permisos de administrador. Repite con --si.", "33"))
            return 1
        rc = correr(f"curl -fsSL {objetivo} | sudo sh", simular, shell=True)
        return anotar(item[2], "script del proveedor (curl | sh): " + objetivo, rc, simular)
    return 1


def buscar(nombres):
    sel = []
    for k in (n.lower() for n in nombres):
        exactos = [it for it in CATALOGO if k in (it[1].lower(), it[0].lower())]
        encontrados = exactos or [it for it in CATALOGO if k in it[2].lower()]
        for it in encontrados:
            if it not in sel:
                sel.append(it)
    return sel


def lista():
    grupo = None
    for it in CATALOGO:
        if it[0] != grupo:
            grupo = it[0]
            print("\n" + c(grupo, "1"))
        ok = instalado(it[3], it[5])
        marca = c("✓", "32") if ok else c("·", "2")
        clase = c("alternativa", "33") if it[1] in ALTERNATIVAS else c("oficial    ", "2")
        nota = ALTERNATIVAS.get(it[1]) or (it[6] if not ok else "")
        print(f"  {marca} {it[1]:<14} {clase} {c('←', '2')} {it[2]}" + (c(f"   {nota}", "2") if nota else ""))
    print(f"\n{c('✓', '32')} ya instalado   · disponible.   Instalar: leksso-apps instalar NOMBRE   (--todo para todo lo automático)")
    print("oficial: el programa de su fabricante para Linux.   alternativa: otro programa, de terceros, que hace esa función.")
    print("Lo que no tiene comando: leksso-apps pendientes")


def pendientes():
    print(c("Sin comando de instalación", "1") + "\n")
    for win, motivo, alt in PENDIENTES:
        print(f"  {c(win, '1')}\n    {motivo}. {alt}")


def main(argv):
    simular = "--simular" in argv
    si = "--si" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        return lista()
    if args[0] in ("pendientes", "pend"):
        return pendientes()
    if args[0] != "instalar":
        print(__doc__)
        return 2
    todo = "--todo" in argv or "--completo" in argv
    if todo:
        # --todo instala solo lo oficial: las alternativas de terceros se piden por su nombre o con --completo
        sel = [it for it in CATALOGO if (it[1] not in ALTERNATIVAS or "--completo" in argv)
               and it[1] not in SOLO_POR_NOMBRE and not instalado(it[3], it[5])]
    else:
        nombres = args[1:]
        if not nombres:
            print("Indica qué instalar: un nombre, un grupo o --todo")
            return 2
        sel = buscar(nombres)
        if not sel:
            print("No encuentro nada con ese nombre. Mira la lista con: leksso-apps")
            return 1
    # Lo de Proton pedido por su nombre se revisa aunque ya esté: así se actualiza.
    pend = [it for it in sel if it[3] == "deb-proton" or not instalado(it[3], it[5])]
    for it in sel:
        if it not in pend:
            print(f"  ya instalado: {it[1]}")
    if not pend:
        return 0
    if todo and not si and not simular:
        print("Se instalará: " + ", ".join(it[1] for it in pend))
        if input("¿Continuar? [s/N] ").strip().lower() not in ("s", "si", "sí"):
            return 1
    fallos = []
    confirmado = todo  # la confirmación de --todo cubre también los scripts del proveedor
    for it in pend:
        if hacer(it, simular, si or confirmado) != 0:
            fallos.append(it[1])
    if not simular and shutil.which("leksso-asociar"):
        subprocess.run(["leksso-asociar"], capture_output=True)  # navegador y programas nuevos como predeterminados si faltaban
    print()
    if fallos:
        print(c("Con errores: " + ", ".join(fallos), "31"))
        return 1
    print(c("Hecho.", "32") + (" (simulado: no se ha instalado nada)" if simular else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
