# LifeLine frontend launcher (Windows PowerShell)
# Verifies prerequisites, then starts the Vite dev server. Errors stay visible.
$ErrorActionPreference = "Stop"

$frontend = Join-Path $PSScriptRoot "frontend"
$nodeModules = Join-Path $frontend "node_modules"

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Error "Node.js not found. Install Node.js LTS from https://nodejs.org, open a new terminal, and retry."
    exit 1
}

if (-not (Test-Path $nodeModules)) {
    Write-Host "node_modules not found. Running npm install (one-time)..." -ForegroundColor Yellow
    Push-Location $frontend
    npm install
    Pop-Location
}

Write-Host "Starting LifeLine frontend on http://localhost:5173 (backend expected on :8000) ..." -ForegroundColor Green
Set-Location $frontend
npm run dev
