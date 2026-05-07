$ErrorActionPreference = "Stop"

function Write-Step {
    param(
        [int]$Current,
        [int]$Total,
        [string]$Title
    )
    Write-Host ""
    Write-Host ("-" * 60)
    Write-Host ("[ {0}/{1} ] {2}" -f $Current, $Total, $Title) -ForegroundColor Cyan
    Write-Host ("-" * 60)
}

function Require-Value {
    param(
        [string]$Prompt,
        [bool]$Secret = $false,
        [string]$Default = ""
    )
    while ($true) {
        if ($Secret) {
            $secure = Read-Host -Prompt $Prompt -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try {
                $value = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            }
        } else {
            $suffix = ""
            if ($Default -ne "") {
                $suffix = " [$Default]"
            }
            $inputValue = Read-Host -Prompt "$Prompt$suffix"
            if ([string]::IsNullOrWhiteSpace($inputValue) -and $Default -ne "") {
                $value = $Default
            } else {
                $value = $inputValue
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
        Write-Host "Valeur requise." -ForegroundColor Yellow
    }
}

function Ask-YesNo {
    param(
        [string]$Prompt,
        [bool]$DefaultNo = $true
    )
    $defaultLabel = if ($DefaultNo) { "Y/N (default: N)" } else { "Y/N (default: Y)" }
    $raw = Read-Host -Prompt "$Prompt [$defaultLabel]"
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return (-not $DefaultNo)
    }
    return $raw.Trim().ToLowerInvariant() -in @("y", "yes", "o", "oui")
}

function Ensure-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Add-PathIfNeeded {
    param([string]$PathToAdd)
    if ([string]::IsNullOrWhiteSpace($PathToAdd)) {
        return
    }
    if ($env:PATH -notlike "*$PathToAdd*") {
        $env:PATH = "$PathToAdd;$env:PATH"
    }
}

$stepTotal = 8

Write-Host ""
Write-Host "JARVIS v3.0 - Setup interactif (PowerShell)" -ForegroundColor Cyan
Write-Host ""

Write-Step -Current 1 -Total $stepTotal -Title "Verification des prerequis"

$pythonCmd = $null
if (Ensure-Command "python") { $pythonCmd = "python" }
elseif (Ensure-Command "py") { $pythonCmd = "py -3" }

if (-not $pythonCmd) {
    throw "Python 3.11+ introuvable. Installe Python et active l'option Add to PATH."
}

$pyVersionRaw = & $pythonCmd --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Impossible de lire la version Python."
}
$versionText = ($pyVersionRaw | Select-Object -First 1).ToString()
$versionMatch = [regex]::Match($versionText, "(\d+)\.(\d+)")
if (-not $versionMatch.Success) {
    throw "Version Python invalide: $versionText"
}
$major = [int]$versionMatch.Groups[1].Value
$minor = [int]$versionMatch.Groups[2].Value
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
    throw "Python $major.$minor detecte, Python 3.11+ requis."
}
Write-Host "Python $major.$minor detecte." -ForegroundColor Green

if (-not (Ensure-Command "uv")) {
    Write-Host "uv introuvable, installation..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $uvBin = Join-Path $env:USERPROFILE ".local\bin"
    Add-PathIfNeeded -PathToAdd $uvBin
}
if (-not (Ensure-Command "uv")) {
    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    Add-PathIfNeeded -PathToAdd $cargoBin
}
if (-not (Ensure-Command "uv")) {
    throw "uv introuvable apres installation."
}
Write-Host "uv detecte." -ForegroundColor Green

Write-Step -Current 2 -Total $stepTotal -Title "Installation des dependances Python"
uv sync
Write-Host "Dependances installees." -ForegroundColor Green

Write-Step -Current 3 -Total $stepTotal -Title "Configuration LLM principal"
$apiBackend = "anthropic"
$openaiApiKey = ""
$openaiModel = "gpt-4o-mini"
$anthropicApiKey = ""
$anthropicModel = "claude-sonnet-4-6"
if (Ask-YesNo -Prompt "Utiliser OpenAI comme LLM principal ?" -DefaultNo $false) {
    $apiBackend = "openai"
    $openaiApiKey = Require-Value -Prompt "Cle API OpenAI (sk-...)" -Secret $true
} else {
    $anthropicApiKey = Require-Value -Prompt "Cle API Anthropic (sk-ant-...)" -Secret $true
}

Write-Step -Current 4 -Total $stepTotal -Title "Identite utilisateur"
$userFirstname = Require-Value -Prompt "Ton prenom"
Write-Host "Bonjour, $userFirstname" -ForegroundColor Green

