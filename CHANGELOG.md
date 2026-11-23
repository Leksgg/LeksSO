# Changelog

Formato: `+` nuevo · `-` eliminado o retirado · `~` modificado · `*` otros.
Lo más reciente, arriba.

## Beta 0.1.40 · 2026-11-23

+ **Plugins de audio LSP, en el catálogo.** `leksso-apps instalar lsp-plugins` instala los plugins LSP (gratuitos y de código abierto): compresor, gate, ecualizadores paramétricos, multibanda y limitador, en formato VST 2 (el que carga el filtro «VST 2.x» de OBS en el micrófono) y LV2 (para Easy Effects y otros programas de audio). No vienen en la base: se instalan a petición.

## Beta 0.1.39 · 2026-11-23

~ **Brave viene instalado con el sistema y es el navegador por defecto.** Antes era una aplicación del catálogo que había que instalar aparte. Ahora la instalación lo deja puesto y como predeterminado para enlaces y archivos web. En la imagen de instalación sin internet va dentro del repositorio local (su clave se comprueba por huella al construirla, y solo se acepta la esperada); instalando con red, sale de su repositorio firmado. Si no se pudiera instalar, la instalación continúa y se hace después con `leksso-apps instalar brave`.

~ **Steam en equipos con NVIDIA: los juegos ya arrancan.** Con el controlador propietario de NVIDIA, Steam necesita también las librerías de 32 bits de NVIDIA; sin ellas falta `libGL.so.1` de 32 bits y el juego se cierra al instante sin mostrar nada (en el registro de Steam, «reaper: error while loading shared libraries: libGL.so.1» y código de salida 127). Ahora, al instalar Steam desde el catálogo en un equipo con NVIDIA, se instala también `nvidia-driver-libs:i386`. Si ya tienes Steam y los juegos no abren: `sudo apt install nvidia-driver-libs:i386`. Comprobado en `a01` con Dead by Daylight.

## Beta 0.1.38 · 2026-11-22

~ **El botón de «versión nueva» ya aparece al iniciar sesión.** La barra leía el resultado de la comprobación antes de que esta terminara y no volvía a mirar hasta 15 minutos después, así que al arrancar no salía el botón aunque hubiera una versión nueva. Ahora la comprobación avisa a la barra al terminar, y la barra además se refresca cada 5 minutos.

## Beta 0.1.37 · 2026-11-22

~ **Escritorio por zonas más simple: explorador en el centro y la IA a la derecha.** Se acabó la franja estrecha del centro con el texto «Aquí se abre la app…» y la columna de carpetas aparte, que repetía el árbol del explorador (y a veces salía duplicada si el explorador de LeksSO tardaba en arrancar). Ahora el centro es el explorador completo (barra, árbol y contenido); lo que abras (Steam, Brave, la terminal…) entra como pestaña nueva en esa misma zona, y el panel de la IA sigue a la derecha. Comprobado en `a01`.

~ **Modo de energía dentro de la batería.** El módulo aparte de «Rendimiento» desaparece: ahora un rayo delante de la pila lo dice por color. Ahorro, rayo verde con una hoja verde; Equilibrado, rayo verde; Rendimiento, rayo amarillo. Un clic en la batería abre una ventanita con los tres modos y lo que hace cada uno; se cierra con la X, con Esc o al elegir uno (el menú anterior no se podía cerrar). Enchufada y cargando, la pila lleva un enchufe en vez de rayo, para no confundirlos. En un sobremesa, sin batería, se enseña solo el rayo del modo.

## Beta 0.1.36 · 2026-11-22

~ **Barra inferior más viva.** La batería cambia de color con el nivel (verde por encima del 50 %, ámbar del 21 al 50 %, rojo del 20 % o menos), parpadea al 10 % o menos y, enchufada, se queda en verde con un rayo; el tooltip da el tiempo restante y la salud de la pila. Nuevo módulo del **modo de energía** (Ahorro, Equilibrado, Rendimiento) con icono y color propios; un clic abre un menú con los tres modos y una línea que explica cada uno. CPU y memoria pasan a icono y porcentaje, en gris en calma, ámbar desde el 70 % (CPU) o 75 % (RAM) y rojo desde el 90 %. La red enseña barras de señal en vez de un número, el volumen cambia de icono según el nivel y los módulos tienen ancho fijo para que la barra no baile. Se quita la versión de la barra (sigue en Ajustes, Actualizaciones): el aviso de actualización aparece solo cuando hay una nueva.

~ **Escritorio por zonas: Steam y los programas antiguos ya no caen en cualquier sitio.** La regla que manda lo que abres al centro solo reconocía programas de Wayland (los que tienen `app_id`). Steam y otros programas de X11 (por XWayland) no lo tienen, se saltaban la regla y se abrían donde estuviera el foco: debajo del centro, junto a la terminal, o como una pestaña dentro del panel de la IA. Ahora hay una regla también para ellos, y **el panel de la IA queda reservado a las IA** (panel, asistentes); todo lo demás, al centro. Siguen flotando el menú, la energía, el portapapeles, los ajustes y las actualizaciones. Comprobado en `a01`: Steam se abrió dentro del panel de la IA, justo en su recuadro.

## Beta 0.1.35 · 2026-11-21

~ **Instalador: un grupo LVM viejo en otro disco ya no atasca la instalación.** Si otro disco tenía un volumen llamado `leksso-vg` (de una instalación anterior), LVM no deja crear otro con el mismo nombre y la instalación se paraba en el resumen de particiones, con el cifrado creado y vacío. Ahora, al elegir el disco, el instalador mira los grupos que hay en los demás discos y usa un nombre libre (`leksso-vg-2`, `-3`...). Si el grupo viejo está en el propio disco elegido, se borra como siempre.

## Beta 0.1.34 · 2026-11-20

~ **Red inalámbrica: un portátil solo con Wi-Fi ya queda con red desde el primer arranque.** Hasta ahora la instalación no dejaba el Wi-Fi utilizable en un equipo sin cable, por dos motivos:
  - **Faltaba `wpasupplicant`**, que NetworkManager necesita para conectarse a cualquier Wi-Fi con contraseña. Es un paquete «recomendado» y el instalador instala sin recomendados. Ahora forma parte de la base, junto con `iw` y `wireless-regdb` (canales y potencias permitidos por país).
  - **El firmware de la tarjeta no se instalaba** durante la instalación, solo más tarde y con red, o sea, nunca en un equipo sin cable. Ahora se instala siempre, desde el repositorio local de la imagen: Intel, Realtek, Atheros, MediaTek, Broadcom y el general, cada paquete por separado (un fallo no detiene la instalación).
  - El repositorio local de la imagen incluye esos paquetes (906 en total).
  - Si ya tienes LeksSO instalado sin Wi-Fi: con cualquier conexión (cable o el móvil por USB), `leksso-actualizar aplicar` los instala.

## Beta 0.1.33 · 2026-11-20

~ **Arreglo de la 0.1.32: la instalación sin red se caía** («Falló la ejecución de la orden de preconfiguración… código de error 100»). La 0.1.32 exigía unos paquetes nuevos de administración de discos (`lxqt-policykit`, `cloud-guest-utils`, `smartmontools`, `gparted`, `gnome-disk-utility`) que no estaban en el repositorio local de la imagen de instalación. Ahora se instalan uno a uno y **sin que un fallo detenga la instalación**; sin red, se instalan después (Aplicaciones, Utilidades). El repositorio local que se construya a partir de ahora los incluye, y también `firmware-brcm80211` (Wi-Fi Broadcom). Hasta ahora no se había visto porque la instalación fallaba antes por la firma de la imagen de pruebas.
+ **Instalador: menú de dos niveles y pantalla propia del disco** (probado en la VM hasta el último paso):
  - **Menú de arriba** con «Instalar LeksSO», «Instalar Windows 10» (solo si el pendrive lleva su partición) y «Reparar»; el segundo nivel lista las 6 variantes con su leyenda. Sin cuenta atrás (no debe empezar a borrar solo) y sin las entradas de Debian que sobraban.
  - **Pantalla del disco**: lista cada disco con modelo, tamaño, tipo (NVMe, SSD, disco duro, USB) y qué contiene («Windows», «Linux», «cifrado»); no ofrece el pendrive de instalación; preselecciona el NVMe/SSD; y hay que **escribir BORRAR** para continuar (vacío vuelve a la lista).
  - Se dejan las confirmaciones de Debian tras ella (saltarlas hacía caer «Instalar el sistema base»).

