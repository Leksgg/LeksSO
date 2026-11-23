# Con permisos de administrador. Cambia el TIPO de la partición LEKSSO del pendrive real (disco USB 5) de «Sistema EFI» a «datos
# básicos» (no toca su contenido). Uso: tipo-leksso.ps1 datos | efi   («efi» lo deja como estaba, por si el equipo no arranca así).
param([ValidateSet('datos','efi')][string]$Modo = 'datos')
$ErrorActionPreference = 'Stop'
$log = 'D:\temp\tipo-leksso.log'
function L($m) { $l = "{0:HH:mm:ss} {1}" -f (Get-Date), $m; Add-Content -Path $log -Value $l -Encoding utf8; Write-Host $l }
trap { L ("ERROR: " + $_.Exception.Message); Start-Sleep 4; break }
$d = Get-Disk -Number 5
if ($d.BusType -ne 'USB' -or $d.IsSystem -or $d.IsBoot -or $d.FriendlyName -notmatch 'Kingston') { throw "El disco 5 no es el pendrive esperado ($($d.FriendlyName))." }
$p = Get-Partition -DiskNumber 5 | Where-Object { (Get-Volume -Partition $_ -ErrorAction SilentlyContinue).FileSystemLabel -eq 'LEKSSO' }
if (-not $p) { throw 'No encuentro la partición LEKSSO.' }
L ("Antes: partición {0}, tipo {1}, {2:N2} GB" -f $p.PartitionNumber, $p.GptType, ($p.Size/1GB))
$tipo = if ($Modo -eq 'datos') { '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}' } else { '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' }
Set-Partition -DiskNumber 5 -PartitionNumber $p.PartitionNumber -GptType $tipo
$q = Get-Partition -DiskNumber 5 -PartitionNumber $p.PartitionNumber
L ("Después: tipo {0}" -f $q.GptType)
Get-Partition -DiskNumber 5 | ForEach-Object { L ("  part {0}: {1:N2} GB tipo {2}" -f $_.PartitionNumber, ($_.Size/1GB), $_.GptType) }
