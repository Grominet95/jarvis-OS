param(
    [switch]$Ci
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Ensure-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ask-BuildBundle {
    $raw = Read-Host "Construire le bundle offline maintenant ? [y/N]"
    return $raw.Trim().ToLowerInvariant() -in @("y", "yes", "o", "oui")
}

function Repair-BundleVenv {
    $rehome = Join-Path $PSScriptRoot "scripts\release\rehome_bundle.ps1"
    if (Test-Path $rehome) {
        & $rehome -ProjectRoot $PSScriptRoot
    }
}

function Get-JarvisPython {
    $bundlePy = Join-Path $PSScriptRoot "bundle\.venv\Scripts\python.exe"
    $venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $bundlePy) { return $bundlePy }
    if (Test-Path $venvPy) { return $venvPy }
    return $null
}

function Add-PathIfNeeded {
    param([string]$PathToAdd)
    if ([string]::IsNullOrWhiteSpace($PathToAdd)) { return }
    if ($env:PATH -notlike "*$PathToAdd*") {
        $env:PATH = "$PathToAdd;$env:PATH"
    }
}

function Ensure-Uv {
    if (Ensure-Command "uv") { return }
    Write-Host "uv introuvable, installation..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    Add-PathIfNeeded -PathToAdd (Join-Path $env:USERPROFILE ".local\bin")
    Add-PathIfNeeded -PathToAdd (Join-Path $env:USERPROFILE ".cargo\bin")
    if (-not (Ensure-Command "uv")) {
        throw "uv introuvable apres installation."
    }
}

function Get-BundledUv {
    $bundledUv = Join-Path $PSScriptRoot "bundle\bin\uv.exe"
    if (Test-Path $bundledUv) { return $bundledUv }
    if (Ensure-Command "uv") { return "uv" }
    return $null
}

function Ensure-JarvisPackage {
    param([string]$PythonPath)
    & $PythonPath -c "import jarvis.setup_app" 2>$null
    if ($LASTEXITCODE -eq 0) { return }
    $uvCmd = Get-BundledUv
    if (-not $uvCmd) { throw "jarvis package missing in venv and uv unavailable." }
    # Bundle case: deps are already installed in the venv, only the editable
    # link needs (re)registering -> offline + no-deps avoids any network call.
    & $uvCmd pip install --python $PythonPath --no-deps -e .
    if ($LASTEXITCODE -ne 0) {
        & $uvCmd pip install --python $PythonPath -e .
        if ($LASTEXITCODE -ne 0) { throw "jarvis package install failed." }
    }
}

Repair-BundleVenv

if ($Ci) {
    Write-Host "JARVIS V3 - setup --Ci (mode non-interactif)" -ForegroundColor Cyan
    $py = Get-JarvisPython
    if (-not $py) {
        Ensure-Uv
        uv sync --frozen --group dev
        $py = Get-JarvisPython
    }
    if (-not $py) { throw "Python runtime introuvable." }
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

$python = Get-JarvisPython
if (-not $python) {
    if (Test-Path (Join-Path $PSScriptRoot "bundle\manifest.json")) {
        throw "Bundle detecte mais bundle/.venv manquant. Relance scripts\release\build_bundle.ps1"
    }
    Write-Host "Aucun runtime pre-packaged detecte." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Option A (recommandee) : telecharge une release Jarvis avec bundle offline" -ForegroundColor White
    Write-Host "Option B (maintainer)    : scripts\release\build_bundle.ps1 (une fois, avec reseau)" -ForegroundColor White
    Write-Host "Option C (dev)           : uv sync puis relance .\setup.ps1" -ForegroundColor White
    Write-Host ""
    if (Ask-BuildBundle) {
        & "$PSScriptRoot\scripts\release\build_bundle.ps1"
        $python = Get-JarvisPython
    }
}

if (-not $python) {
    Ensure-Uv
    if (-not (Test-Path ".venv")) {
        uv sync
        if ($LASTEXITCODE -ne 0) { throw "uv sync a echoue." }
    }
    $python = Get-JarvisPython
}

if (-not $python) {
    throw "Impossible de demarrer l'assistant de configuration."
}

Ensure-JarvisPackage -PythonPath $python

Write-Host "Ouverture de http://127.0.0.1:8765/setup" -ForegroundColor Green
Write-Host "Ctrl-C pour arreter l'assistant." -ForegroundColor DarkGray
Write-Host ""
& $python -m jarvis.setup_app