## Beta 0.1.32 · 2026-11-20

+ **Instalador: sin parar en equipos sin red ni con dos discos** (probado en una VM sin red y con dos discos; falta la instalación completa hasta el escritorio con una ISO firmada):
  - **Sin red no pregunta nada de red** (lista de controladores, «ninguna interfaz», «configurar la red», «sin réplica»): `netcfg/enable false`, `apt-setup/no_mirror true` y `priority=critical`. Solo pide lo imprescindible: usuario, disco y clave.
  - **Con dos discos** ya no sale el menú del método (que parecía el particionado manual): pregunta solo qué disco. Atención: el orden de la lista cambia entre arranques; mira el modelo y el tamaño antes de pulsar Intro.
  - **GRUB se instala en el disco elegido.** Con dos discos lo intentaba en el primero (`/dev/sda`) y fallaba: «Falló un paso: Instalar el cargador de arranque GRUB».
  - **Ya no sobrescribe el disco entero con datos aleatorios** antes de cifrar (`partman-auto-crypto/erase_disks false`; antes tardaba horas en un disco grande).
  - **Menú de arranque legible**: la caja del tema de Debian cortaba los títulos a unos 46 caracteres; se ensancha y se añade una leyenda debajo que explica cada opción. Títulos con el mismo formato: «Instalar LeksSO | cómo va el disco | cómo entra el usuario».
+ **Administrar discos y particiones**:
  - **Ajustes, Discos**: tabla de discos y particiones (solo lectura) y accesos a **GParted**, **Discos de GNOME**, la salud del disco (SMART) y «Ampliar el sistema». GParted y Discos entran en el catálogo (Utilidades) y en la base, con `smartmontools`, `parted` y un agente de permisos pequeño (`lxqt-policykit`) para que pidan la contraseña de administrador.
  - **`sudo leksso-disco ampliar [--comprobar]`**: da al sistema todo el espacio libre tras su partición, con el equipo encendido (partición, contenedor cifrado, LVM, sistema de archivos). No cambia la clave, así que el desbloqueo por TPM sigue valiendo. Probado en un disco cifrado con LVM de prueba (1 GB a 2 GB) y en el A04 con `--comprobar`. Reducir o mover las particiones del sistema exige hacerlo con el sistema apagado: pendiente (entrada «Administrar discos» en el pendrive).
+ **Recuperación, como las opciones avanzadas de inicio de Windows**:
  - **Energía, «Reiniciar en otro sistema o dispositivo…»**: reinicia UNA vez en Windows, en una memoria USB de arranque, en la red o en la BIOS, y después el equipo arranca como siempre. Detrás está `leksso-reiniciar-en listar | usar ID | bios` (`efibootmgr`, que ahora va en la base).
  - **`sudo leksso-reparar [--comprobar] [--completa]`**: repara el arranque sin tocar tus archivos (monta las particiones de arranque, termina paquetes a medias, regenera el initramfs, reinstala GRUB y su entrada en la BIOS, regenera el menú). `--comprobar` solo enseña lo que haría. Funciona con el sistema en marcha y desde la consola del modo de rescate del pendrive.
  - **`sudo leksso-actualizar reinstalar`**: vuelve a instalar la versión que tienes, con su firma comprobada (repara archivos de LeksSO dañados). `leksso-reparar --completa` lo usa.
  - **Instalador: «Reparar LeksSO que no arranca (modo de rescate; NO borra nada)»**, entrada nueva del menú, con las instrucciones en pantalla.
  - La ventana de Energía es más alta (380×680) para el botón nuevo.
~ **Convivencia con Windows, probada en una VM** (Windows 10 en un disco y LeksSO 0.1.31 con cifrado y TPM en otro): el menú de arranque de LeksSO muestra «Windows Boot Manager» y Windows arranca desde él; LeksSO se instala sin tocar el disco de Windows; el desbloqueo del disco por TPM funciona en un arranque real (sin pedir clave) y la oferta del primer arranque sale sola. **Hora de la placa**: la instalación no puede dejarla en hora local (el instalador de Debian reescribe el reloj al terminar), así que ahora lo hace `leksso-hora` al iniciar la sesión, una sola vez, si hay Windows y sudo sin contraseña.
* Visto al probar: al elegir el disco el instalador solo enseña modelo y tamaño y marca el primero por defecto, que puede ser el de Windows. La protección contra borrar un disco con Windows sigue pendiente.

## Beta 0.1.31 · 2026-11-20

+ **Instalador: convivir con Windows**: `os-prober` va en el USB y el menú de arranque de LeksSO (GRUB) muestra Windows si lo encuentra; así se elige el sistema al encender. Si hay Windows, la hora de la placa se deja en hora local para que no se desfase al alternar. Sin otro sistema, no cambia nada. Cada sistema debe ir en su disco: el instalador sigue borrando el disco entero que se elige (la protección contra borrar un disco con Windows y el modo «junto a Windows» siguen pendientes). `scripts/instalador/crear-vm-convivencia.ps1` crea la máquina virtual de Hyper-V (arranque seguro, TPM y dos discos) para probarlo antes de tocar el equipo real.
+ **Servidor de TeamSpeak 3 en LeksSO**: `sudo leksso-ts3-instalar [--datos CARPETA]` instala la 3.13.8 (versión y suma SHA-256 fijadas; si no coincide, no instala) como un usuario propio sin acceso al resto del equipo y, con `--datos`, trae la base de datos y los archivos de un servidor de Windows sin tocar el origen (cierra el registro WAL y comprueba la integridad). Queda **apagado**: `sudo leksso-ts3 on` lo arranca y abre solo la voz (UDP 9987) y los archivos (TCP 30033) mientras esté encendido; `off` lo para y cierra los puertos. La consulta nunca se abre (solo desde el propio equipo). Para entrar desde fuera de casa hay que reenviar esos puertos en el router.

## Beta 0.1.30 · 2026-11-20

+ **Instalador: cifrado con desbloqueo automático (TPM2)**: dos entradas nuevas en el menú de la ISO («disco cifrado con desbloqueo automático por TPM» y la misma sin contraseña de usuario, que es la más cómoda). Se instala con la clave que se elija y, en el primer arranque del escritorio, se ofrece enlazar el disco al TPM (`leksso-disco primer-arranque`); la clave queda de respaldo. Las herramientas (`clevis`, `tpm2-tools`) van en el USB. Preparado en el código; la ISO aún no se ha construido ni probado.
+ **Disco cifrado con desbloqueo automático (TPM2)**: `leksso-disco automatico on|off`, `renovar` y `estado`, y la tarjeta **Disco cifrado** en Ajustes. Si el equipo tiene TPM2, el disco se abre solo en cada arranque, sin teclear la clave, mientras el estado de Secure Boot (PCR 7) sea el de siempre; si cambia (BIOS, base de firmas), pide la clave normal una vez y se renueva con `renovar`. La clave del disco **no se borra**: es el respaldo. Pide confirmar que la tienes guardada y avisa de que protege el disco extraído o robado, pero no contra quien encienda el equipo tal cual. Activarlo requiere teclear la clave del disco una vez. Revisión de equipo y ensayo en un LUKS de prueba: enlazar, abrir sin clave, respaldo y caída al prompt tras cambiar el arranque.

