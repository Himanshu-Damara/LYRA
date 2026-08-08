$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectRoot '.venv'

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Python is not installed. Install Python 3.11 or newer from https://www.python.org/downloads/ and rerun setup.ps1.'
}

if (-not (Test-Path (Join-Path $venvPath 'Scripts\python.exe'))) {
    & py -3 -m venv $venvPath
}

$python = Join-Path $venvPath 'Scripts\python.exe'
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    throw 'Core dependency installation failed.'
}

Write-Host "Environment ready. Start LYRA with:"
Write-Host "  $python tools\web_server.py"
