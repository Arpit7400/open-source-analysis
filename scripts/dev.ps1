#Requires -Version 5.1
<#
.SYNOPSIS
    CareerForge AI dev launcher (Windows PowerShell).

.DESCRIPTION
    Starts the FastAPI backend (:8000) in a background job, then runs the
    Next.js frontend (:3000) in the foreground. When you press Ctrl-C (or the
    frontend exits), the backend job is stopped and cleaned up.

    Assumes scripts\setup.ps1 has already been run (a .venv exists and the web
    dependencies are installed). If not, this script runs setup automatically.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#>

$ErrorActionPreference = 'Stop'

# --- Resolve repository root regardless of invocation directory -------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir
Set-Location $RootDir

$VenvDir   = Join-Path $RootDir '.venv'
$WebDir    = Join-Path $RootDir 'apps\web'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$NodeModules = Join-Path $WebDir 'node_modules'

# --- Ensure dependencies exist ----------------------------------------------
if (-not (Test-Path $VenvPython) -or -not (Test-Path $NodeModules)) {
    Write-Host '[dev] Dependencies missing; running one-time setup...' -ForegroundColor Yellow
    & (Join-Path $ScriptDir 'setup.ps1')
}

if (-not (Test-Path $VenvPython)) {
    throw "Backend virtual environment not found at $VenvPython. Run scripts\setup.ps1 first."
}

$backendJob = $null

# --- Cleanup helper: stop the backend job on exit ---------------------------
function Stop-Backend {
    param([Parameter(Mandatory = $false)] $Job)
    if ($null -ne $Job) {
        Write-Host ''
        Write-Host '[dev] Shutting down backend...' -ForegroundColor Yellow
        Stop-Job   -Job $Job -ErrorAction SilentlyContinue
        Remove-Job -Job $Job -Force -ErrorAction SilentlyContinue
    }
}

try {
    # --- Start the backend in a background job ------------------------------
    Write-Host '[dev] Starting backend on http://localhost:8000 (demo mode)...' -ForegroundColor Cyan
    $backendJob = Start-Job -Name 'careerforge-api' -ScriptBlock {
        param($py, $root)
        Set-Location $root
        & $py -m careerforge_api
    } -ArgumentList $VenvPython, $RootDir

    # Give the backend a moment to bind the port.
    Start-Sleep -Seconds 2

    Write-Host ''
    Write-Host '  Backend  : http://localhost:8000        (API docs: http://localhost:8000/docs)'
    Write-Host '  Frontend : http://localhost:3000'
    Write-Host ''
    Write-Host '  Press Ctrl-C to stop both.' -ForegroundColor DarkGray
    Write-Host ''

    # --- Run the frontend in the foreground ---------------------------------
    # npm is a .cmd shim on Windows; call it via cmd /c so PowerShell resolves it.
    Push-Location $WebDir
    try {
        & npm run dev
    }
    finally {
        Pop-Location
    }
}
finally {
    Stop-Backend -Job $backendJob
}