## Beta 0.1.29 · 2026-11-20

+ **Ajustes, Bloqueo y reposo**: se elige cuándo se bloquea la pantalla, se apaga y se suspende (Nunca, 1, 5, 10, 15, 30 minutos, 1 o 2 horas); se guarda en `~/.config/leksso/reposo` y se aplica al momento. Por defecto sigue igual: 10, 15 y 30 minutos (la suspensión solo con batería). Con el bloqueo en «Nunca» tampoco se bloquea al suspender. `leksso-reposo iniciar|aplicar|mostrar`.
~ **Codex: iniciar sesión**: desde dentro de la caja llevaba a una «ruta no válida» (Codex espera la respuesta del navegador en `localhost:1455` y la caja no tiene reenvío de puertos, a propósito). Ahora `leksso-codex login` (y el primer arranque, solo) hace la autenticación fuera de la caja; la sesión queda en la carpeta que la caja ve. Con `leksso-codex login --device-auth` se entra con un código, sin navegador local.
~ **Ajustes**: los textos largos de las tarjetas (p. ej. el del SSH) ahora se ajustan al ancho en vez de cortarse.

## Beta 0.1.28 · 2026-11-20

~ **Micrófono y altavoz del portátil**: el micrófono grababa silencio total (el audio usaba el perfil genérico `stereo-fallback`, que no enruta los micrófonos digitales). Ahora la base instala `alsa-ucm-conf` y `alsa-utils`; con eso aparecen «Digital Microphone» y «Speaker» y se graba con voz. Hallado en la validación del A04 con Discord.
~ **Auriculares Bluetooth**: faltaba `libspa-0.2-bluetooth`, así que PipeWire no admitía audio Bluetooth; se instala en la base.
~ **Sin audio tras reiniciar el sonido**: `fluidsynth` (dependencia de Lutris) abría la tarjeta directamente y PipeWire se quedaba sin dispositivos (`pcm0p busy`). Su servicio de usuario se enmascara al actualizar y al instalar desde el catálogo.
~ **Causa del raíl perdido tras reiniciar (A04)**: la sesión de sway no pasaba su entorno gráfico a systemd. Al instalar el catálogo se instaló `xdg-desktop-portal-gtk` (dependencia de Minigalaxy); en el siguiente arranque el portal principal intentaba usarlo, no podía abrirse sin pantalla, se quedaba esperando 25 s por petición y waybar moría con «Failed to activate service org.freedesktop.portal.Desktop: timed out». Ahora sway importa `WAYLAND_DISPLAY`, `SWAYSOCK` y `XDG_CURRENT_DESKTOP` en systemd y en D-Bus antes de arrancar la barra.
~ **Barra del escritorio que se reinicia sola**: tras un reinicio en el A04 el raíl y la barra de tareas no aparecieron (waybar no arrancó y nada lo volvió a lanzar). Ahora sway lanza `leksso-barra`, que arranca waybar y lo reinicia si se cae (hasta 20 veces seguidas) y deja cada cierre, con su código de salida, en `~/.cache/leksso/barra.log` para saber la causa. Solo hay una copia vigilando a la vez.
~ **Teclas de brillo**: no funcionaban (el archivo del brillo era solo de root y Debian no trae la regla de brightnessctl). Nueva regla udev `70-leksso-brillo.rules` que da permiso al grupo `video`; se instala con el resto y se aplica al momento. Hallado en la validación del A04.

## Beta 0.1.27 · 2026-11-19

+ **Extensiones de VS Code en el catálogo**: 93 extensiones en 9 grupos (`vscode-ia`, `vscode-python`, `vscode-js`, `vscode-cpp-net`, `vscode-java`, `vscode-git`, `vscode-markdown`, `vscode-nube`, `vscode-otros`). Se instalan para tu usuario con `code --install-extension` (también cuando se lanza con `sudo leksso-instalador`) y entran en `--todo` y `--completo`. Se pueden instalar por grupo: `leksso-apps instalar vscode-java`.

## Beta 0.1.26 · 2026-11-19

~ **Tamaño de las zonas del escritorio**: los anchos y altos que dejes arrastrando los bordes (explorador, panel de IA, terminal) se guardan solos en `~/.config/leksso/zonas` y se vuelven a poner al iniciar sesión, al restaurar las zonas y al plegar la columna de carpetas. Antes, cada inicio volvía a 22 %, 26 % y 26 %. Se puede volver a los de fábrica en cualquier momento, sin cerrar ni mover ventanas: Ajustes, Zonas del escritorio, o `leksso-zonas --fabrica`. `leksso-zonas --medir` muestra los tamaños actuales.
~ **`sway/local.conf` en Hyper-V**: ya no se reescribe en cada actualización si existe.
~ **SSH con una cuenta sin contraseña**: antes se encendía y nadie podía entrar (sshd rechaza las contraseñas vacías). Ahora `leksso-acceso-remoto on` no enciende nada si la cuenta no tiene contraseña ni clave autorizada, y Ajustes, Acceso remoto ofrece resolverlo en el momento: poner una contraseña para SSH (solo se pide al entrar por SSH; el inicio de sesión y sudo siguen igual) o autorizar una clave pública. El modo público sigue siendo solo con clave y pide autorizar una si falta.
+ `leksso-acceso-remoto cuenta` (¿contraseña? ¿cuántas claves?) y `leksso-acceso-remoto clave 'ssh-...'` (valida y autoriza una clave pública, sin sudo).

## Beta 0.1.25 · 2026-11-19

~ **Ajustes, más ancha**: la ventana se abre al 55 % del ancho de la pantalla (entre 720 y 1000 px) y los botones se reparten en 1, 2 o 3 columnas según el ancho. El texto de cada botón se ajusta a su ancho en vez de cortarse.

## Beta 0.1.24 · 2026-11-19

+ **Instalador de una orden**: `sudo leksso-instalador` instala todo el catálogo (los programas de Linux y sus equivalentes) y enciende el SSH solo para la red local. Opciones `--sin-ssh` y `--simular`. `leksso-apps instalar --completo` hace lo mismo con los programas.
+ **Ajustes, Acceso remoto (SSH)**: botón que muestra si el SSH está apagado, solo en red local o también público, y permite elegir. El modo público solo admite clave SSH (la contraseña se desactiva), exige una clave autorizada del usuario y limita las conexiones nuevas; `sudo leksso-acceso-remoto on local|publico`.
~ **Ajustes**: la ventana tiene barra de desplazamiento y se ajusta al tamaño de la pantalla; antes se cortaba.

## Beta 0.1.23 · 2026-11-19

Segunda revisión de seguridad (sobre la 0.1.22). Se corrige lo comprobado; lo que es un cambio de arquitectura queda anotado abajo.