Write-Step -Current 5 -Total $stepTotal -Title "Localisation proactive"
$proactiveCity = Require-Value -Prompt "Ville" -Default "Paris"
$proactiveLat = Require-Value -Prompt "Latitude" -Default "48.85"
$proactiveLon = Require-Value -Prompt "Longitude" -Default "2.35"

Write-Step -Current 6 -Total $stepTotal -Title "Modules optionnels"
$ttsProvider = "piper"
$elevenlabsApiKey = ""
$elevenlabsVoiceId = ""
$elevenlabsModel = "eleven_flash_v2_5"
if (Ask-YesNo -Prompt "Utiliser ElevenLabs plutot que Piper ?" -DefaultNo $true) {
    $ttsProvider = "elevenlabs"
    $elevenlabsApiKey = Require-Value -Prompt "Cle ElevenLabs (sk_...)" -Secret $true
    $elevenlabsVoiceId = Require-Value -Prompt "Voice ID ElevenLabs"
}

$livekitUrl = ""
$livekitApiKey = ""
$livekitApiSecret = ""
$deepgramApiKey = ""
if (Ask-YesNo -Prompt "Activer le pipeline vocal LiveKit ?" -DefaultNo $true) {
    $livekitUrl = Require-Value -Prompt "LiveKit URL (wss://...)"
    $livekitApiKey = Require-Value -Prompt "LiveKit API Key" -Secret $true
    $livekitApiSecret = Require-Value -Prompt "LiveKit API Secret" -Secret $true
    $deepgramApiKey = Require-Value -Prompt "Deepgram API Key" -Secret $true
}

$aisstreamKey = ""
if (Ask-YesNo -Prompt "Configurer AISstream ?" -DefaultNo $true) {
    $aisstreamKey = Require-Value -Prompt "Cle AISstream" -Secret $true
}

Write-Step -Current 7 -Total $stepTotal -Title "Telechargement des modeles ML"
if (-not (Test-Path "yolov8n.pt")) {
    uv run python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
}

$piperDir = "models/piper"
$piperModel = Join-Path $piperDir "fr_FR-upmc-medium.onnx"
$piperJson = "$piperModel.json"
if (-not (Test-Path $piperModel)) {
    New-Item -ItemType Directory -Path $piperDir -Force | Out-Null
    $baseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium"
    curl.exe -L --silent -o $piperModel "$baseUrl/fr_FR-upmc-medium.onnx"
    curl.exe -L --silent -o $piperJson "$baseUrl/fr_FR-upmc-medium.onnx.json"
}

Write-Step -Current 8 -Total $stepTotal -Title "Generation de l'environnement"
New-Item -ItemType Directory -Path "memory_data/sessions" -Force | Out-Null
New-Item -ItemType Directory -Path "memory_data/topics" -Force | Out-Null
New-Item -ItemType Directory -Path "memory_data/conso" -Force | Out-Null
New-Item -ItemType Directory -Path "memory_data/initiatives" -Force | Out-Null
New-Item -ItemType Directory -Path "workspace/projects" -Force | Out-Null
New-Item -ItemType Directory -Path "vision/faces" -Force | Out-Null

if (Test-Path ".env") {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Copy-Item ".env" ".env.backup.$stamp"
}

$envContent = @"
USER_FIRSTNAME=$userFirstname
LLM_PROVIDER=api
API_BACKEND=$apiBackend
ANTHROPIC_API_KEY=$anthropicApiKey
ANTHROPIC_MODEL=$anthropicModel
OPENAI_API_KEY=$openaiApiKey
OPENAI_MODEL=$openaiModel
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO
PROACTIVE_LAT=$proactiveLat
PROACTIVE_LON=$proactiveLon
PROACTIVE_CITY=$proactiveCity
TTS_PROVIDER=$ttsProvider
ELEVENLABS_API_KEY=$elevenlabsApiKey
ELEVENLABS_VOICE_ID=$elevenlabsVoiceId
ELEVENLABS_MODEL=$elevenlabsModel
WHISPER_MODEL=tiny
LIVEKIT_URL=$livekitUrl
LIVEKIT_API_KEY=$livekitApiKey
LIVEKIT_API_SECRET=$livekitApiSecret
DEEPGRAM_API_KEY=$deepgramApiKey
AISSTREAM_KEY=$aisstreamKey
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-large-latest
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
GOOGLE_API_KEY=
"@

Set-Content -Path ".env" -Value $envContent -Encoding UTF8

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "Systeme pret." -ForegroundColor Green
Write-Host "Lancer le serveur: uv run python main.py" -ForegroundColor White
if (-not [string]::IsNullOrWhiteSpace($livekitUrl)) {
    Write-Host "Lancer la voix: uv run python voice_agent.py dev" -ForegroundColor White
}
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""
