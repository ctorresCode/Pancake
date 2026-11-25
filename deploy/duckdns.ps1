# Le avisa a DuckDNS cuál es la IP actual de la casa (cambia cada cierto tiempo).
$root = Split-Path $PSScriptRoot -Parent
$envFile = Get-Content (Join-Path $root ".env")
$domain = (($envFile | Where-Object { $_ -match '^PANCAKE_DOMAIN=' }) -replace '^PANCAKE_DOMAIN=', '').Trim()
$token = (($envFile | Where-Object { $_ -match '^DUCKDNS_TOKEN=' }) -replace '^DUCKDNS_TOKEN=', '').Trim()
$sub = $domain -replace '\.duckdns\.org$', ''
if (-not $sub -or -not $token) { Write-Output "Faltan PANCAKE_DOMAIN o DUCKDNS_TOKEN en .env"; exit 1 }

$res = Invoke-RestMethod -Uri "https://www.duckdns.org/update?domains=$sub&token=$token&ip=" -UseBasicParsing
$line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $res
Add-Content -Path (Join-Path $PSScriptRoot "duckdns.log") -Value $line
Write-Output $line