~ **Permisos de archivos**: al aprobar, se comprueba que la carpeta sigue siendo la misma que cuando se pidió (si alguien la sustituyó mientras esperabas, no se concede). Desactivar un asistente inutiliza al momento sus tareas abiertas. Cada asistente tiene su propia cuota de peticiones sin responder, para que uno con la cola llena no tape a los demás.
~ **Recuperar de las copias**: cada recuperación va a una carpeta nueva y exclusiva (nunca mezcla ni pisa la anterior), la ruta se pasa a restic tal cual (sin interpretar `*`, `?` ni `[`), y la carpeta de preparación solo se entrega al usuario cuando root ha terminado de recorrerla.
~ **Rotación de copias**: varias copias parciales seguidas (con archivos saltados) ya no pueden borrar la última copia completa.
~ **Cajas**: sin pasta, la caja con red NO arranca (antes compartía la red del equipo con un aviso). Con el perfil estricto, el filtro seccomp se abre dentro de pasta para que llegue de verdad a bubblewrap. El lanzador de Claude lee su configuración sin seguir enlaces y con tope de tamaño. La prueba de la caja ahora comprueba por separado que el programa arranca, que tiene Internet y que el aislamiento se mantiene.
~ **Cortafuegos y SSH**: el cortafuegos se aplica en una sola transacción, sin reiniciar nftables (en Debian, parar nftables borra todas las reglas, también las de Docker o una VPN). Antes de abrir el puerto de SSH se comprueba la configuración efectiva (`sshd -T`).
~ **Instalación y descargas**: el cerrojo de instalación vive en `/run` (en `/run/lock` cualquiera podía crear el archivo y bloquear el actualizador). Cada `.deb` descargado tiene su propio archivo de root, y toda descarga rechaza redirecciones que no sean HTTPS. El firmware automático lee también las direcciones de varias líneas de las fuentes de apt.

* No se hace en esta versión, y por qué: quitar la ejecución de órdenes como root desde los asistentes y sustituirla por operaciones concretas con Polkit es un rediseño (y esa ejecución es una función que se activa a propósito, apagada por defecto); un perfil de Wine sin acceso a la sesión gráfica para ejecutables desconocidos necesita una sesión gráfica aparte; firmar la ISO entera, fijar npm y Ollama, y el historial/portapapeles/grupos siguen pendientes.

## Beta 0.1.22 · 2026-11-18

Revisión de seguridad de la 0.1.21. Todo lo que sigue sale de una revisión externa del código; cada punto se comprobó antes de arreglarlo.

~ **Aprobaciones de la IA**. El panel enseña la orden entera (sin cortarla y con los caracteres de control a la vista) y no deja permitir lo que no cabe en la ventana. Una orden que hay que aprobar no puede pasar de 1500 caracteres. Una orden aprobada caduca a los dos minutos y, al ejecutarla, se vuelve a comprobar que el asistente sigue activo y con permiso; quitar un permiso ahora frena también lo ya aprobado. Las peticiones sin responder caducan a los diez minutos. Las tareas quedan ligadas al canal que las pidió y los identificadores son más largos. «Archivos sin preguntar» solo vale con el asistente activo y dentro de tu carpeta personal, sin carpetas ocultas.
~ **Servicio de administración**: reconoce al permisor por coincidencia exacta de su unidad, su programa y su orden, y rechaza variables que cambian lo que Python importa.
~ **Solidez del permisor**: la salida de una orden se acota en memoria (solo se guarda el final), hay un tope de conexiones por socket, y la carpeta de sockets se comprueba (propia y privada). El registro aguanta separadores raros en una ruta y anota la orden también antes de ejecutarla.
~ **Mover y deshacer**: sacar un archivo de su carpeta exige poder borrar allí; mover no pisa un destino que aparezca en ese instante, y deshacer un movimiento o un borrado comprueba que el objeto sigue siendo el mismo.
~ **Actualizaciones**: se instala exactamente el commit que se verificó (no lo que el nombre de la versión señale después), el nombre que lleva dentro la etiqueta firmada debe ser el de la versión (una versión antigua firmada ya no puede hacerse pasar por una nueva), y solo corre una instalación o actualización a la vez.
~ **Cajas de IA con red propia**: con `--red` la caja sale a Internet por una red suya (pasta) y ya no comparte la del equipo: no ve los sockets locales (como el de instancia única de kitty) ni los servicios en localhost. Si falta pasta, avisa y comparte la red como antes. El lanzador de Claude usa un archivo temporal único para no seguir enlaces plantados desde la caja.
~ **Instalación y copias**: lo que se escribe en tu carpeta personal lo hace tu usuario y no root, y la recuperación de copias restaura en una carpeta privada y la copia a tu carpeta como tú. Así un enlace simbólico no puede llevar escrituras o cambios de propietario a rutas del sistema. Python se ejecuta aislado en los pasos de instalación.
~ **Instalador USB**: la imagen se abre una sola vez, sin permitir que nadie la modifique, y esos mismos bytes son los que se comprueban y se graban. El paquete de la ISO lleva solo `main` y las etiquetas (antes, todas las ramas). Las imágenes de pruebas lo dicen en el título de cada entrada del menú. El repositorio de paquetes se construye en una carpeta de trabajo nueva y privada.
~ **Programas de terceros**: las claves de los repositorios de Brave y Microsoft se comprueban por su huella antes de instalarlas. Un `.deb` descargado se lee una vez, se enseña su SHA-256 y se entrega a root desde esa copia. El firmware automático solo toma paquetes de los repositorios de debian.org.
~ **Red**: el SSH que deja abierto una máquina virtual de Hyper-V se limita a redes privadas. El cortafuegos de LeksSO sustituye solo su propia tabla y respeta las reglas de otros programas. Al encender el acceso remoto, el servicio lee la configuración nueva en el momento.
~ **Copias de seguridad**: una copia con archivos saltados ya no cuenta como «última copia correcta», y la comprobación incluye una parte al azar de los datos (10 %), no solo la estructura.
~ **Monitores de conexiones e instalaciones**: no se cuelgan si alguien pone una tubería donde esperaban un programa. El botón «Bloquear este destino» solo se ofrece en conexiones que salen a Internet (el bloqueo es de salida). La contraseña de un solo uso del registro de clave de arranque ya no aparece en los argumentos de ningún proceso.

* Límites que se mantienen y ahora están dichos: el origen que anota el registro de instalaciones es una atribución por contexto (un proceso de tu cuenta podría aparentar otro); un programa de Windows en Wine ve tu sesión gráfica (no hay todavía una forma de darle una conexión restringida con este Sway); los scripts de instalación de terceros (Ollama, paquetes npm) no tienen una huella fija contra la que comprobarlos; kitty permite por defecto que los programas escriban en el portapapeles mediante el terminal (se mantiene porque lo usan tmux y SSH); el USB confía en la ISO que se comprobó al grabarlo.

## Beta 0.1.21 · 2026-11-18

+ Tema claro **Alba** (papel cálido con acento azul), en Ajustes → Apariencia. Los iconos de archivos y carpetas y el blanco brillante del terminal siguen el tema, para que también se lea bien en claro.
+ Búsqueda de archivos: una caja en Archivos (Ctrl+F) que encuentra por nombre al instante en tu carpeta personal y en los discos conectados. Usa `plocate`: no deja ningún proceso en marcha; el índice pesa unos 2 MB y se renueva una vez al día.
+ **Copias de seguridad** en Ajustes → Copias, desactivadas hasta que las actives. Eliges la frecuencia (cada día, cada semana o cada mes) y la hora; se guardan las 5 últimas copias y al hacer la sexta se borra la más antigua, solo después de comprobar que la nueva está sana. Se copia tu carpeta personal, cifrada con una clave que eliges tú. La ventana muestra siempre la última copia, la próxima y hasta qué día puedes volver, avisa si el disco es el mismo que el de tus archivos y, si una copia falla, lo ves en la barra. Recuperar archivos los deja en `~/Recuperado`, sin tocar lo que tienes. Si el equipo estaba apagado a la hora elegida, la copia se hace al encenderlo. La IA no puede tocar las copias.
+ **Registro de instalaciones** en Ajustes → Seguridad: qué programas se instalan, cómo y de dónde vienen, con su certeza. «Confirmado» cuando lo prueba quien lo hizo (el catálogo de LeksSO, las actualizaciones, la IA o una sesión SSH), «inferido» cuando se deduce del contexto (por ejemplo, desde un terminal local) y «desconocido» cuando nadie lo anotó. Anota lo que instala apt y detecta, cada pocas horas, programas que aparecen fuera de apt (carpetas de usuario, `/usr/local/bin`, AppImage). El registro está encadenado con hashes, es de solo añadir y tiene un sello que delata cualquier edición; quien tenga permisos de administrador podría borrarlo. La barra avisa solo si hay programas de origen desconocido sin revisar. La IA solo puede leerlo si lo apruebas en el panel y no puede tocarlo.
+ **Monitor de conexiones**: botón de escudo en el rail (se ilumina solo si hay novedad) y pestañas en Ajustes → Seguridad. Muestra qué conexiones hay por categoría (entran desde fuera, salen a Internet, red local y servicios que escuchan), de qué programa es cada una y si está «validada» o «sin validar» (nunca «segura»). Un programa se reconoce por su paquete de Debian, y lo que lanza un programa de confianza (los juegos de Steam, por ejemplo) hereda su confianza. Acciones: **Confiar en esto**, **Parar ahora (puede volver)**, **Bloquear este destino** y **Abrir su carpeta**. Avisa al momento si alguien entra por SSH, marca los programas nuevos sin validar y los que envían mucho más de lo habitual; la primera semana solo aprende, sin avisos. Un temporizador de un minuto, sin ningún proceso residente. Bloquear es permanente hasta que lo quitas en la pestaña Bloqueos, bloquea el destino (IP y puerto) y no al programa, y no deja bloquear el router, el DNS, la hora ni las actualizaciones. El historial se guarda 30 días y se puede borrar. La IA solo puede leerlo con tu aprobación y no puede bloquear, confiar ni parar nada.
~ Los programas `restic` y `plocate` vienen instalados. Timeshift ya no se instala por defecto: queda en el catálogo de aplicaciones para quien quiera puntos de restauración del sistema.

