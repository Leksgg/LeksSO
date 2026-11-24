#!/usr/bin/env python3
"""Contexto de seguridad de Wayland para las cajas con ventana (hallazgo 1 de la revisión de la 0.1.52).

Antes, `caja --gui` metía en la caja el socket Wayland de la sesión tal cual. Con ese socket un programa enjaulado puede
pedir a sway la captura de pantalla, el historial del portapapeles, un teclado y un ratón virtuales (con los que
pulsaría Súper+Intro y escribiría en una terminal) y la lista de todas las ventanas. El protocolo wp_security_context_v1
existe para quitarle todo eso: este programa crea un socket NUEVO, lo registra en sway como «de una caja» y es ese el
que se monta dentro. sway deja de enseñarle por él los protocolos privilegiados.

  leksso-contexto-wayland servir [--app-id ID] [--host SOCKET] [--vigilar PID]
      Crea el socket restringido, lo registra y escribe su ruta en la primera línea de la salida. Se queda vivo mientras
      exista el proceso PID (caja.sh se lo pasa; sin --vigilar, mientras la entrada siga abierta) o hasta SIGTERM: al
      morir, sway deja de aceptar conexiones por ese socket. Lo lanza caja.sh; no hace falta teclearlo.
  leksso-contexto-wayland globales [SOCKET]
      Lista los protocolos que enseña un socket (el de la sesión si no se dice cuál). Sirve para comprobar el filtro.

Por qué Python y no un binario compilado: el protocolo son dos interfaces y siete mensajes sin eventos, el programa se
lanza una vez por caja (la velocidad no cuenta) y así no hace falta compilar nada en cada equipo ni guardar binarios en el
repositorio. Solo biblioteca estándar (socket.send_fds pasa los descriptores).
"""
import os
import select
import signal
import socket
import struct
import sys
import tempfile

GESTOR = "wp_security_context_manager_v1"
MOTOR = "leksso-caja"           # «sandbox engine» que se anota en sway
ID_DISPLAY = 1                  # el objeto wl_display siempre es el 1


class ErrorWayland(Exception):
    pass


def cadena(texto):
    """Una cadena del protocolo: longitud (con el cero final) y bytes, rellenado a múltiplo de 4."""
    datos = texto.encode("utf-8") + b"\0"
    return struct.pack("=I", len(datos)) + datos + b"\0" * (-len(datos) % 4)


def leer_cadena(payload, pos):
    (n,) = struct.unpack_from("=I", payload, pos)
    texto = payload[pos + 4:pos + 4 + max(n - 1, 0)].decode("utf-8", "replace")
    return texto, pos + 4 + n + (-n % 4)


def ruta_de_socket(host=None):
    """El socket Wayland de la sesión: WAYLAND_DISPLAY (relativo a XDG_RUNTIME_DIR o absoluto)."""
    nombre = host or os.environ.get("WAYLAND_DISPLAY") or "wayland-0"
    if os.path.isabs(nombre):
        return nombre
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        raise ErrorWayland("no hay XDG_RUNTIME_DIR: ¿es una sesión gráfica?")
    return os.path.join(base, nombre)


