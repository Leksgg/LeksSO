#!/usr/bin/env bash
# Endurece un equipo LeksSO: cortafuegos, actualizaciones de seguridad y ajustes del núcleo.
# Se puede ejecutar varias veces. Debe correr como root.
#
# Uso: sudo ./scripts/endurecer.sh [--ssh]
#   --ssh   deja abierto el puerto 22 (solo para máquinas de prueba que se manejan por SSH)
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta como root: sudo $0 [--ssh]" >&2
  exit 1
fi
SSH=0
[ "${1:-}" = "--ssh" ] && SSH=1

export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends nftables unattended-upgrades

# 1. Cortafuegos: todo lo entrante se bloquea salvo lo que responde a lo que tú abres.
REGLA_SSH=""
# --ssh (máquinas de prueba): solo desde redes privadas, no desde cualquier origen alcanzable.
[ "$SSH" -eq 1 ] && REGLA_SSH='ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } tcp dport 22 accept comment "leksso-acceso-remoto"'
# Si el acceso remoto está encendido (leksso-acceso-remoto on), se conserva su regla según el modo (local o publico).
if [ "$SSH" -eq 0 ] && [ -f /etc/leksso/acceso-remoto ]; then
  if [ "$(cat /etc/leksso/acceso-remoto)" = publico ]; then
    REGLA_SSH='tcp dport 22 ct state new limit rate 20/minute burst 10 packets accept comment "leksso-acceso-remoto"'
  else
    REGLA_SSH='ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } tcp dport 22 accept comment "leksso-acceso-remoto"'
  fi
fi
# Solicitudes de conexión (leksso-solicitud): con el acceso remoto en modo local, su puerto se conserva igual que el de SSH.
# Sin esto, cada actualización cerraba ese puerto hasta apagar y encender el acceso remoto.
REGLA_SOLICITUD=""
if [ -f /etc/systemd/system/leksso-solicitud.socket ] && [ -f /etc/leksso/acceso-remoto ] && [ "$(cat /etc/leksso/acceso-remoto)" != publico ]; then
  REGLA_SOLICITUD='ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } tcp dport 22222 ct state new limit rate 12/minute burst 6 packets accept comment "leksso-acceso-remoto solicitud"'
fi
cat > /etc/nftables.conf <<NFT
#!/usr/sbin/nft -f
# LeksSO: entrante bloqueado por defecto. Saliente libre.
# Solo se reemplaza NUESTRA tabla: las reglas de otros programas (Docker, VPN…) y la tabla de bloqueos del usuario
# (leksso_usuario) se respetan. «table» + «delete table» es la forma de reemplazar sin fallar si aún no existía.
table inet leksso
delete table inet leksso

table inet leksso {
  chain entrada {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    ct state invalid drop
    iif lo accept
    ip protocol icmp icmp type { echo-request, destination-unreachable, time-exceeded } limit rate 10/second accept
    ip6 nexthdr icmpv6 accept
    udp sport 67 udp dport 68 accept
    udp sport 547 udp dport 546 accept
    $REGLA_SSH
    $REGLA_SOLICITUD
  }
  # No somos un router. Docker añade sus propias reglas de reenvío.
  chain reenvio { type filter hook forward priority 0; policy accept; }
  chain salida { type filter hook output priority 0; policy accept; }
}
NFT
nft -c -f /etc/nftables.conf || echo "AVISO: no se pudo comprobar la sintaxis del cortafuegos aquí."
systemctl enable nftables >/dev/null
# En el instalador (sin systemd en marcha) no se puede arrancar el servicio: arrancará en el primer inicio.
# NO se reinicia nftables: en Debian su «stop» ejecuta «flush ruleset» y borraría las reglas de otros programas
# (Docker, VPN…). El archivo se aplica en UNA transacción: o se aplica entera o se queda la política anterior.
if [ -d /run/systemd/system ]; then
  if systemctl is-active --quiet nftables; then
    nft -f /etc/nftables.conf || { echo "ERROR: no se pudo aplicar el cortafuegos; sigue la política anterior." >&2; exit 1; }
  else
    systemctl start nftables
  fi
fi

# 2. Actualizaciones de seguridad automáticas (solo el repositorio de seguridad de Debian; sin reinicio automático).
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true

# 3. Núcleo: un programa no puede espiar a otros del mismo usuario ni leer direcciones del núcleo.
#    No se bloquean los espacios de usuario: los necesitan la caja y Steam.
cat > /etc/sysctl.d/90-leksso.conf <<'SYS'
kernel.yama.ptrace_scope = 1
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.unprivileged_bpf_disabled = 1
net.core.bpf_jit_harden = 2
fs.protected_fifos = 2
fs.protected_regular = 2
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.tcp_syncookies = 1
SYS
sysctl --system >/dev/null 2>&1 || true

echo "Endurecimiento aplicado: cortafuegos, actualizaciones de seguridad y ajustes del núcleo."