## Beta 0.1.20 · 2026-11-18

+ Tercer tema de color, **Waves** (azul marino con acento celeste), en Ajustes → Apariencia. Cambia todo el escritorio igual que Marea y Pizarra.
- Se quita de la barra lateral el botón del Stream Deck: aparecía siempre, haya o no dispositivo, y sin él no hacía nada. El programa sigue instalado y se abre desde Aplicaciones; al conectar un Stream Deck, su servicio se sigue iniciando solo.
- Se quita de Apariencia el botón «Letra e iconos», que abría la herramienta de configuración de Qt (qt6ct): solo servía para elegir esquemas de colores sueltos que no seguían el tema y confundía con la ventana de Apariencia. Las apps Qt siguen la paleta del tema.
* Primera versión Beta. Sigue sin probarse con hardware real: audio, micrófonos, cámaras, pendrives, tableta, Stream Deck, Bluetooth y Wi-Fi.

## Alpha 0.1.19 · 2026-11-18

~ Apariencia ya cambia todo el escritorio de verdad: además de barra, avisos y bordes, ahora también el terminal (se recarga sin cerrarlo), el panel de la IA, Archivos (incluidos «Lugares» y el árbol de carpetas) y el resto de ventanas de LeksSO, que se repintan solas con el tema nuevo sin cerrarlas ni abrirlas de nuevo. La pantalla de bloqueo estrena también el color del tema.
~ «Lugares» en Archivos ahora muestra Descargas, Documentos, Imágenes, Vídeos y Música además de Inicio y Escritorio: se crean al instalar, porque solo salían las que existían.
- Se quita la configuración del terminal foot, que no usaba nadie (el terminal es kitty).

## Alpha 0.1.18 · 2026-11-18

~ Corrige la actualización a 0.1.17: tras actualizar, la barra y los atajos de la sesión abierta seguían llamando a los comandos con el nombre antiguo y dejaban de funcionar hasta volver a entrar. Ahora los comandos antiguos reenvían a los nuevos durante esa sesión y la barra y el compositor releen su configuración al terminar de actualizar.

## Alpha 0.1.17 · 2026-11-18

+ Ajustes → Apariencia permite elegir el tema de color (Marea o Pizarra) y lo aplica al momento a todo el escritorio: barra, menús, avisos, bordes de ventana, bloqueo y las ventanas de LeksSO. Antes solo cambiaba Archivos. El terminal y las ventanas ya abiertas estrenan el tema al abrirlos de nuevo. «Letra e iconos» sigue en un botón aparte.
+ Con Secure Boot, la clave de firma de controladores y su contraseña de un solo uso se crean solas tras aceptar un aviso una vez, y la contraseña se consulta en Ajustes → Secure Boot, oculta hasta pulsar Ver.
~ El controlador de NVIDIA con Secure Boot se instala en dos fases: primero se registra la clave y se reinicia, y solo después se instala el controlador, para no quedarse sin imagen.
~ El sistema pasa a llamarse LeksSO también por dentro: comandos (`leksso-*`), carpetas (`/etc/leksso`, `~/.config/leksso`) y servicios. Al actualizar, los equipos ya instalados se migran solos y no se pierde ningún dato.

## Alpha 0.1.16 · 2026-11-17

+ VLC viene con el sistema y es el reproductor predeterminado de vídeo y audio.
+ Word, Excel y PowerPoint aparecen en el menú en su versión web de Microsoft 365 (gratis con una cuenta de Microsoft; hace falta internet y los documentos se guardan en tu OneDrive).
+ LibreOffice (Writer, Calc e Impress) en el catálogo de aplicaciones, para trabajar sin conexión: al instalarlo abre .docx, .xlsx y .pptx con doble clic. Sin él, esos archivos explican cómo abrirlos.
~ El botón de modelos de IA de la barra ya no parece muerto: la ventana se queda abierta y dice, en lenguaje llano, si Ollama no está instalado, si no responde o si todavía no hay modelos. Antes se abría y se cerraba al instante.

## Alpha 0.1.15 · 2026-11-17

+ El instalador ofrece cuatro opciones en el menú de arranque: con o sin cifrado del disco, y con o sin contraseña de usuario. Ya no obliga a cifrar ni a tener contraseña. Sin contraseña, el equipo entra solo al escritorio al encender y `sudo` no la pide; es para uso propio, porque quien tenga el equipo delante tiene acceso a todo. Desde la red no se puede entrar sin contraseña.

## Alpha 0.1.14 · 2026-11-17

~ El sistema pasa a llamarse **LeksSO** (Leks + Sistema Operativo). Cambia el nombre que se ve; los comandos (`lekso-*`) y las carpetas siguen igual. El repositorio de GitHub también se llama ahora LeksSO, y el nombre antiguo sigue funcionando para los equipos ya instalados.
~ Colores nuevos, tema **Marea**: fondo petróleo oscuro con acento turquesa, y avisos de OK, aviso y error que ya no se confunden con el acento. Se aplica a barra, ventanas, menús, terminal, avisos, bloqueo y iconos. El tema **Pizarra** (grafito cálido y azul) queda preparado en `scripts/aplicar-tema.py`, sin selector en Ajustes todavía. Solo modo oscuro.
+ Controladores y firmware: a los 3 minutos de arrancar y una vez al día, LeksSO actualiza solo el microcódigo y el firmware de Debian, y avisa si hay un controlador NVIDIA nuevo o una actualización de firmware de dispositivos. Esos dos se instalan con un clic en Ajustes → Actualizaciones, con confirmación y comprobando antes Secure Boot, el espacio libre y que el equipo esté enchufado. `lekso-actualizar hardware detectar` muestra lo que hay.
+ `lekso-actualizar hardware quitar-nvidia` vuelve al controlador libre si el de NVIDIA da problemas.
~ Con el controlador de NVIDIA instalado, el escritorio arranca con `--unsupported-gpu`; sin eso, sway no arranca con ese controlador.
* Con Secure Boot activo no se instala el controlador de NVIDIA: el módulo sin firmar no cargaría. Aún no se puede registrar la clave desde aquí.

## Alpha 0.1.13 · 2026-11-16

