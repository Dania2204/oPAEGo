# RNF-14: copia de respaldo de la base de datos de PAEGo (PowerShell).
# Uso:  powershell -File scripts\respaldo_bd.ps1
# Programar a diario con el Programador de tareas de Windows.
# Restaurar: docker cp archivo.dump pae-go-postgres:/tmp/r.dump
#            docker exec pae-go-postgres pg_restore -U pae_user -d pae_go --clean /tmp/r.dump
$ErrorActionPreference = "Stop"
$destino = Join-Path $PSScriptRoot "..\respaldos"
New-Item -ItemType Directory -Force $destino | Out-Null
$nombre = "pae_go_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".dump"
docker exec pae-go-postgres pg_dump -U pae_user -d pae_go -Fc -f "/tmp/$nombre"
docker cp "pae-go-postgres:/tmp/$nombre" (Join-Path $destino $nombre)
docker exec pae-go-postgres rm "/tmp/$nombre"
Write-Output "Respaldo creado: $(Join-Path $destino $nombre)"
# Conservar los últimos 30 respaldos.
Get-ChildItem $destino -Filter "pae_go_*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item
