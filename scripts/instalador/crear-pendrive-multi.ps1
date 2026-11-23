# Rehace una memoria USB de instalación MULTI-SISTEMA: LeksSO (con su menú de dos niveles) y Windows 10 en el mismo pendrive.
# PowerShell COMO ADMINISTRADOR. Borra TODO el pendrive: solo ofrece discos USB, enseña modelo y tamaño y no toca nada hasta
# que escribes BORRAR.
#
#   .\crear-pendrive-multi.ps1 [-Disco N] [-IsoLeksso RUTA.iso] [-Windows10 CARPETA_EXTRAIDA]
#
# Disposición (GPT): 1) LEKSSO  (FAT32, partición de sistema EFI): GRUB, el menú y el instalador de LeksSO.
#                    2) WIN10   (FAT32): el instalador de Windows 10 x64 (su install.esd pesa menos de 4 GB: no hace falta partirlo).
#                    3) LIBRE   (FAT32): el resto, para Windows 11 más adelante o para datos.
# El menú (en la partición 1) muestra «Instalar Windows 10» solo si encuentra la partición con la etiqueta WIN10.
# Cada Windows necesita su propia partición (su arranque busca \sources, \boot y \efi en la raíz), por eso no comparten.
param(
  [int]$Disco = -1,
  [string]$IsoLeksso = 'D:\Instaladores\LeksSO\leksso-instalador-0.1.33-beta.iso',
  [string]$Windows10 = 'D:\Instaladores\Windows10\x64',
  [string]$Respaldo = 'D:\Respaldos\ESD-USB-2026-11-20',
  [int]$MBLeksso = 3072,
  [int]$MBWin10 = 6144
)
$ErrorActionPreference = 'Stop'
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Abre PowerShell como administrador.' }
foreach ($r in $IsoLeksso, $Windows10) { if (-not (Test-Path -LiteralPath $r)) { throw "No encuentro: $r" } }
if (-not (Test-Path -LiteralPath "$Windows10\sources\install.esd") -and -not (Test-Path -LiteralPath "$Windows10\sources\install.wim")) { throw 'La carpeta de Windows no tiene sources\install.esd/wim.' }
$tamWin = (Get-ChildItem -LiteralPath $Windows10 -Recurse -File | Measure-Object Length -Sum).Sum
if ($tamWin -gt ($MBWin10 - 200) * 1MB) { throw ("Windows ocupa {0:N0} MB y la partición es de {1} MB: no cabe." -f ($tamWin / 1MB), $MBWin10) }

# 1. El disco: solo USB, nunca el del sistema
$usb = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsSystem -and -not $_.IsBoot })
if ($Disco -ge 0) { $usb = @($usb | Where-Object Number -eq $Disco) }
if ($usb.Count -eq 0) { throw 'No hay ningún disco USB que ofrecer.' }
if ($usb.Count -gt 1) { $usb | ForEach-Object { "  disco {0}: {1}  {2:N1} GB" -f $_.Number, $_.FriendlyName, ($_.Size / 1GB) }; throw 'Hay varios discos USB: indica -Disco N.' }
$d = $usb[0]
if ($d.Size -lt 8GB -or $d.Size -gt 64GB) { throw ("El disco {0} mide {1:N1} GB: no parece un pendrive de instalación." -f $d.Number, ($d.Size / 1GB)) }
if ($MBLeksso + $MBWin10 + 512 -gt $d.Size / 1MB) { throw 'Las particiones no caben en el pendrive.' }
Write-Host ''
Write-Host ("Se va a BORRAR por completo: disco {0}  {1}  {2:N1} GB" -f $d.Number, $d.FriendlyName, ($d.Size / 1GB)) -ForegroundColor Yellow
# 2. Respaldo: lo único propio del pendrive actual (TeamSpeak y Windows) debe estar copiado
foreach ($n in 'teamspeak3-server_win64', '_windows-instalador') {
  $r = Join-Path $Respaldo $n
  if (-not (Test-Path -LiteralPath $r)) { throw "Falta el respaldo de $n en $Respaldo. No borro nada." }
}
Write-Host ("Respaldo encontrado en {0}." -f $Respaldo)
$resp = Read-Host 'Escribe BORRAR para continuar (cualquier otra cosa cancela)'
if ($resp.Trim().ToUpper() -ne 'BORRAR') { Write-Host 'Cancelado. No se ha tocado nada.'; return }