~ Docker arranca bajo demanda: ya no se inicia con el equipo (retrasaba el arranque unos 6 segundos y ocupaba unos 135 MB siempre). Se pone en marcha solo con la primera orden `docker`.
~ Reiniciar y apagar ya no se quedan hasta dos minutos esperando a un servicio que no responde (pasaba con el ayudante de Bluetooth `mpris-proxy`): la espera máxima es de 20 segundos.

## Alpha 0.1.12 · 2026-11-16

+ Perfil de energía en la ventana de Energía: Ahorro, Equilibrado o Rendimiento, con lo que hace cada uno.
+ Modo juego (botón del mando en el carril, o `lekso-juego`): pone el perfil de rendimiento y quita la protección del núcleo que frena a algunos juegos de Windows; al apagarlo vuelve todo a como estaba. Se instala GameMode (en Steam: `gamemoderun %command%`).
~ `lekso-apps` dice en cada entrada si es «oficial» (el programa de su fabricante para Linux) o «alternativa» (otro programa, de terceros), y por qué. Antes se confundían. `--todo` ya solo instala lo oficial.
~ `lekso-apps` reconoce Playwright como instalado.

## Alpha 0.1.11 · 2026-11-16

~ Fase de pruebas: las versiones se publican sin firmar (`publicar-version.sh --sin-firma`). Solo las instalan los equipos que tienen `/etc/lekso/sin-firma`; los demás las rechazan.
+ Archivos de LekSO (`lekso-archivos`): el explorador en dos piezas que van juntas. A la izquierda, «Carpetas» (lugares habituales, dispositivos conectados y el árbol); en el centro, el contenido de la carpeta, que es lo que se ve cuando no hay ninguna aplicación abierta. Abrir una aplicación la pone encima, como una pestaña más. En español: abrir, copiar, cortar, pegar (sin pisar nada), renombrar, carpeta nueva, papelera, arrastrar y ver ocultos.
+ Las carpetas se pliegan y despliegan (botón de archivos del carril o Súper+E) para dar más sitio a la aplicación.
~ El explorador completo (pcmanfm-qt) sigue instalado para pestañas, miniaturas y discos; se abre desde el menú de aplicaciones.
~ Panel de la IA: el título de «lo que ha cambiado» ya no se pisa con el texto de debajo. La versión de la barra se refresca cada minuto.

## Alpha 0.1.10 · 2026-11-16

+ Permisos por asistente. Cada asistente (Claude, Codex) tiene los suyos, con casillas en la ventana «Asistentes de IA» (`lekso-asistentes`, o clic derecho en el botón del asistente): usarlo o no; archivos con permiso carpeta a carpeta o sin preguntar; ejecutar órdenes en el equipo con tu usuario; tareas de administrador (no, preguntando cada vez, sin preguntar). Tres niveles de un clic: «Solo archivos», «Este equipo» y «Acceso total».
+ La IA puede operar el equipo: herramienta `ejecutar` (también como administrador si se lo permites). Hace las cosas y cuenta el resultado, en vez de dictarte comandos. Cada orden queda en el registro del panel de la IA.
+ Varios asistentes activos a la vez, cada uno en su ventana.
~ Lo destructivo (borrar carpetas del sistema, formatear, contraseñas, apagar) pide confirmación siempre, sea cual sea el nivel. Es una red de seguridad para lo evidente, no una garantía.
~ Los permisos viven en `/etc/lekso/asistentes.json` y solo se cambian con tu contraseña: un asistente no puede dárselos a sí mismo. La identidad de cada asistente la da su propio canal, no lo que diga.
~ Instalación nueva: asistentes instalados, apagados y en «Solo archivos». La barra avisa («· admin») si alguno puede administrar.
* Aviso: con «Ejecutar órdenes» el asistente actúa con tu usuario y ve todos tus archivos; con «Acceso total», todo el equipo. Un texto malicioso en una web o un archivo podría manipularlo. Actívalo sabiendo eso.

## Alpha 0.1.9 · 2026-11-16

~ Barra: iconos para Wi-Fi, batería (con rayo al cargar y enchufe si está conectada) y volumen, en vez de «Wi-Fi 82%» o «BAT 99%». Los títulos largos ya no empujan los indicadores fuera de la pantalla, y las zonas fijas no aparecen como ventanas.
+ La versión de LekSO se ve en la barra y en el panel de la IA.
~ El estado de la IA muestra el asistente elegido («IA · Claude»), no solo los modelos locales. Clic: abre el panel.
+ El panel de la IA enseña también lo que ha consultado (leer, listar, medir el equipo), no solo lo que ha cambiado.
~ El asistente conoce los comandos propios de LekSO y los recomienda en vez de recetas genéricas de Linux.
~ Los títulos de las zonas ya no muestran sus nombres internos.

## Alpha 0.1.8 · 2026-11-16

+ `lekso-asistente`: elige tu asistente de IA. Claude y Codex vienen instalados pero inactivos; ninguno se usa hasta que lo activas (`lekso-asistente activar claude|codex`). El botón del asistente abre el activo o te deja elegir. `desactivar` lo apaga sin desinstalar.
+ La IA puede medir el equipo: herramienta `estado_equipo` (memoria, disco, CPU, carga, batería, temperaturas y procesos que más consumen). Solo lectura, sin permiso: da cifras y nombres de proceso, nunca archivos ni argumentos.
+ `lekso-codex`: Codex CLI dentro de la caja de IA, conectado al permisor.
~ La instalación incluye Node y los dos asistentes cuando hay conexión; sin red, se instalan al elegirlos.
~ `lekso-claude` avisa con claridad si Claude Code no está instalado, en vez de cerrarse sin explicación.

## Alpha 0.1.7 · 2026-11-16

+ Fase de pruebas en equipos reales: una imagen creada con `construir-iso.sh --fase-pruebas` instala un equipo que acepta actualizaciones sin exigir firma (`/etc/lekso/sin-firma`; se sigue exigiendo que la versión esté en la rama principal) y que arranca con el acceso remoto encendido en la red local. Borrar ese archivo vuelve a exigir firma.
~ El actualizador distingue «no encuentro la versión descargada» de «firma no válida».

## Alpha 0.1.6 · 2026-11-16

~ Los equipos instalados desde USB no podían actualizarse: su copia del repositorio apuntaba al paquete del USB. Ahora el actualizador descarga siempre del repositorio oficial y el instalador lo deja bien al terminar. En un equipo ya instalado con la 0.1.4 o la 0.1.5 desde USB, una sola vez: `sudo git -C /var/lib/lekso/repo remote set-url origin https://github.com/Leksgg/LekSO.git`.

## Alpha 0.1.5 · 2026-11-16

+ `lekso-acceso-remoto on|off|estado`: acceso por SSH a tu equipo, apagado por defecto. Encendido, solo acepta conexiones de la red local, nunca como root, y sobrevive a reinicios y actualizaciones hasta que lo apagues.
+ `scripts/instalador/crear-usb.ps1`: crea la memoria USB de instalación desde Windows. Comprueba la suma y la firma de la imagen, solo ofrece discos USB (nunca el del sistema), pide escribir BORRAR y graba la imagen tal cual.
+ `scripts/instalador/firmar-imagen.sh`: firma la imagen de instalación (suma SHA-256 y firma con la clave de versiones).

## Alpha 0.1.4 · 2026-11-15

