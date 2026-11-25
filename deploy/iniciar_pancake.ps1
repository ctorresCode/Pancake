# Arranca Pancake para que se pueda entrar desde internet.
# Uso: clic derecho > "Ejecutar con PowerShell", o desde la terminal: .\deploy\iniciar_pancake.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# Leer PANCAKE_DOMAIN del .env
$domain = (Get-Content .env | Where-Object { $_ -match '^PANCAKE_DOMAIN=' }) -replace '^PANCAKE_DOMAIN=', ''
if (-not $domain) { Write-Host "Falta PANCAKE_DOMAIN en el archivo .env" -ForegroundColor Red; exit 1 }

$env:DEBUG = "False"
$env:PANCAKE_DOMAIN = $domain.Trim()
$python = Join-Path $root "venv\Scripts\python.exe"

Write-Host "Preparando la base de datos y los archivos..." -ForegroundColor Cyan
& $python manage.py migrate --noinput
& $python manage.py collectstatic --noinput | Out-Null

Write-Host "Iniciando Django (Waitress) en 127.0.0.1:8000..." -ForegroundColor Cyan
$django = Start-Process -FilePath $python -ArgumentList "-m", "waitress", "--listen=127.0.0.1:8000", "--threads=8", "pancake.wsgi:application" -PassThru -WindowStyle Hidden

try {
    Write-Host "Iniciando Caddy (HTTPS) para https://$($env:PANCAKE_DOMAIN) ..." -ForegroundColor Green
    Write-Host "Deja esta ventana abierta. Para apagar Pancake, ciérrala o pulsa Ctrl+C." -ForegroundColor Yellow
    & (Join-Path $root "tools\caddy\caddy.exe") run --config (Join-Path $root "deploy\Caddyfile") --adapter caddyfile
}
finally {
    if ($django -and -not $django.HasExited) { Stop-Process -Id $django.Id -Force }
    Write-Host "Pancake apagado."
}