class Conexion:
    """Lo mínimo del cliente Wayland: enviar peticiones (con descriptores) y leer eventos."""

    def __init__(self, ruta):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(10)
        try:
            self.s.connect(ruta)
        except OSError as e:
            self.s.close()
            raise ErrorWayland(f"no puedo conectar con {ruta}: {e}")
        self.siguiente = 2
        self.buf = b""

    def nuevo_id(self):
        i = self.siguiente
        self.siguiente += 1
        return i

    def enviar(self, objeto, opcode, args=b"", fds=()):
        msg = struct.pack("=II", objeto, ((8 + len(args)) << 16) | opcode) + args
        if fds:
            socket.send_fds(self.s, [msg], list(fds))
        else:
            self.s.sendall(msg)

    def evento(self):
        """El siguiente mensaje del servidor: (objeto, opcode, datos)."""
        while True:
            if len(self.buf) >= 8:
                objeto, cab = struct.unpack_from("=II", self.buf)
                tam = cab >> 16
                if tam < 8:
                    raise ErrorWayland("mensaje del servidor mal formado")
                if len(self.buf) >= tam:
                    datos = self.buf[8:tam]
                    self.buf = self.buf[tam:]
                    return objeto, cab & 0xFFFF, datos
            try:
                trozo = self.s.recv(65536)
            except socket.timeout:
                raise ErrorWayland("el compositor no contesta")
            if not trozo:
                raise ErrorWayland("el compositor cerró la conexión")
            self.buf += trozo

    def sincronizar(self, al_recibir=None):
        """Pide un wl_display.sync y procesa los eventos hasta que llega: todo lo anterior ya está atendido."""
        cb = self.nuevo_id()
        self.enviar(ID_DISPLAY, 0, struct.pack("=I", cb))
        while True:
            objeto, op, datos = self.evento()
            if objeto == ID_DISPLAY and op == 0:                      # wl_display.error
                _, codigo = struct.unpack_from("=II", datos)
                texto, _ = leer_cadena(datos, 8)
                raise ErrorWayland(f"el compositor rechazó la petición (código {codigo}): {texto}")
            if objeto == cb and op == 0:                              # wl_callback.done
                return
            if al_recibir:
                al_recibir(objeto, op, datos)

    def cerrar(self):
        self.s.close()


def globales_de(ruta):
    """{interfaz: (nombre, versión)} de lo que ese socket deja ver."""
    c = Conexion(ruta)
    try:
        reg = c.nuevo_id()
        c.enviar(ID_DISPLAY, 1, struct.pack("=I", reg))              # wl_display.get_registry
        encontrados = {}

        def global_(objeto, op, datos):
            if objeto == reg and op == 0:                             # wl_registry.global
                (nombre,) = struct.unpack_from("=I", datos)
                interfaz, pos = leer_cadena(datos, 4)
                (version,) = struct.unpack_from("=I", datos, pos)
                encontrados[interfaz] = (nombre, version)
        c.sincronizar(global_)
        return encontrados
    finally:
        c.cerrar()


def registrar(ruta_host, ruta_nueva, app_id, instancia, escucha, cierre):
    """Registra en el compositor el socket que escucha en ruta_nueva como el de una caja. Lanza ErrorWayland si no puede.
    escucha: socket ya ligado y escuchando. cierre: extremo de lectura de una tubería; sway deja de aceptar conexiones
    cuando el otro extremo se cierra."""
    c = Conexion(ruta_host)
    try:
        reg = c.nuevo_id()
        c.enviar(ID_DISPLAY, 1, struct.pack("=I", reg))
        vistos = {}

        def global_(objeto, op, datos):
            if objeto == reg and op == 0:
                (nombre,) = struct.unpack_from("=I", datos)
                interfaz, pos = leer_cadena(datos, 4)
                (version,) = struct.unpack_from("=I", datos, pos)
                vistos[interfaz] = (nombre, version)
        c.sincronizar(global_)
        if GESTOR not in vistos:
            raise ErrorWayland("este compositor no admite wp_security_context_v1 (hace falta sway 1.9 o más nuevo)")
        nombre, version = vistos[GESTOR]
        gestor = c.nuevo_id()
        c.enviar(reg, 0, struct.pack("=I", nombre) + cadena(GESTOR) + struct.pack("=II", min(version, 1), gestor))   # wl_registry.bind
        ctx = c.nuevo_id()
        c.enviar(gestor, 1, struct.pack("=I", ctx), fds=[escucha.fileno(), cierre])       # create_listener(id, listen_fd, close_fd)
        c.enviar(ctx, 1, cadena(MOTOR))                                                   # set_sandbox_engine
        c.enviar(ctx, 2, cadena(app_id))                                                  # set_app_id
        c.enviar(ctx, 3, cadena(instancia))                                               # set_instance_id
        c.enviar(ctx, 4)                                                                  # commit
        c.sincronizar()                                                                   # si algo falla, llega como error
        c.enviar(ctx, 0)                                                                  # destroy: el socket sigue activo
        c.enviar(gestor, 0)
        c.sincronizar()
    finally:
        c.cerrar()