+ `scripts/instalar.sh`: instala LekSO sobre un Debian 13 recién instalado. Descarga la versión más reciente (o la indicada), comprueba su firma con la clave incluida en el propio script (nunca con la del repositorio descargado), exige que el commit esté en la rama principal y pide confirmación. Acepta un origen local (`--origen`) para instalar desde un paquete del USB, y `--simular` para comprobarlo todo sin instalar.
+ Firmware y microcódigo según el hardware real (Wi-Fi, sonido, gráficos y control térmico en Intel; microcódigo en AMD), con detección automática de dispositivos. En una máquina virtual no se instala.
+ Instalador en USB que no necesita internet (`scripts/instalador/`): imagen de Debian 13 con firmware más el paquete de LekSO (repositorio local de 789 paquetes, 595 MB, creado con `construir-repo-offline.sh`) y una respuesta automática que borra el disco que elijas, lo cifra (LUKS + LVM), crea el intercambio para hibernar según la RAM (1,2 veces) e instala Debian y LekSO. Solo pregunta lo que decide quien instala: el disco, su usuario, su contraseña, la del cifrado y la confirmación final de borrado. `construir-iso.sh` genera la imagen; la versión que lleva se comprueba con su firma al instalar.
~ El instalador y el endurecimiento funcionan sin red y dentro del instalador de Debian (sin systemd en marcha).
+ `publicar-version.sh --sin-subir`: prepara y firma una versión en local sin publicarla, para probar el instalador antes de subirla.
~ El instalador en USB deja un registro de la instalación en `/var/log/lekso-postinstalar.log` y lleva también el servidor SSH en el repositorio local (solo se usa en las imágenes de prueba).
+ Pruebas del instalador (`scripts/test_instalar.py`): elección de versión, firma buena, de otra clave, sin firmar, huella distinta, commit fuera de la rama principal y una clave de atacante metida en el repositorio.

## Alpha 0.1.3 · 2026-11-15

~ Las teclas de micrófono y brillo avisan cuando el equipo no tiene micrófono o brillo regulable, y la captura de ventana avisa si no hay ninguna activa, en vez de no hacer nada.
+ Cuando la IA pide permiso aparece una notificación («La IA pide permiso», con la carpeta y lo que quiere hacer); al pulsarla se abre el panel donde se aprueba. Antes la petición esperaba en una pestaña que nadie estaba mirando y el asistente parecía bloqueado.
~ El foco del teclado va a la ventana donde haces clic, no a donde se queda el ratón (antes, con el ratón sobre otra ventana, el teclado «no respondía» en la que estabas mirando).
~ El asistente ya no pregunta «¿confías en esta carpeta?» en cada inicio: su carpeta de trabajo, vacía y solo suya, se marca de confianza.
+ La IA puede pedir una carpeta nueva (un nivel, dentro de una que exista): el panel la marca como «carpeta NUEVA: se creará», se crea solo al aprobar y se puede deshacer si sigue vacía. La carpeta personal entera sigue sin poder pedirse.
* El asistente de IA no sabía cuál era la carpeta personal real: veía la de su caja (`/home/caja`) y pedía rutas que el permisor no reconocía. Ahora el adaptador traduce `~/…` y `/home/caja/…` a la carpeta real, y las instrucciones al modelo se lo explican (también que `escribir` crea las carpetas que falten).
~ El reposo bloquea a los 10 minutos, apaga la pantalla a los 15 y suspende a los 30 (solo con batería), en vez de 5, 10 y 25.
~ Pantalla de bloqueo con un mensaje claro («Pantalla bloqueada · escribe tu contraseña y pulsa Intro») y el anillo de contraseña siempre visible: antes era una pantalla oscura vacía y parecía un equipo colgado.

## Alpha 0.1.2 · 2026-11-15

+ Antes de instalar se comprueba también que el commit de la versión pertenece a la rama principal del repositorio; se guarda y se muestra el commit y la firma de lo instalado.
+ `scripts/desbloquear-firma.sh` y `scripts/publicar-version.sh --auto`: publicar la siguiente versión con un solo comando, con la clave de firma protegida por contraseña y desbloqueada unas horas; si algo falla, se deshace la preparación.
+ Pruebas de la verificación (`scripts/test_actualizar.py`): firma buena, de otra clave, sin firmar, etiqueta ligera, inexistente, fuera de la rama principal y nombres de versión hostiles.
~ La comprobación de firma exige que coincida con un firmante autorizado, no solo que exista una firma.
* Una etiqueta con salto de línea final se aceptaba como versión válida; corregido.
~ La ventana de Actualizaciones nombra las versiones por su nombre (Alpha 0.1.1) y muestra solo lo nuevo.

## Alpha 0.1.1 · 2026-11-15

+ Primera actualización de prueba: se publica como versión firmada y llega al equipo con aviso.
~ Ajustes muestra la versión instalada («LekSO Alpha 0.1.1») junto a la información del sistema.
~ El indicador de IA de la barra se actualiza cada 30 segundos en vez de cada 5, con menos despertares del procesador y más batería.

## Alpha 0.1.0 · 2026-11-15

Primera versión de prueba.

+ Escritorio por zonas sobre Debian 13 y sway: raíl de iconos, explorador, centro con terminal, panel de la IA y barra de tareas.
+ Permisor de IA con alcance por tarea, registro firmado y deshacer; caja de Bubblewrap para programas y para la IA; asistente con Claude Code conectado solo al permisor.
+ Instalación repetible (`scripts/provision-base.sh`) y catálogo de aplicaciones (`lekso-apps`).
+ Notificaciones, capturas, portapapeles, ajustes, energía, reposo, red, Bluetooth, discos y Stream Deck.
+ Cortafuegos, actualizaciones de seguridad de Debian y ajustes del núcleo.
+ Versión visible y actualizaciones firmadas: `lekso-actualizar`, Ajustes → Actualizaciones y aviso en la barra.

## 2026-11-15 · Calidad de vida

+ Notificaciones (mako) con la paleta de LekSO, arriba a la derecha.
+ Teclas de volumen, micrófono, brillo y multimedia con aviso en pantalla, también con la pantalla bloqueada.
+ Capturas de pantalla: `Impr` (región), `Mayús+Impr` (pantalla) y `Mod+Impr` (ventana); se guardan en `~/Imágenes/Capturas`, se copian al portapapeles y avisan.
+ Historial del portapapeles (`Mod+V`, botón en el raíl).
+ Ajustes: un solo sitio (`Mod+I`, el engranaje del raíl) para sonido, red, pantallas, Bluetooth, apariencia, impresoras, aplicaciones y modo de energía.
+ Reposo: bloqueo a los 5 minutos, pantalla apagada a los 10 y suspensión a los 25 solo con batería; la pantalla completa (vídeo, juegos, directos) lo impide. `Mod+L` bloquea al momento.
+ Visual Studio Code como editor de código (`lekso-apps instalar code`, repositorio firmado de Microsoft): arranca con Wayland nativo y sin telemetría si el usuario no tiene ya sus ajustes.
- Se quita del raíl el botón «Cuenta», que no hacía nada.
~ Los botones del raíl y la barra funcionan aunque la barra se reinicie a mano: los programas que llaman a sway buscan su socket si no lo heredan.
~ Las ventanas de portapapeles y ajustes flotan en el centro; el gestor de redes (`lekso-redes`) usa los colores de LekSO.
+ Batería en la barra (solo en portátiles), Bluetooth con interfaz, servicio de impresión, miniaturas de vídeo, fuentes con emoji y compatibles con Arial.

## 2026-11-15 · Asistente de IA con Claude Code