# 3. Particiones
Write-Host 'Preparando el disco...'
Clear-Disk -Number $d.Number -RemoveData -RemoveOEM -Confirm:$false
# Tras Clear-Disk el disco suele seguir «inicializado» (con tabla vacía): se pasa a GPT sin volver a inicializarlo.
$estilo = (Get-Disk -Number $d.Number).PartitionStyle
if ($estilo -eq 'RAW') { Initialize-Disk -Number $d.Number -PartitionStyle GPT }
elseif ($estilo -ne 'GPT') { Set-Disk -Number $d.Number -PartitionStyle GPT }
$tipoEfi = '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'; $tipoDatos = '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}'
function Nueva($tam, $tipo, $etiqueta) {
  if ($tam) { $p = New-Partition -DiskNumber $d.Number -Size ($tam * 1MB) -GptType $tipo } else { $p = New-Partition -DiskNumber $d.Number -UseMaximumSize -GptType $tipo }
  Start-Sleep -Seconds 2
  $p | Add-PartitionAccessPath -AssignDriveLetter -ErrorAction SilentlyContinue
  $p = Get-Partition -DiskNumber $d.Number -PartitionNumber $p.PartitionNumber
  Format-Volume -Partition $p -FileSystem FAT32 -NewFileSystemLabel $etiqueta -Confirm:$false | Out-Null
  (Get-Partition -DiskNumber $d.Number -PartitionNumber $p.PartitionNumber).DriveLetter
}
# La partición de arranque del pendrive va como «datos básicos», NO como «Sistema EFI»: con una partición EFI en el pendrive, el
# instalador de Windows la confunde con la del equipo y falla («No se puede crear una partición nueva ni encontrar una que ya
# exista» o «no puede preparar el equipo para la siguiente fase»). Comprobado en la VM con la ISO original (2026-11-23).
$l1 = Nueva $MBLeksso $tipoDatos 'LEKSSO'
$l2 = Nueva $MBWin10 $tipoDatos 'WIN10'
$l3 = Nueva 0 $tipoDatos 'LIBRE'
Write-Host ("Particiones: LEKSSO={0}:  WIN10={1}:  LIBRE={2}:" -f $l1, $l2, $l3)
if (-not $l1 -or -not $l2) { throw 'No se asignaron letras a las particiones.' }

# 4. LeksSO: se extrae la ISO con sus nombres reales (Windows corta los nombres largos al copiar una ISO)
Write-Host 'Copiando LeksSO (extraída con Linux, para conservar los nombres)...'
function ARutaWsl($ruta) { '/mnt/' + $ruta.Substring(0, 1).ToLower() + ($ruta.Substring(2) -replace '\\', '/') }
$isoW = ARutaWsl (Resolve-Path -LiteralPath $IsoLeksso).Path
$cmd = "mkdir -p /mnt/leks && umount /mnt/leks 2>/dev/null; mount -t drvfs ${l1}: /mnt/leks && xorriso -osirrox on -indev '$isoW' -extract / /mnt/leks 2>&1 | tail -2 && sync && echo '--- comprobando (sin diferencias = bien):' && xorriso -indev '$isoW' -compare -disk_dir / /mnt/leks 2>&1 | tail -3; umount /mnt/leks"
wsl -u root -e bash -c $cmd

# 5. Windows 10
Write-Host 'Copiando Windows 10 (unos minutos)...'
robocopy $Windows10 "${l2}:\" /E /R:2 /W:2 /NFL /NDL /NP /NJH | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy falló con el código $LASTEXITCODE" }
$ok = $true
$origen = (Get-ChildItem -LiteralPath $Windows10 -Recurse -File).Count
$destino = (Get-ChildItem -LiteralPath "${l2}:\" -Recurse -File -Force | Where-Object { $_.FullName -notmatch 'System Volume Information' }).Count
Write-Host ("Windows 10: {0} archivos en el origen, {1} en el pendrive." -f $origen, $destino)
if ($origen -ne $destino) { $ok = $false }
$esd = 'sources\install.esd'
if (Test-Path -LiteralPath "$Windows10\$esd") {
  $h1 = (Get-FileHash -LiteralPath "$Windows10\$esd" -Algorithm SHA256).Hash
  $h2 = (Get-FileHash -LiteralPath "${l2}:\$esd" -Algorithm SHA256).Hash
  Write-Host ("install.esd: {0}" -f $(if ($h1 -eq $h2) { 'igual al origen (SHA-256)' } else { 'DISTINTO' }))
  if ($h1 -ne $h2) { $ok = $false }
}

# 6. Nota de qué lleva (para poder rehacerlo)
$hIso = (Get-FileHash -LiteralPath $IsoLeksso -Algorithm SHA256).Hash.ToLower()
$nota = "Pendrive multi-sistema, creado $(Get-Date -Format 'yyyy-MM-dd HH:mm')`r`nLeksSO: $(Split-Path $IsoLeksso -Leaf)  sha256 $hIso`r`nWindows 10 x64: $Windows10`r`nPartición 3 (LIBRE): sin usar.`r`n"
[IO.File]::WriteAllText("${l1}:\sistemas.txt", $nota)

Write-Host ''
if ($ok) { Write-Host 'Listo. Pendrive multi-sistema creado y comprobado.' -ForegroundColor Green } else { Write-Host 'Terminado, pero hay diferencias: revisa lo de arriba antes de usarlo.' -ForegroundColor Red }
Write-Host 'Puedes cerrar esta ventana.'
Start-Sleep -Seconds 5