def _vive(pid):
    """¿Sigue en marcha ese proceso? Un zombi (terminó pero quien lo lanzó aún no lo ha recogido) cuenta como muerto:
    con os.kill(pid, 0) seguiría «vivo», y si quien lo lanzó espera a que se cierre nuestra salida, nadie avanzaría."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            estado = f.read().rsplit(b")", 1)[1].split()[0]
        return estado not in (b"Z", b"X")
    except FileNotFoundError:
        return False
    except (OSError, IndexError):
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def servir(app_id, host=None, salida=sys.stdout, entrada=sys.stdin, vigilar=None):
    """vigilar: PID de quien me lanza (caja.sh): termino cuando ese proceso deja de existir, sin depender de que ninguna
    tubería llegue hasta la caja. Sin vigilar, termino al cerrarse la entrada."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        raise ErrorWayland("no hay XDG_RUNTIME_DIR: ¿es una sesión gráfica?")
    try:
        carpeta = tempfile.mkdtemp(prefix="leksso-contexto-", dir=base)      # 0700: solo el usuario
    except OSError as e:
        raise ErrorWayland(f"no puedo crear el socket en {base}: {e}")
    ruta = os.path.join(carpeta, "wayland-0")
    escucha = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    leer, escribir = os.pipe()
    try:
        escucha.bind(ruta)
        escucha.listen(16)
        registrar(ruta_de_socket(host), ruta, app_id, os.urandom(8).hex(), escucha, leer)
        os.close(leer)                                                       # sway ya tiene su copia
        leer = None
        salida.write(ruta + "\n")
        salida.flush()
        if vigilar is not None:                                              # ya no hablo con nadie: suelto el terminal de quien me lanzó
            try:
                nulo = os.open(os.devnull, os.O_RDWR)
                os.dup2(nulo, 2)
                os.close(nulo)
            except OSError:
                pass
        terminar = []
        signal.signal(signal.SIGTERM, lambda *_: terminar.append(1))
        signal.signal(signal.SIGINT, lambda *_: terminar.append(1))
        while not terminar:
            if vigilar is not None:
                if not _vive(vigilar):                                       # la caja terminó: fin
                    break
                select.select([], [], [], 1.0)
                continue
            try:
                ya, _, _ = select.select([entrada], [], [], 1.0)
            except (InterruptedError, ValueError, OSError):
                break
            if ya and not entrada.readline():                                # quien me lanzó cerró la entrada: fin
                break
        return 0
    finally:
        # al cerrar la tubería, sway deja de aceptar conexiones por este socket
        for fd in (escribir, leer):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        escucha.close()
        try:
            os.unlink(ruta)
            os.rmdir(carpeta)
        except OSError:
            pass


def main(a):
    try:
        if a[:1] == ["servir"]:
            app_id, host, vigilar, resto = "leksso.caja", None, None, a[1:]
            while resto:
                if resto[0] == "--app-id" and len(resto) > 1:
                    app_id, resto = resto[1], resto[2:]
                elif resto[0] == "--host" and len(resto) > 1:
                    host, resto = resto[1], resto[2:]
                elif resto[0] == "--vigilar" and len(resto) > 1 and resto[1].isdigit():
                    vigilar, resto = int(resto[1]), resto[2:]
                else:
                    print(__doc__)
                    return 2
            return servir(app_id, host, vigilar=vigilar)
        if a[:1] == ["globales"] and len(a) <= 2:
            for nombre in sorted(globales_de(ruta_de_socket(a[1] if len(a) > 1 else None))):
                print(nombre)
            return 0
    except ErrorWayland as e:
        print(f"leksso-contexto-wayland: {e}", file=sys.stderr)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
