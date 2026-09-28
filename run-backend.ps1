# LifeLine backend launcher (Windows PowerShell)
# Verifies prerequisites, then starts uvicorn on :8000. Errors stay visible.
$ErrorActionPreference = "Stop"

$backend = Join-Path $PSScriptRoot "backend"
$venvPython = Join-Path $backend "venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "venv not found. Creating it first..." -ForegroundColor Yellow
    Push-Location $backend
    python -m venv venv
    & .\venv\Scripts\python.exe -m pip install -r requirements.txt
    Pop-Location
}

if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Warning "backend\.env not found."
    Write-Host "  Copy the template and add your keys, then restart:"
    Write-Host "    cd backend; copy .env.example .env; notepad .env"
    Write-Host "  (Continuing anyway - the app runs with memory/LLM disabled and discloses it.)"
}

if (-not (Test-Path (Join-Path $backend "data\store.json"))) {
    Write-Warning "Local store is empty - seeding the demo patient first..."
    & $venvPython (Join-Path $backend "seed\seed_patient.py")
}

Write-Host "Starting LifeLine backend on http://localhost:8000 ..." -ForegroundColor Green
Set-Location $backend
& $venvPython -m uvicorn app.main:app --reload --port 8000
