param(
    [switch]$Ci
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

. (Join-Path $PSScriptRoot "scripts\onedrive_guard.ps1")
Invoke-JarvisOneDriveGuard -ProjectRoot $PSScriptRoot -NonInteractive:$Ci -RelaunchCommand "setup"

function Repair-BundleVenv {
    $rehome = Join-Path $PSScriptRoot "scripts\release\rehome_bundle.ps1"
    if (Test-Path $rehome) {
        & $rehome -ProjectRoot $PSScriptRoot
    }
}

function Get-BundlePython {
    return Join-Path $PSScriptRoot "bundle\.venv\Scripts\python.exe"
}

function Get-BundledUv {
    $bundledUv = Join-Path $PSScriptRoot "bundle\bin\uv.exe"
    if (Test-Path $bundledUv) { return $bundledUv }
    return $null
}

function Ensure-JarvisPackage {
    param([string]$PythonPath)
    & $PythonPath -c "import jarvis.setup_app" 2>$null
    if ($LASTEXITCODE -eq 0) { return }
    $uvCmd = Get-BundledUv
    if (-not $uvCmd) { throw "jarvis package missing in bundle venv." }
    & $uvCmd pip install --python $PythonPath --no-deps -e .
    if ($LASTEXITCODE -ne 0) {
        & $uvCmd pip install --python $PythonPath -e .
        if ($LASTEXITCODE -ne 0) { throw "jarvis package install failed." }
    }
}

if (Test-Path (Join-Path $PSScriptRoot "bundle\manifest.json")) {
    Repair-BundleVenv
}

if ($Ci) {
    Write-Host "JARVIS V3 - setup --Ci (mode non-interactif)" -ForegroundColor Cyan
    $py = Get-BundlePython
    if (-not (Test-Path $py)) { throw "Bundle Python runtime introuvable." }
    & $py -c "from jarvis.kernel.setup_layout import ensure_runtime_layout; ensure_runtime_layout()"
    if (-not (Test-Path ".env")) {
        @"
LLM_PROVIDER=api
API_BACKEND=anthropic
ANTHROPIC_API_KEY=unused-in-fake-llm-mode
ANTHROPIC_MODEL=claude-sonnet-4-6
VOICE_ANTHROPIC_MODEL=claude-haiku-4-5-20251001
USER_FIRSTNAME=B9
HOME_CITY=Paris
MEMORY_DIR=memory_data
PORT=8000
"@ | Set-Content -Path ".env" -Encoding UTF8
    }
    Write-Host "setup --Ci OK" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "JARVIS - Configuration web locale" -ForegroundColor Cyan
Write-Host ""

$python = Get-BundlePython
if (-not (Test-Path $python)) {
    throw "Bundle absent. Relance .\jarvis.ps1 setup (telecharge le bundle automatiquement)."
}

Ensure-JarvisPackage -PythonPath $python

Write-Host "Ouverture de http://127.0.0.1:8765/setup" -ForegroundColor Green
Write-Host "Ctrl-C pour arreter l'assistant." -ForegroundColor DarkGray
Write-Host ""
& $python -m jarvis.setup_app
