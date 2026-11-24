"""Órdenes en el equipo: quién puede ejecutar qué, qué pregunta siempre y que la identidad la da el canal."""
import json
import os
import tempfile
import unittest

os.environ["LEKSSO_SIN_AVISOS"] = "1"
_TMP = tempfile.mkdtemp()
os.environ["LEKSSO_ASISTENTES"] = os.path.join(_TMP, "asistentes.json")

import asistentes  # noqa: E402
import permisor  # noqa: E402
from nucleo import Denegado  # noqa: E402


def fijar(**por_asistente):
    with open(os.environ["LEKSSO_ASISTENTES"], "w", encoding="utf-8") as f:
        json.dump({permisor._usuario(): por_asistente}, f)


class Ordenes(unittest.TestCase):
    def setUp(self):
        self.p = permisor.Permisor(tempfile.mkdtemp())
        self.hechas = []
        self.p.correr = {False: lambda o, e, c: self._corre("usuario", o), True: lambda o, e, c: self._corre("root", o)}

    def _corre(self, quien, orden):
        self.hechas.append((quien, orden))
        return {"codigo": 0, "salida": "ok"}

    def ia(self, asistente, **m):
        return self.p.manejar_ia(m, "nube", asistente)

    def test_sin_permiso_no_ejecuta(self):
        fijar(claude={"activo": True})
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", orden="ls")
        self.assertEqual(self.hechas, [])

    def test_desactivado_no_ejecuta(self):
        fijar(claude={"activo": False, "comandos": True, "admin": "libre"})
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", orden="ls")

    def test_comandos_si_admin_no(self):
        fijar(claude={"activo": True, "comandos": True})
        self.assertEqual(self.ia("claude", op="ejecutar", orden="ls")["codigo"], 0)
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", orden="apt update", admin=True)
        self.assertEqual(self.hechas, [("usuario", "ls")])

    def test_la_ia_no_toca_las_copias_ni_con_permiso_libre(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"})
        for orden in ("sudo leksso-copias desactivar", "rm -rf /var/lib/leksso-copias", "cat /etc/leksso/copias.key",
                      "restic -r /var/lib/leksso-copias forget --keep-last 0 --prune", "systemctl stop leksso-copias.timer",
                      "cat /var/lib/leksso/copias.json"):
            for admin in (False, True):
                with self.assertRaises(Denegado, msg=orden):
                    self.ia("claude", op="ejecutar", orden=orden, admin=admin)
        self.assertEqual(self.hechas, [])
        self.assertEqual(self.ia("claude", op="ejecutar", orden="ls")["codigo"], 0)     # lo demás sigue como siempre

    def test_registro_de_seguridad_leer_pide_permiso_y_tocar_nunca(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"})
        for orden in ("leksso-auditoria listar", "sudo -n leksso-auditoria listar --ultimos 50", "sudo leksso-auditoria verificar"):
            for admin in (False, True):
                r = self.ia("claude", op="ejecutar", orden=orden, admin=admin)
                self.assertEqual(r["estado"], "pendiente", orden)          # no se ejecuta: espera al usuario
                self.assertEqual(r["motivo"], "registro de seguridad")
        self.assertEqual(self.hechas, [])
        for orden in ("sudo leksso-auditoria revisar 3", "leksso-auditoria anotar --nombre x --modo y",
                      "cat /var/lib/leksso-auditoria/instalaciones.jsonl", "rm /var/lib/leksso-auditoria/instalaciones.jsonl",
                      "chattr -a /var/lib/leksso-auditoria/instalaciones.jsonl", "echo x > /etc/leksso/auditoria.ancla",
                      "leksso-auditoria listar; rm -rf /var/lib/leksso-auditoria", "cat /etc/apt/apt.conf.d/99leksso-auditoria"):
            for admin in (False, True):
                with self.assertRaises(Denegado, msg=orden):
                    self.ia("claude", op="ejecutar", orden=orden, admin=admin)
        self.assertEqual(self.hechas, [])

    def test_monitor_de_conexiones_leer_pide_permiso_y_actuar_nunca(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"})
        for orden in ("leksso-conexiones listar", "sudo -n leksso-conexiones estado"):
            for admin in (False, True):
                r = self.ia("claude", op="ejecutar", orden=orden, admin=admin)
                self.assertEqual((r["estado"], r["motivo"]), ("pendiente", "registro de seguridad"), orden)
        self.assertEqual(self.hechas, [])
        for orden in ("sudo leksso-conexiones confiar pkg:malware", "leksso-conexiones bloquear 1.2.3.4", "leksso-conexiones desbloquear ab12cd34",
                      "sudo leksso-conexiones parar x 1 /bin/x", "nft flush table inet leksso_usuario", "nft delete table inet leksso_usuario",
                      "cat /var/lib/leksso-conexiones/confiables.json", "rm /var/lib/leksso-conexiones/bloqueos.json",
                      "systemctl stop leksso-conexiones-foto.timer"):
            for admin in (False, True):
                with self.assertRaises(Denegado, msg=orden):
                    self.ia("claude", op="ejecutar", orden=orden, admin=admin)
        self.assertEqual(self.hechas, [])

    def test_regla_de_copias_sin_falsos_positivos(self):
        for ok in ("ls ~/Documentos", "apt update", "git status", "echo hola"):
            self.assertFalse(asistentes.toca_copias(ok), ok)
        for mal in ("leksso-copias estado", "LEKSSO_COPIAS=1 x", "/etc/leksso/copias.key", "restic snapshots"):
            self.assertTrue(asistentes.toca_copias(mal), mal)

    def test_cada_asistente_sus_permisos(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"}, codex={"activo": True})
        self.ia("claude", op="ejecutar", orden="apt update", admin=True)
        with self.assertRaises(Denegado):
            self.ia("codex", op="ejecutar", orden="apt update", admin=True)
        with self.assertRaises(Denegado):
            self.ia("codex", op="ejecutar", orden="ls")
        self.assertEqual(self.hechas, [("root", "apt update")])

    def test_canal_sin_asistente_no_ejecuta(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"})
        for canal in (None, "otro"):
            with self.assertRaises(Denegado):
                self.ia(canal, op="ejecutar", orden="ls")
        # el nombre dentro del mensaje no cuenta: manda el canal
        with self.assertRaises(Denegado):
            self.p.manejar_ia({"op": "ejecutar", "orden": "ls", "asistente": "claude"}, "nube", None)

    def test_lo_destructivo_como_admin_espera_al_usuario(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"})
        r = self.ia("claude", op="ejecutar", orden="reboot", admin=True)
        self.assertEqual(r["estado"], "pendiente")
        self.assertEqual(self.hechas, [])
        with self.assertRaises(Denegado):                       # sin aprobar no se puede ejecutar por pid
            self.ia("claude", op="ejecutar", pid=r["pid"])
        self.p.manejar_control({"op": "aprobar", "pid": r["pid"]})
        self.assertEqual(self.ia("claude", op="estado", pid=r["pid"])["estado"], "aprobada")
        self.assertEqual(self.ia("claude", op="ejecutar", pid=r["pid"])["codigo"], 0)
        self.assertEqual(self.hechas, [("root", "reboot")])
        with self.assertRaises(Denegado):                       # una aprobación vale para una sola ejecución
            self.ia("claude", op="ejecutar", pid=r["pid"])

    def test_orden_aprobada_no_la_usa_otro_asistente(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"},
              codex={"activo": True, "comandos": True})
        r = self.ia("claude", op="ejecutar", orden="reboot", admin=True)
        self.p.manejar_control({"op": "aprobar", "pid": r["pid"]})
        with self.assertRaises(Denegado):
            self.ia("codex", op="ejecutar", pid=r["pid"])
        self.assertEqual(self.hechas, [])

    def test_rechazada_no_se_ejecuta(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"})
        r = self.ia("claude", op="ejecutar", orden="reboot", admin=True)
        self.p.manejar_control({"op": "rechazar", "pid": r["pid"]})
        self.assertEqual(self.ia("claude", op="estado", pid=r["pid"])["estado"], "rechazada")
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", pid=r["pid"])

    def test_lo_destructivo_pregunta_aunque_sea_acceso_total(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "libre"})
        for orden, admin in (("rm -rf /", True), ("rm -rf ~", False), ("mkfs.ext4 /dev/sda1", True),
                             ("dd if=/dev/zero of=/dev/nvme0n1", True), ("passwd a04", True), ("reboot", True),
                             ("echo x >> /etc/sudoers", True)):
            r = self.ia("claude", op="ejecutar", orden=orden, admin=admin)
            self.assertEqual(r.get("estado"), "pendiente", orden)
            self.p.pendientes.clear()           # la cuota por canal no es lo que se prueba aquí
        self.assertEqual(self.hechas, [])

    def test_lo_normal_no_se_marca_destructivo(self):
        for orden in ("apt install -y htop", "rm -rf ./build", "rm archivo.txt", "systemctl restart ssh",
                      "ls /etc", "df -h", "rm -rf /tmp/pruebas/cosa"):
            self.assertFalse(asistentes.destructivo(orden), orden)

    def test_ordenes_no_validas(self):
        fijar(claude={"activo": True, "comandos": True})
        for mala in ("", "x" * 9000, "ls\0rm", 7, None):
            with self.assertRaises(Denegado):
                self.ia("claude", op="ejecutar", orden=mala)

    def test_queda_en_el_registro(self):
        fijar(claude={"activo": True, "comandos": True})
        self.ia("claude", op="ejecutar", orden="ls -la")
        ultima = self.p.n.ultimas(1)[0]
        self.assertEqual(ultima["accion"], "orden")
        self.assertIn("[claude] ls -la", ultima["ruta"])

    def test_archivos_libre_concede_sin_preguntar(self):
        casa = str(self.p.n.casa)
        os.makedirs(os.path.join(casa, "docs"))
        fijar(claude={"activo": True, "archivos": "libre"}, codex={"activo": True})
        pide = {"op": "pedir", "titulo": "leer", "carpetas": {os.path.join(casa, "docs"): "r"}}
        self.assertEqual(self.p.manejar_ia(dict(pide), "nube", "claude")["estado"], "aprobada")
        self.assertEqual(self.p.manejar_ia(dict(pide), "nube", "codex")["estado"], "pendiente")

    def test_quien_administra_tambien_ejecuta(self):
        self.assertTrue(asistentes.validar({"admin": "libre"})["comandos"])
        self.assertEqual(asistentes.validar({"admin": "raro", "archivos": 3})["admin"], "no")


    # ----- los cinco niveles -----
    def test_el_admin_preguntar_antiguo_pasa_a_no(self):
        v = asistentes.validar({"activo": True, "archivos": "libre", "comandos": True, "admin": "preguntar"})
        self.assertEqual(v["admin"], "no")
        self.assertEqual(asistentes.resumen(v), "Este equipo")

    def test_cada_nivel_tiene_nombre_y_descripcion(self):
        self.assertEqual(list(asistentes.PREAJUSTES), ["consultar", "archivos", "caja", "equipo", "total"])
        for clave, valores in asistentes.PREAJUSTES.items():
            self.assertEqual(asistentes.validar(dict(valores, activo=True)) | {"activo": True}, dict(valores, activo=True))
            self.assertIn(clave, asistentes.NOMBRE_PREAJUSTE)
            self.assertTrue(asistentes.DESCRIPCION_PREAJUSTE[clave])
            self.assertEqual(asistentes.resumen(dict(valores, activo=True)), asistentes.NOMBRE_PREAJUSTE[clave])

    def test_consultar_solo_lee(self):
        casa = str(self.p.n.casa)
        os.makedirs(os.path.join(casa, "docs"))
        fijar(claude=dict(asistentes.PREAJUSTES["consultar"], activo=True))
        ok = self.p.manejar_ia({"op": "pedir", "titulo": "leer", "carpetas": {os.path.join(casa, "docs"): "r"}}, "nube", "claude")
        self.assertEqual(ok["estado"], "pendiente")
        for perms in ("w", "rw", "rwd"):
            with self.assertRaises(Denegado):
                self.p.manejar_ia({"op": "pedir", "titulo": "escribir", "carpetas": {os.path.join(casa, "docs"): perms}}, "nube", "claude")

    def _nivel_caja(self):
        casa = str(self.p.n.casa)
        os.makedirs(os.path.join(casa, "proyecto"))
        fijar(claude=dict(asistentes.PREAJUSTES["caja"], activo=True))
        self.llamadas = []
        self.p.correr_caja = lambda o, e, c, carpetas: self.llamadas.append((o, carpetas)) or {"codigo": 0, "salida": "ok"}
        return os.path.join(casa, "proyecto")

    def test_comandos_en_caja_exigen_una_tarea(self):
        self._nivel_caja()
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", orden="ls")
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", orden="ls", tarea="inventada")
        self.assertEqual(self.llamadas, [])
        self.assertEqual(self.hechas, [])

    def test_comandos_en_caja_corren_con_las_carpetas_de_la_tarea(self):
        proyecto = self._nivel_caja()
        r = self.ia("claude", op="pedir", titulo="trabajar", carpetas={proyecto: "rw"})
        self.p.manejar_control({"op": "aprobar", "pid": r["pid"]})
        tarea = self.ia("claude", op="estado", pid=r["pid"])["tarea"]
        self.assertEqual(self.ia("claude", op="ejecutar", orden="git status", tarea=tarea)["codigo"], 0)
        self.assertEqual(self.llamadas, [("git status", [(os.path.realpath(proyecto), True)])])
        self.assertEqual(self.hechas, [])                       # nunca corrió fuera de la caja

    def test_comandos_en_caja_solo_lectura_monta_ro(self):
        proyecto = self._nivel_caja()
        r = self.ia("claude", op="pedir", titulo="mirar", carpetas={proyecto: "r"})
        self.p.manejar_control({"op": "aprobar", "pid": r["pid"]})
        tarea = self.ia("claude", op="estado", pid=r["pid"])["tarea"]
        self.ia("claude", op="ejecutar", orden="ls", tarea=tarea)
        self.assertEqual(self.llamadas[0][1], [(os.path.realpath(proyecto), False)])

    def test_la_tarea_de_otro_asistente_no_sirve_en_la_caja(self):
        proyecto = self._nivel_caja()
        fijar(claude=dict(asistentes.PREAJUSTES["caja"], activo=True), codex=dict(asistentes.PREAJUSTES["caja"], activo=True))
        r = self.ia("claude", op="pedir", titulo="trabajar", carpetas={proyecto: "rw"})
        self.p.manejar_control({"op": "aprobar", "pid": r["pid"]})
        tarea = self.ia("claude", op="estado", pid=r["pid"])["tarea"]
        with self.assertRaises(Denegado):
            self.ia("codex", op="ejecutar", orden="ls", tarea=tarea)
        self.assertEqual(self.llamadas, [])

    def test_comandos_en_caja_no_dan_administrador(self):
        proyecto = self._nivel_caja()
        r = self.ia("claude", op="pedir", titulo="trabajar", carpetas={proyecto: "rw"})
        self.p.manejar_control({"op": "aprobar", "pid": r["pid"]})
        tarea = self.ia("claude", op="estado", pid=r["pid"])["tarea"]
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", orden="ls", admin=True, tarea=tarea)

    def test_bajar_a_caja_frena_una_orden_ya_aprobada_fuera_de_ella(self):
        fijar(claude={"activo": True, "comandos": True, "admin": "no"})
        r = self.ia("claude", op="ejecutar", orden="rm -rf ~")
        self.assertEqual(r["estado"], "pendiente")
        self.p.manejar_control({"op": "aprobar", "pid": r["pid"]})
        fijar(claude=dict(asistentes.PREAJUSTES["caja"], activo=True))
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", pid=r["pid"])
        self.assertEqual(self.hechas, [])

    def test_este_equipo_no_tiene_administrador(self):
        fijar(claude=dict(asistentes.PREAJUSTES["equipo"], activo=True))
        with self.assertRaises(Denegado):
            self.ia("claude", op="ejecutar", orden="apt update", admin=True)
        self.assertEqual(self.ia("claude", op="ejecutar", orden="ls")["codigo"], 0)
        self.assertEqual(self.hechas, [("usuario", "ls")])


if __name__ == "__main__":
    unittest.main()
