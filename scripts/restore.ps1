# Restaura la base desde un backup local (D-71). Por defecto solo SIMULA: no cambia nada.
#
#   powershell -File scripts\restore.ps1                        # lista los backups
#   powershell -File scripts\restore.ps1 -Backup NOMBRE.dump    # simulacro: comprueba que restaura
#   powershell -File scripts\restore.ps1 -Backup NOMBRE.dump -Apply
#                                                               # REEMPLAZA la base por el backup
#
# Con -Apply: detiene la API y el worker, hace un backup de seguridad de la base actual, la
# recrea desde el backup elegido, aplica las migraciones y vuelve a arrancar todo. Pide escribir
# RESTAURAR (o pasar -Confirmar RESTAURAR) porque se pierde lo escrito después del backup.
param(
    [string]$Backup,
    [switch]$Apply,
    [string]$Confirmar
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$run = @('compose', 'run', '--rm', '--no-deps', '-T', 'api', 'python', '-m', 'app.ops.backups')

function Fail($message) { Write-Host $message -ForegroundColor Red; exit 1 }

docker compose up -d db | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'No se pudo iniciar la base de datos.' }

if (-not $Backup) {
    & docker @run list
    exit $LASTEXITCODE
}

if (-not $Apply) {
    & docker @run restore $Backup
    exit $LASTEXITCODE
}

# Antes de parar nada: que el backup exista, esté íntegro y restaure de prueba.
& docker @run verify $Backup
if ($LASTEXITCODE -ne 0) { Fail 'El backup no pasó la verificación. No se cambió nada.' }

if ($Confirmar -ne 'RESTAURAR') {
    Write-Host "Se REEMPLAZARÁ la base actual por $Backup. Lo escrito después de ese backup se perderá" -ForegroundColor Yellow
    Write-Host '(antes se guarda un backup de seguridad de la base actual).'
    $Confirmar = Read-Host 'Escriba RESTAURAR para continuar'
    if ($Confirmar -ne 'RESTAURAR') { Fail 'Cancelado. No se cambió nada.' }
}

docker compose stop api worker frontend
& docker @run restore $Backup --apply
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host 'La restauración falló. La aplicación sigue detenida; la base anterior está en el backup de seguridad.' -ForegroundColor Red
    exit $code
}

# `migrate` aplica las migraciones pendientes (si el backup es de una versión anterior) y levanta todo.
docker compose up -d
if ($LASTEXITCODE -ne 0) { Fail 'No se pudo volver a arrancar la aplicación.' }
Write-Host 'Listo. La aplicación volvió a arrancar con la base restaurada.' -ForegroundColor Green
