# Corre las pruebas E2E del navegador en un entorno AISLADO con la demo cargada (D-65).
#
# - Usa su propio proyecto de Compose (nicheradar_e2e), su propia base y otros puertos.
# - No toca la base de trabajo ni usa claves reales: las variables de claves se vacían.
# - Al terminar elimina el entorno y su base, salvo que se pase -Keep.
#
# Uso:  powershell -File scripts\e2e.ps1
param([switch]$Keep)

$root = Split-Path -Parent $PSScriptRoot
$project = 'nicheradar_e2e'

$env:DEMO_MODE = 'true'
# Los backups del entorno de pruebas no deben mezclarse con los reales de ./backups.
$env:BACKUPS_DIR = Join-Path ([IO.Path]::GetTempPath()) 'nicheradar_e2e_backups'
$env:DB_HOST_PORT = '15433'
$env:API_HOST_PORT = '8001'
$env:FRONTEND_HOST_PORT = '5174'
foreach ($name in 'YOUTUBE_API_KEY', 'OPENAI_API_KEY', 'VIDIQ_API_KEY', 'HASDATA_API_KEY', 'CLAUDE_API_KEY', 'ANTHROPIC_API_KEY') {
    Set-Item "Env:$name" ''
}

docker compose -p $project --project-directory $root up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

docker compose -p $project --project-directory $root --profile e2e run --rm e2e
$code = $LASTEXITCODE

if (-not $Keep) {
    docker compose -p $project --project-directory $root --profile e2e down -v
}
exit $code
