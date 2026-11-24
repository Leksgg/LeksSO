# Crea la memoria USB de instalación de LeksSO desde Windows (PowerShell como administrador).
#
#   .\crear-usb.ps1 -Iso C:\ruta\leksso-instalador.iso            con una imagen que ya tienes
#   .\crear-usb.ps1 -Url https://.../leksso-instalador.iso        la descarga y comprueba su firma antes de grabar
#
# Seguridad: solo ofrece discos USB, te enseña modelo y tamaño, y no toca nada hasta que escribes BORRAR.
# La imagen se comprueba con su suma SHA-256 y, si hay archivos .sha256 y .sha256.sig a su lado, con la
# firma de LeksSO (clave incluida aquí, la misma que firma las versiones).
param(
  [string]$Iso,
  [string]$Url,
  [switch]$SinFirma   # solo para imágenes de pruebas propias
)
$ErrorActionPreference = 'Stop'
$ClavePublica = 'leksso-release namespaces="file" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG8wCtKi9u4zuhJM7Qn13ZhyGhCLspTx2t6h72ERbeq1'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Abre PowerShell como administrador (clic derecho > Ejecutar como administrador).'
}

# 1. La imagen: local o descargada
if ($Url) {
  if ($Url -notmatch '^https://') { throw 'La dirección debe ser https.' }
  $carpeta = Join-Path $env:TEMP ('leksso-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $carpeta | Out-Null
  $Iso = Join-Path $carpeta 'leksso-instalador.iso'
  Write-Host "Descargando $Url ..."
  Invoke-WebRequest -Uri $Url -OutFile $Iso -UseBasicParsing
  foreach ($ext in '.sha256', '.sha256.sig') {
    try { Invoke-WebRequest -Uri ($Url + $ext) -OutFile ($Iso + $ext) -UseBasicParsing } catch { }
  }
}
if (-not $Iso -or -not (Test-Path -LiteralPath $Iso)) { throw 'Indica -Iso con la ruta de la imagen, o -Url.' }
$Iso = (Resolve-Path -LiteralPath $Iso).Path

# 2. Comprobaciones de la imagen
# La imagen se abre UNA vez y se queda abierta sin permitir escrituras de nadie más hasta el final: lo que se
# comprueba (suma y firma) son exactamente los bytes que luego se graban. Los archivos de suma y firma se leen una
# vez a memoria y se verifican desde copias propias en una carpeta nueva.
$flujo = [IO.File]::Open($Iso, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
$sha = [Security.Cryptography.SHA256]::Create()
$hash = ([BitConverter]::ToString($sha.ComputeHash($flujo)) -replace '-', '').ToLower()
$flujo.Position = 0
$archivoSuma = "$Iso.sha256"
if (Test-Path $archivoSuma) {
  $textoSuma = [IO.File]::ReadAllText($archivoSuma)
  $esperado = (($textoSuma).Trim() -split '\s+')[0].ToLower()
  if ($esperado -ne $hash) { throw "La suma de la imagen no coincide (esperada $esperado, calculada $hash). No grabo nada." }
  Write-Host 'Suma SHA-256: correcta.'
  if (Test-Path "$archivoSuma.sig") {
    $ssh = (Get-Command ssh-keygen.exe -ErrorAction SilentlyContinue).Source
    if (-not $ssh) { throw 'Falta ssh-keygen (Windows: Configuración > Características opcionales > Cliente OpenSSH) para comprobar la firma.' }
    $priv = Join-Path $env:TEMP ('leksso-v-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $priv | Out-Null
    $perm = Join-Path $priv 'allowed_signers'; Set-Content -Path $perm -Value $ClavePublica -Encoding ascii
    $firma = Join-Path $priv 'suma.sig'; [IO.File]::WriteAllBytes($firma, [IO.File]::ReadAllBytes("$archivoSuma.sig"))
    $textoSuma | & $ssh -Y verify -f $perm -I leksso-release -n file -s $firma | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'La FIRMA de la imagen no es válida. No grabo nada.' }
    Write-Host 'Firma de LeksSO: válida.'
  } elseif (-not $SinFirma) { throw 'La imagen no trae firma (.sha256.sig). Si es una imagen de pruebas tuya, usa -SinFirma.' }
} elseif (-not $SinFirma) { throw 'No hay archivo .sha256 junto a la imagen. Si es una imagen de pruebas tuya, usa -SinFirma.' }
else { Write-Host "AVISO: imagen sin comprobar (SHA-256 $hash)." -ForegroundColor Yellow }

# 3. El USB: solo discos USB, nunca el del sistema
$candidatos = Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsBoot -and -not $_.IsSystem -and $_.Size -ge 4GB -and $_.Size -le 512GB }
if (-not $candidatos) { throw 'No encuentro ninguna memoria USB (4 GB o más). Conéctala y repite.' }
Write-Host "`nMemorias USB encontradas:"
$candidatos | ForEach-Object { '  Disco {0}: {1}  {2:N1} GB' -f $_.Number, $_.FriendlyName, ($_.Size / 1GB) }
$num = Read-Host "`nNúmero del disco que se va a BORRAR por completo"
$disco = $candidatos | Where-Object { "$($_.Number)" -eq $num }
if (-not $disco) { throw 'Ese número no es una de las memorias USB de la lista.' }
if ($flujo.Length -gt $disco.Size) { throw 'La imagen no cabe en esa memoria.' }
$conf = Read-Host ('Se borrará TODO en "{0}" ({1:N1} GB). Escribe BORRAR para continuar' -f $disco.FriendlyName, ($disco.Size / 1GB))
if ($conf -ne 'BORRAR') { throw 'Cancelado. No se ha tocado nada.' }

# 4. Grabar la imagen tal cual (las imágenes de Debian arrancan directamente desde el USB)
Set-Disk -Number $disco.Number -IsOffline $false -ErrorAction SilentlyContinue
Set-Disk -Number $disco.Number -IsReadOnly $false -ErrorAction SilentlyContinue
Clear-Disk -Number $disco.Number -RemoveData -RemoveOEM -Confirm:$false -ErrorAction SilentlyContinue
Set-Disk -Number $disco.Number -IsOffline $true

Add-Type -TypeDefinition @'
using System; using System.IO; using System.Runtime.InteropServices; using Microsoft.Win32.SafeHandles;
public static class RawDisk {
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  static extern SafeFileHandle CreateFile(string n, uint acc, uint share, IntPtr sa, uint disp, uint flags, IntPtr t);
  public static void Write(string path, Stream i, Action<long,long> progreso) {
    using (var h = CreateFile(path, 0x40000000, 3, IntPtr.Zero, 3, 0x80000000 /*WRITE_THROUGH*/, IntPtr.Zero)) {
      if (h.IsInvalid) throw new IOException("No se pudo abrir el disco: " + Marshal.GetLastWin32Error());
      using (var o = new FileStream(h, FileAccess.Write, 4 * 1024 * 1024, false))
      {
        var b = new byte[4 * 1024 * 1024]; long hecho = 0, total = i.Length; int n;
        while ((n = i.Read(b, 0, b.Length)) > 0) {
          int w = (n + 511) / 512 * 512; if (w > n) Array.Clear(b, n, w - n);
          o.Write(b, 0, w); hecho += n; progreso(hecho, total);
        }
        o.Flush();
      }
    }
  }
}
'@
Write-Host "`nGrabando... (unos minutos, no desconectes la memoria)"
[RawDisk]::Write("\\.\PhysicalDrive$($disco.Number)", $flujo, [Action[long,long]]{ param($h,$t) Write-Progress -Activity 'Grabando LeksSO en la USB' -PercentComplete ([int](100 * $h / $t)) })
$flujo.Dispose()
Set-Disk -Number $disco.Number -IsOffline $false -ErrorAction SilentlyContinue
Write-Progress -Activity 'Grabando LeksSO en la USB' -Completed
Write-Host @'

Listo. Para instalar:
  1. Deja la USB conectada y reinicia el portátil.
  2. Entra en el menú de arranque (suele ser F12, F9, Esc o F2 al encender) y elige la USB.
  3. En el menú elige una de las «Instalar LeksSO»: disco cifrado con clave, cifrado con TPM o sin cifrar. Te preguntará qué disco borrar, tu usuario y su contraseña (y la clave del cifrado, si lo elegiste).
Windows desaparece de ese disco: copia antes lo que quieras conservar.
'@ -ForegroundColor Green
