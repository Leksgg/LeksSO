#!/usr/bin/env python3
"""leksso-ia: cliente del usuario para el permisor (aprobar, deshacer, registro) y cliente de la IA.

Usuario: leksso-ia servir | pendientes | aprobar PID [-r] | rechazar PID | registro [N] | verificar
        leksso-ia deshacer ACCION [--forzar] | deshacer-tarea TAREA | recordadas | olvidar RUTA
IA:     leksso-ia ia pedir TITULO RUTA:PERMISOS... | ia estado PID | ia listar|leer|borrar TAREA RUTA
        leksso-ia ia escribir TAREA RUTA TEXTO | ia mover TAREA ORIGEN DESTINO | ia cerrar TAREA
"""
import json
import re
import socket
import subprocess
import sys

import permisor


def hablar(ruta, msg):
    with socket.socket(socket.AF_UNIX) as s:
        s.connect(str(ruta))
        s.sendall((json.dumps(msg) + "\n").encode())
        return json.loads(s.makefile().readline())


def control(**m):
    r = hablar(permisor.rutas()[1], m)
    if not r.get("ok"):
        sys.exit(f"No: {r.get('error')}")
    return r


NUBE = False


def ia(**m):
    local, nube = permisor.rutas()[0], permisor.ruta_nube()
    # Dentro de una caja solo existe el canal que le toca; se usa ese sin que la IA tenga que saberlo.
    usar_nube = NUBE or (not local.exists() and nube.exists())
    return hablar(nube if usar_nube else local, m)


def aprobar(pid, recordar):
    p = control(op="pendientes")["pendientes"].get(pid)
    if not p:
        sys.exit("No hay esa petición pendiente.")
    print(f"\n  La IA pide: {p['titulo']}")
    print(f"  Los datos que lea irán a: {'la NUBE' if p['destino'] == 'nube' else 'el modelo local'}")
    for ruta, perms in p["carpetas"].items():
        nombres = {"r": "leer", "w": "escribir", "d": "borrar (a la papelera)"}
        print(f"  Carpeta {ruta}: " + ", ".join(nombres[x] for x in perms)
              + ("   (carpeta NUEVA: se creará)" if ruta in p.get("nuevas", []) else ""))
    if input("\n  ¿Permitir? [s/N] ").strip().lower() != "s":
        control(op="rechazar", pid=pid)
        return print("  Rechazada.")
    r = control(op="aprobar", pid=pid, recordar=recordar)
    print(f"  Aprobada. Tarea {r['tarea']}.")


def ultimo_sello_del_diario():
    """La última cabeza que el permisor dejó en el diario del sistema, o None si no se puede leer (no hay journalctl o el
    usuario no tiene permiso). El usuario no puede reescribir ese diario: es lo que ancla el registro."""
    try:
        r = subprocess.run(["journalctl", "-t", "leksso-permisor", "-o", "cat", "-n", "200", "--no-pager"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    cabezas = re.findall(r"sello n=\d+ cabeza=([0-9a-f]{64})", r.stdout)
    return cabezas[-1] if cabezas else None


def main(a):
    if not a:
        return print(__doc__)
    c = a[0]
    if c == "servir":
        return permisor.servir()
    if c == "pendientes":
        for pid, p in control(op="pendientes")["pendientes"].items():
            print(pid, p["titulo"], p["carpetas"], p["destino"])
    elif c == "aprobar":
        aprobar(a[1], "-r" in a)
    elif c == "rechazar":
        control(op="rechazar", pid=a[1])
    elif c == "registro":
        for r in control(op="registro", n=int(a[1]) if len(a) > 1 else 20)["registro"]:
            marca = "  " if r.get("ok", True) else "NO"
            print(marca, r.get("t", ""), r.get("id", r.get("deshace", "")), r.get("accion", "deshace"),
                  r.get("ruta", ""), r.get("motivo", ""))
    elif c == "verificar":
        sello = ultimo_sello_del_diario()
        v = control(op="verificar", sello=sello)["verificacion"]
        print(f"Líneas válidas: {v['lineas']}   cortes en la cadena: {v['cortes']}   firmas falsas: {v['invalidas']}")
        if sello is None:
            print("No se pudo leer el diario del sistema (hacen falta permisos: sudo leksso-ia verificar): solo se comprobó la cadena.")
        else:
            print("Sello del sistema:", "COINCIDE con el registro" if v["sello_del_sistema"] else "NO aparece en el registro: faltan líneas")
        print("TODO BIEN" if v["ok"] else "REVISAR: el registro no es de fiar")
        sys.exit(0 if v["ok"] else 1)
    elif c == "deshacer":
        control(op="deshacer", accion=a[1], forzar="--forzar" in a)
        print("Deshecho.")
    elif c == "deshacer-tarea":
        print(control(op="deshacer_tarea", tarea=a[1], forzar="--forzar" in a)["n"], "acciones deshechas.")
    elif c == "recordadas":
        for k, v in control(op="recordadas")["recordadas"].items():
            print(v, k)
    elif c == "olvidar":
        control(op="olvidar", ruta=a[1])
    elif c == "ia":
        global NUBE
        if "--nube" in a:               # canal de las IA en la nube
            NUBE = True
            a = [x for x in a if x != "--nube"]
        o = a[1]
        if o == "pedir":
            carpetas = dict(x.rsplit(":", 1) for x in a[3:])
            r = ia(op="pedir", titulo=a[2], carpetas=carpetas)
        elif o == "estado":
            r = ia(op="estado", pid=a[2])
        elif o in ("listar", "leer", "borrar"):
            r = ia(op=o, tarea=a[2], ruta=a[3])
        elif o == "escribir":
            r = ia(op=o, tarea=a[2], ruta=a[3], texto=a[4])
        elif o == "mover":
            r = ia(op=o, tarea=a[2], origen=a[3], destino=a[4])
        else:
            r = ia(op=o, tarea=a[2])
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
