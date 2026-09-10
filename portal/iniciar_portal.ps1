$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$portal = Join-Path $scriptDir "script.py"
$python = Get-Command python -ErrorAction SilentlyContinue

if (-not $python) {
    throw "No se encontro Python en PATH."
}

& $python.Source $portal
