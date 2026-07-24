#Requires -Version 5.1
<#
.SYNOPSIS
    CareerForge AI one-time setup (Windows PowerShell).

.DESCRIPTION
    Creates the Python virtual environment, installs the backend package (with
    dev extras), copies .env from .env.example, and installs the frontend
    dependencies. Safe to re-run.

    Nothing here requires Docker, a GPU, or any external service — the demo runs
    with just Python 3.12+ and Node 18+.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>

$ErrorActionPreference = 'Stop'

# --- Resolve repository root regardless of invocation directory -------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir
Set-Location $RootDir

$VenvDir    = Join-Path $RootDir '.venv'
$ApiDir     = Join-Path $RootDir 'apps\api'
$WebDir     = Join-Path $RootDir 'apps\web'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

# --- Locate a Python launcher (prefer the py launcher, then python) ---------
function Resolve-Python {
    if (Get-Command 'py' -ErrorAction SilentlyContinue) {
        # Ask the launcher for a 3.x interpreter explicitly.
        return @('py', '-3')
    }
    if (Get-Command 'python' -ErrorAction SilentlyContinue) {
        return @('python')
    }
    throw "Python 3.12+ is required but neither 'py' nor 'python' was found on PATH."
}

$pythonCmd = Resolve-Python
Write-Host "[setup] Using Python launcher: $($pythonCmd -join ' ')" -ForegroundColor Cyan

# --- Verify Node.js is present ----------------------------------------------
if (-not (Get-Command 'node' -ErrorAction SilentlyContinue)) {
    throw "Node.js 18+ is required but 'node' was not found on PATH."
}
Write-Host "[setup] Using Node: $(node --version)" -ForegroundColor Cyan

# --- Create the virtual environment -----------------------------------------
if (-not (Test-Path $VenvPython)) {
    Write-Host "[setup] Creating virtual environment at $VenvDir ..." -ForegroundColor Cyan
    & $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -m venv $VenvDir
}
else {
    Write-Host "[setup] Reusing existing virtual environment at $VenvDir" -ForegroundColor DarkGray
}

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment python not found at $VenvPython after creation."
}

# --- Install the backend (editable, with dev extras) ------------------------
Write-Host '[setup] Upgrading pip ...' -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip

Write-Host "[setup] Installing backend (editable + dev extras) from $ApiDir ..." -ForegroundColor Cyan
# Quote the path[extras] target so the shell treats it as one argument.
& $VenvPython -m pip install -e "$ApiDir[dev]"

# --- Copy .env if the user has not created one ------------------------------
$envFile     = Join-Path $RootDir '.env'
$envExample  = Join-Path $RootDir '.env.example'
if ((-not (Test-Path $envFile)) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host '[setup] Created .env from .env.example (demo defaults).' -ForegroundColor Green
}

# --- Install frontend dependencies ------------------------------------------
Write-Host "[setup] Installing frontend dependencies in $WebDir ..." -ForegroundColor Cyan
Push-Location $WebDir
try {
    & npm install
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host '[setup] Done. Next steps:' -ForegroundColor Green
Write-Host '  * Start everything:   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1'
Write-Host '  * Backend URL :       http://localhost:8000  (docs at /docs)'
Write-Host '  * Frontend URL:       http://localhost:3000'
Write-Host ''
