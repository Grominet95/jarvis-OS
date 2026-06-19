$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Set-Location ..\..

$bundleRoot = Join-Path (Get-Location) "bundle"
$venvPath = Join-Path $bundleRoot ".venv"
$modelsDir = Join-Path $bundleRoot "models"
$piperDir = Join-Path $modelsDir "piper"
$binDir = Join-Path $bundleRoot "bin"

Write-Host "Jarvis — build offline bundle (Windows)" -ForegroundColor Cyan
Write-Host "Ce script telecharge une fois Python, les deps et les modeles." -ForegroundColor DarkGray
Write-Host ""

function Ensure-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Ensure-Command "uv")) {
    Write-Host "Installation de uv..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $uvBin = Join-Path $env:USERPROFILE ".local\bin"
    if ($env:PATH -notlike "*$uvBin*") { $env:PATH = "$uvBin;$env:PATH" }
}
if (-not (Ensure-Command "uv")) {
    throw "uv introuvable."
}

New-Item -ItemType Directory -Path $bundleRoot, $modelsDir, $piperDir, $binDir -Force | Out-Null

Write-Host "[1/5] Sync Python env into bundle/.venv" -ForegroundColor Cyan
if (Test-Path $venvPath) {
    Remove-Item -Recurse -Force $venvPath
}
uv venv $venvPath --python 3.11
uv sync --python $venvPath
if ($LASTEXITCODE -ne 0) { throw "uv sync failed." }

$bundlePython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $bundlePython)) { throw "bundle python missing." }

Write-Host "[2/5] Copy uv binary" -ForegroundColor Cyan
$uvExe = (Get-Command uv).Source
Copy-Item $uvExe (Join-Path $binDir "uv.exe") -Force

Write-Host "[3/5] Download ML models" -ForegroundColor Cyan
if (-not (Test-Path "yolov8n.pt")) {
    & $bundlePython -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
}
Copy-Item "yolov8n.pt" (Join-Path $modelsDir "yolov8n.pt") -Force

$piperOnnx = Join-Path $piperDir "fr_FR-upmc-medium.onnx"
$piperJson = "$piperOnnx.json"
if (-not (Test-Path $piperOnnx)) {
    $baseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium"
    curl.exe -L --silent -o $piperOnnx "$baseUrl/fr_FR-upmc-medium.onnx"
    curl.exe -L --silent -o $piperJson "$baseUrl/fr_FR-upmc-medium.onnx.json"
}

Write-Host "[4/5] Download livekit-server" -ForegroundColor Cyan
$lkTarget = Join-Path $binDir "livekit-server.exe"
if (-not (Test-Path $lkTarget)) {
    $release = "https://github.com/livekit/livekit/releases/latest/download/livekit-server_windows_amd64.zip"
    $zipPath = Join-Path $env:TEMP "livekit-server.zip"
    curl.exe -L --silent -o $zipPath $release
    Expand-Archive -Path $zipPath -DestinationPath $binDir -Force
    $extracted = Get-ChildItem $binDir -Filter "livekit-server*.exe" | Select-Object -First 1
    if ($extracted) {
        Move-Item $extracted.FullName $lkTarget -Force
    }
}

Write-Host "[5/5] Write manifest" -ForegroundColor Cyan
$manifest = @{
    version = "1"
    platform = "windows"
    python = "3.11"
    venv = ".venv"
    models = @{
        yolo = "models/yolov8n.pt"
        piper_onnx = "models/piper/fr_FR-upmc-medium.onnx"
        piper_json = "models/piper/fr_FR-upmc-medium.onnx.json"
    }
    bin = @{
        uv = "bin/uv.exe"
        livekit = "bin/livekit-server.exe"
    }
} | ConvertTo-Json -Depth 5
Set-Content -Path (Join-Path $bundleRoot "manifest.json") -Value $manifest -Encoding UTF8

Write-Host ""
Write-Host "Bundle ready: $bundleRoot" -ForegroundColor Green
Write-Host "Next: .\jarvis.ps1 eclosion" -ForegroundColor White
