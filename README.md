# LeksSO

Un sistema operativo de escritorio ligero, construido sobre Debian 13, pensado para que se entienda: todo se maneja con ventanas claras, nada se instala ni se actualiza solo, y una IA solo puede tocar lo que tú le concedes, cuando se lo pides.

Está en uso diario en equipos reales. Las versiones normales son solo un número (`0.1.48`); las de prueba llevan `-alpha`, `-beta` o `-rc`.

## Qué te encuentras al encender

- **Un escritorio en tres zonas.** A la izquierda, una barra de botones (el raíl). En el centro, el explorador de archivos y tus programas, en pestañas. A la derecha, el panel de la IA. Los tamaños se guardan solos.
- **El raíl.** Aplicaciones, archivos, seguridad, portapapeles, cámara y micrófono, notificaciones, acceso remoto, captura de pantalla, actualizaciones, asistentes de IA, modo juego y ajustes. Abajo: minimizar y apagar.
- **La barra de abajo.** Programas abiertos, uso del procesador y la memoria, volumen, red, batería con su modo de energía, y la hora. Un clic en la hora abre un calendario con los festivos; un clic en la red, una ventana para elegir wifi.
- **Siete apariencias.** Grafito (la de serie) y Grafito claro, Waves y Waves claro, Pizarra, Gris y rosa y Blanco y rosa. Cambian todo el escritorio a la vez, también la pantalla de bloqueo. La ventana de Apariencia enseña una miniatura de cada una y, en «Tamaño», deja ajustar las cifras de la barra y la escala del escritorio.
- **Pantalla de bloqueo** con la hora en grande, de quién es la sesión y un ojo para ver la contraseña mientras la escribes.
- **Ajustes en una sola ventana.** Sonido, red, pantallas, Bluetooth, apariencia, impresoras (también por wifi), discos, copias de seguridad, reposo, cifrado del disco y acceso remoto.

## Programas

- **Aplicaciones → Para instalar** lista lo que LeksSO sabe instalar por ti (OBS, Steam, Discord, VS Code y más), por grupos y con buscador. Un clic abre una terminal que lo instala: pregunta antes y pide tu contraseña. También desde la terminal: `leksso-apps`.
- **Juegos.** Steam con Proton, y un modo juego que ajusta el equipo mientras juegas.
- **Programas de Windows.** `leksso-wine` abre un `.exe` dentro de una caja: solo ve su propia carpeta.
- **Navegador.** Brave, instalado de serie.

## Seguridad

- **La IA actúa bajo petición.** No lee ni indexa nada por su cuenta. Cada tarea lleva su alcance (leer, escribir, borrar) y sus permisos; cada acción queda en un registro firmado y se puede deshacer. Funciona con modelos locales (Ollama) y con asistentes en la nube dentro de una caja.
- **Cajas.** Un programa dentro de una caja no tiene red, no ve tus archivos y encuentra el sistema en solo lectura, salvo lo que le abras (`caja`, hecha con Bubblewrap).
- **Conexiones a la vista.** El botón de seguridad enseña qué programas se conectan a internet y a dónde, y deja bloquear un destino.
- **Cámara y micrófono.** Un panel para silenciar el micrófono y **bloquear la cámara de verdad** (se descarga su controlador: ningún programa puede usarla). Bloquear no pide contraseña; volver a permitirla, sí.
- **Actualizaciones firmadas.** Solo se instalan versiones firmadas con la clave de LeksSO, cuando tú pulsas «Actualizar». Se puede volver a la anterior.
- **Acceso remoto apagado de serie.** Al encenderlo en «solo red local», otro equipo de tu red puede **pedir entrar** (`leksso-solicitud pedir DIRECCIÓN`): en tu pantalla sale una ventana con un código de dos palabras que debe coincidir en los dos equipos, y solo entra si pulsas «Permitir».
- **Ayuda a distancia con permiso.** Quien tiene acceso puede pedir ver tu pantalla (`leksso-pantalla pedir`): sale una ventana para permitirlo cada vez, un aviso rojo mientras dura y un botón PARAR. El botón «Acceso remoto» del raíl enseña quién puede entrar y deja quitarlo.
- **Disco cifrado** opcional, con clave al arrancar o desbloqueo con el TPM del equipo. Cortafuegos activo y arranque seguro (Secure Boot) compatible.

## Instalar

**Sobre un Debian 13 recién instalado, sin escritorio:**

```sh
wget https://raw.githubusercontent.com/Leksgg/LeksSO/v0.1.48/scripts/instalar.sh
sudo bash instalar.sh
```

El instalador descarga la última versión, **comprueba su firma** con la clave incluida en el propio script (huella `SHA256:E5cacFQkhc7QCOXvlEa16/iiuqXTI4XFwuz22zbQg8I`), te enseña qué va a hacer y pide confirmación. Con `--simular` lo comprueba todo sin instalar nada.

**Desde un pendrive, sin red:** `scripts/instalador/` construye una imagen de instalación a partir del Debian oficial, con un repositorio de paquetes incluido. Ofrece disco cifrado o sin cifrar, usuario con o sin contraseña, y una entrada experimental para instalar junto a Windows en el mismo disco.

## Actualizar

Cuando sale una versión nueva, el botón de actualizaciones del raíl se pone en ámbar y aparece un aviso en la barra. Se instala desde ahí o con `sudo leksso-actualizar aplicar`. La versión instalada se ve con `leksso-actualizar version`. Lo que cambia en cada versión está en [CHANGELOG.md](CHANGELOG.md).

## Principios

- **Ligero.** En reposo usa alrededor de 1 GB de memoria. Sin tienda, sin widgets, sin telemetría.
- **Claro.** Textos cortos, ventanas con botón de cerrar, y nada que obligue a usar el teclado si se puede hacer con el ratón.
- **Nada ocurre solo.** Instalar, actualizar, permitir una conexión o dar acceso a la IA: siempre lo decides tú, y siempre se puede deshacer o apagar.
- **No reescribir lo que ya existe.** Debian, sway, waybar, Bubblewrap, Wine, Ollama y NetworkManager hacen el trabajo; LeksSO los une y les pone una cara coherente.

## Qué hay en el repositorio

| Carpeta | Qué es |
| --- | --- |
| `config/` | El escritorio: sway, waybar, apariencias, y las herramientas con ventana (`config/bin/`: ajustes, menú, redes, calendario, bloqueo, cámara, notificaciones…). |
| `leksso-ia/` | El permisor de IA: alcance por tarea, registro firmado, deshacer, gestor de modelos y panel. |
| `scripts/` | Instalación y mantenimiento: `instalar.sh`, `provision-base.sh` (prepara el sistema), `leksso-actualizar.py`, `leksso-apps.py` (catálogo), `leksso-solicitud.py`, `caja.sh`, copias de seguridad. |
| `scripts/instalador/` | Construcción de la imagen de instalación y del pendrive. |

## Pruebas

Cada pieza tiene sus pruebas en `scripts/test_*.py` y en `leksso-ia/`. Requieren Linux, Python 3 y Bubblewrap.

```sh
for t in scripts/test_*.py; do python3 "$t"; done
python3 scripts/mutar_tema.py           # mutación de temas y tamaño: rompe cada pieza en una copia y exige que una prueba lo note

cd leksso-ia
PYTHONPATH=. python3 -m unittest test_nucleo test_modelo test_ataques
bash prueba_e2e.sh
bash ../scripts/test_caja_ataques.sh
python3 mutar.py                        # mutación del permisor (defensas de la IA)
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