+ Adaptador MCP del permisor (`lekso-ia/mcp_permisor.py`, solo biblioteca estándar): ocho herramientas (pedir acceso, listar, leer, escribir, borrar, mover, cerrar tarea y consultar una petición). No expone aprobar, ejecutar programas ni el canal de control. Lo leído se recorta por defecto para ahorrar tokens y el acceso espera la aprobación en una sola llamada.
+ `lekso-claude`: Claude Code dentro de `caja --ia-nube`, con sus herramientas propias desactivadas y solo las del permisor; su sesión vive en una carpeta aparte.
+ `caja --env VAR=VALOR` para pasar variables a la caja de forma explícita.
+ Botón del asistente en el raíl; se acopla como pestaña en la zona derecha.
+ Terminal nueva (kitty, un solo proceso para todas las ventanas) con copiar y pegar como en cualquier otra aplicación: `Ctrl+C` copia si hay texto seleccionado y, si no, interrumpe el programa; `Ctrl+V` pega; seleccionar con el ratón copia solo.
~ foot sigue instalado como alternativa; el resto del sistema abre terminales con `lekso-term`.
+ Botón y atajo (`Mod+M`) para ocultar y mostrar las ventanas flotantes: el «minimizar» de LekSO.
+ Pruebas del adaptador (`lekso-ia/test_mcp.py`): protocolo, flujo completo, argumentos hostiles y entrada gigante.
* La caja del asistente tiene red completa; limitarla al dominio del proveedor queda pendiente.

## 2026-11-15 · Seguridad del equipo, energía y teclado

+ Cortafuegos (`scripts/endurecer.sh`): todo lo entrante bloqueado salvo respuestas a lo que el equipo pide; saliente libre.
+ Actualizaciones de seguridad automáticas (solo el repositorio de seguridad de Debian, sin reinicios automáticos).
+ Ajustes del núcleo: sin espionaje entre procesos, sin lectura de direcciones del sistema y sin eBPF para usuarios sin privilegios. Se siguen permitiendo los espacios de usuario que necesita la caja.
+ Botón de energía en el raíl: bloquear, suspender, hibernar, cerrar sesión, reiniciar y apagar. Solo activa lo que el equipo admite y pide confirmación en lo que cierra programas.
+ El teclado de la sesión sigue al del sistema (español por defecto).
~ El permisor de IA corre como servicio de usuario con filtro de llamadas al sistema y sin permisos de administrador.
~ Los programas de la propia interfaz comparten estilo (`lekso_ui`).
* Corregido en la instalación: la carpeta `~/.local` quedaba a nombre de root.

## 2026-11-15 · Instalar aplicaciones

+ Comando `lekso-apps`: catálogo de equivalentes en Linux de las aplicaciones habituales de Windows (desarrollo, Docker, Playwright, IA, navegadores, comunicación, multimedia, utilidades y juegos). Lista lo instalado, instala por nombre o por grupo, simula con `--simular` y explica lo que no tiene equivalente (`pendientes`).
+ Fuentes: paquetes de Debian, repositorios firmados (Brave, VS Code), descargas directas del proveedor (Discord, Obsidian, Heroic, r2modman) y npm.
~ Al instalar un navegador, pasa a ser el predeterminado para páginas web y enlaces.

## 2026-11-15 · Dispositivos y nombres de ventana

+ Pendrives y discos: automontaje (también NTFS y exFAT) desde el explorador.
+ Soporte de cámaras, listado de USB y Bluetooth instalados.
+ Volumen: indica el dispositivo activo; clic abre el mezclador, clic derecho silencia, la rueda sube o baja.
+ Botón «Aplicaciones» en el raíl: menú flotante con iconos, buscador y botón de cerrar (X, Esc o el propio botón). No se cierra al mover el ratón. Sin entradas técnicas.
+ Stream Deck (streamdeck-ui): se inicia solo al conectarlo, con acceso por USB para el usuario y botón en el raíl para configurarlo.
+ Red con NetworkManager: la barra indica cable o Wi-Fi, IP y puerta de enlace al pasar el ratón; un clic abre el gestor de redes.
~ Las ventanas de la terminal, el editor, el panel de la IA y la información de archivo tienen nombre propio en la barra de tareas.

## 2026-11-15 · Escritorio por zonas

+ Distribución por zonas sobre sway: raíl de iconos a la izquierda, explorador, centro (la app activa, a pantalla completa de su zona) con terminal debajo, y panel de la IA a la derecha.
+ Todo lo que abre el usuario va a la zona central.
+ Barra de tareas abajo, con un botón por ventana (clic para ir a ella, clic central para cerrarla).
+ Botón «Restaurar vista» en el raíl: vuelve a la distribución por defecto sin cerrar las apps abiertas, que pasan a pestañas del centro.
+ El escritorio arranca solo al iniciar sesión en la primera consola.
+ labwc queda como alternativa (ventanas flotantes con minimizar, maximizar y cerrar, e iconos en el escritorio).

## 2026-11-15 · Abrir archivos

+ Programa predeterminado para cada tipo de archivo del sistema (917): editor de texto, visor de imágenes, lector de PDF, reproductor, archivador y, para el resto, una pantalla con la información del archivo.
+ Los programas de Windows se abren dentro de la caja, con solo su carpeta en lectura.
+ `scripts/asociar-archivos.py` rellena solo lo que falta: lo que elija el usuario no se toca.
~ Los binarios de Linux no se ejecutan con doble clic.

## 2026-11-15 · Iconos por tipo de archivo

+ Tema de iconos LekSO: 126 SVG ligeros (unos 150 KB), uno por tipo de archivo, con color por familia y letras (código, web, datos, documentos, imagen, vídeo, audio, paquetes, programas) y carpetas en cian.
+ `scripts/generar-iconos.py` genera el tema; hereda de Adwaita para lo que no define.
~ El script de preparación instala el tema y el complemento SVG de Qt, y deja la carpeta de configuración a nombre del usuario.

## 2026-11-15 · La IA dentro de su caja

+ `caja --ia` y `caja --ia-nube`: la caja de una IA. Dentro entra solo el socket de su canal; no ve archivos ni el socket de control, y para tocar cualquier cosa pide permiso al permisor.
+ El canal de nube siempre pregunta, aunque la carpeta esté recordada.
+ El cliente elige solo el canal que exista en su caja.
+ Prueba `scripts/test_caja_ia.sh`.

## 2026-11-15 · Endurecimiento del permisor y de la caja

+ Registro firmado: las líneas editadas a mano se ignoran.
+ Canal separado para IA en la nube; el destino de lo leído lo fija el canal, no el mensaje.
+ Cada lectura devuelve un aviso de contenido no confiable y marca instrucciones ocultas o caracteres invisibles.
+ Perfil `--estricta` de la caja con filtro seccomp.
+ Pruebas de ataque, de corte brusco, de escapes de la caja y de mutación.
~ Las carpetas se muestran resueltas (sin enlaces) al pedir permiso.
~ Títulos y rutas de una petición solo admiten caracteres imprimibles.
~ Las operaciones que cambian archivos van de una en una.
~ Topes de peticiones pendientes, tareas abiertas y tamaño de mensajes y escrituras.
~ El panel lee solo el final del registro.
~ Leer una tubería o un dispositivo ya no bloquea el permisor.
- Borrar ya no se recuerda entre tareas.
- La caja ya no hereda las variables de entorno.

## 2026-11-15 · Permisor de IA, modelos, panel y explorador

+ Permisor de IA: tareas con carpetas y permisos, registro, deshacer por acción o por tarea, papelera estándar, versiones previas con purga y carpetas recordadas.
+ Gestor de modelos de Ollama con descarga por inactividad y aviso si no cabe en la RAM.
+ Panel de texto para permitir, rechazar y deshacer.
+ Explorador con árbol lateral y ruta con botones.
+ Caja con pantalla, audio y GPU opcionales.
+ Scripts de medición de OBS para Linux y Windows.
+ Licencia MIT.
~ El estado de la IA en la barra sale del gestor de modelos.

## 2026-11-15 · Base y tema

+ Debian 13 mínimo con sway, waybar, foot, fuzzel y pcmanfm-qt; script de preparación repetible.
+ Caja con Bubblewrap: sin red, sin carpeta personal y con el sistema en solo lectura.
+ Tema oscuro común en barra, pestañas y aplicaciones Qt.
