param(
    [switch]$Reload,
    [switch]$Lan,
    [ValidateRange(1, 65535)][int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv before starting ThreadPilot.' }
if (-not (Test-Path -LiteralPath '.env')) { throw 'Create backend/.env from .env.example and initialize local MySQL first. See README section 7.' }
$listenAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$serverArgs = @('run', '--locked', 'uvicorn', 'app.main:app', '--host', $listenAddress, '--port', "$Port", '--workers', '1')
if ($Reload) { $serverArgs += '--reload' }
& uv @serverArgs
exit $LASTEXITCODE
