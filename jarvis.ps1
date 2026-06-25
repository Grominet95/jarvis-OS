param(
    [Parameter(Position = 0)]
    [string]$Command = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Force UTF-8 for every child Python process. When stdout/stderr are redirected to
# a log file (run command), Python otherwise falls back to the legacy ANSI code page
# (cp1252) with strict error handling, so any non-cp1252 char in a log line (e.g. the
# arrow glyph) raises UnicodeEncodeError, kills the process and leaves an empty log.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

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

function Invoke-JarvisPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PyArgs)
    $python = Get-JarvisPython
    if ($python) {
        & $python @PyArgs
        return
    }
    & uv run python @PyArgs
}

function Get-LivekitCommand {
    $bundled = Join-Path $PSScriptRoot "bundle\bin\livekit-server.exe"
    if (Test-Path $bundled) { return $bundled }
    return "livekit-server"
}

function Get-DotEnvValue {
    param(
        [string]$Key,
        [string]$Default = ""
    )
    if (-not (Test-Path ".env")) { return $Default }
    foreach ($line in Get-Content ".env" -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -eq 2 -and $parts[0].Trim() -eq $Key) {
            return $parts[1].Trim()
        }
    }
    return $Default
}

function Stop-PortListeners {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $connections) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -lt 400) { return $true }
        } catch {
            Start-Sleep -Milliseconds 300
        }
    }
    return $false
}

function Wait-LogMatch {
    param(
        [string]$LogPath,
        [string]$Pattern,
        [int]$TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $LogPath) {
            $content = Get-Content $LogPath -Raw -ErrorAction SilentlyContinue
            if ($content -and ($content -match $Pattern)) { return $true }
        }
        Start-Sleep -Milliseconds 300
    }
    return $false
}

function Start-BackgroundProcess {
    param(
        [string]$CommandLine,
        [string]$LogPath
    )
    # Wrap the whole command in an outer quote pair. `cmd /c` strips that outer pair
    # before executing; without it, a CommandLine that starts with a quoted path (e.g.
    # "C:\...\python.exe") triggers cmd's quote-stripping rule, mangles the command and
    # it silently never runs — leaving an empty log and an API that never binds.
    $wrapped = "`"$CommandLine > `"$LogPath`" 2>&1`""
    return Start-Process -FilePath "cmd.exe" `
        -ArgumentList @("/c", $wrapped) `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden `
        -PassThru
}

function Invoke-JarvisRun {
    $apiPort = [int](Get-DotEnvValue -Key "PORT" -Default "8000")
    $logDir = Join-Path $env:TEMP "jarvis"
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $lkLog = Join-Path $logDir "livekit.log"
    $apiLog = Join-Path $logDir "api.log"
    $voiceLog = Join-Path $logDir "voice.log"
    Write-Host ""
    Write-Host "  J A R V I S" -ForegroundColor Cyan
    Write-Host "  activation systeme" -ForegroundColor DarkGray
    Write-Host ""

    # Tuer les process residuels AVANT de toucher aux logs : un livekit-server
    # (ou un python jarvis) encore vivant d'un run precedent garde son .log
    # ouvert, et "" | Set-Content echouerait avec "le fichier est en cours
    # d'utilisation par un autre processus".
    Stop-Process -Name "livekit-server" -Force -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "jarvis\.(app|interfaces\.voice\.agent)" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-PortListeners -Ports @(7880, 7881, $apiPort)
    Start-Sleep -Milliseconds 300

    # Logs (re)initialises une fois les locks liberes ; -ErrorAction par securite.
    foreach ($log in @($lkLog, $apiLog, $voiceLog)) {
        "" | Set-Content $log -ErrorAction SilentlyContinue
    }

    $procs = @()

    Write-Host "  LiveKit  demarrage..." -ForegroundColor Yellow
    $lkCmd = Get-LivekitCommand
    $lkProc = Start-BackgroundProcess `
        -CommandLine "$lkCmd --dev --node-ip 127.0.0.1 --keys `"devkey: devsecretdevsecretdevsecretdevsecret`"" `
        -LogPath $lkLog
    $procs += $lkProc

    if (Wait-HttpOk -Url "http://127.0.0.1:7880/" -TimeoutSeconds 40) {
        Write-Host "  LiveKit  ws://localhost:7880" -ForegroundColor Green
    } else {
        Write-Host "  LiveKit  timeout - voir $lkLog" -ForegroundColor Red
        foreach ($p in $procs) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }

    # Preflight : verifie l'environnement (deps natives, .env, port) et explique
    # clairement tout probleme AVANT de tenter de lancer l'API (evite le timeout opaque).
    $python = Get-JarvisPython
    if ($python) { & $python -m jarvis.kernel.preflight } else { uv run python -m jarvis.kernel.preflight }
    if ($LASTEXITCODE -ne 0) {
        foreach ($p in $procs) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }

    Write-Host "  API      demarrage..." -ForegroundColor Yellow
    $python = Get-JarvisPython
    $apiCmd = if ($python) { "`"$python`" -m jarvis.app" } else { "uv run python -m jarvis.app" }
    $apiProc = Start-BackgroundProcess `
        -CommandLine $apiCmd `
        -LogPath $apiLog
    $procs += $apiProc

    if (Wait-HttpOk -Url "http://127.0.0.1:$apiPort/health" -TimeoutSeconds 90) {
        Write-Host "  API      http://localhost:$apiPort" -ForegroundColor Green
    } else {
        Write-Host "  API      timeout - l'API n'a pas demarre (ce n'est PAS l'API LLM)" -ForegroundColor Red
        # Affiche la fin du log : la vraie erreur y est (crash au demarrage :
        # dependance native manquante, .env invalide, port 8000 occupe...).
        if (Test-Path $apiLog) {
            Write-Host ""
            Write-Host "  --- dernieres lignes de $apiLog ---" -ForegroundColor DarkGray
            Get-Content $apiLog -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host "  $_" -ForegroundColor DarkGray
            }
            Write-Host ""
        }
        foreach ($p in $procs) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }

    Write-Host "  Vocal    prechauffement (~10s)..." -ForegroundColor Yellow
    $python = Get-JarvisPython
    $voiceCmd = if ($python) {
        "set PYTHONWARNINGS=ignore&& `"$python`" -m jarvis.interfaces.voice.agent dev --log-level info"
    } else {
        "set PYTHONWARNINGS=ignore&& uv run python -m jarvis.interfaces.voice.agent dev --log-level info"
    }
    $voiceProc = Start-BackgroundProcess `
        -CommandLine $voiceCmd `
        -LogPath $voiceLog
    $procs += $voiceProc

    if (Wait-LogMatch -LogPath $voiceLog -Pattern "Jarvis vocal prêt" -TimeoutSeconds 90) {
        Write-Host "  Vocal    pret" -ForegroundColor Green
    } else {
        Write-Host "  Vocal    prechauffement long - voir $voiceLog" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "  Jarvis pret" -ForegroundColor Green
    Write-Host "  -> http://localhost:$apiPort/admin" -ForegroundColor White
    Write-Host "  -> clique sur le micro pour le mode vocal" -ForegroundColor DarkGray
    Write-Host "  -> Ctrl-C pour arreter" -ForegroundColor DarkGray
    Write-Host "  Logs : $logDir" -ForegroundColor DarkGray
    Write-Host ""

    try {
        # N'attendre que les process encore vivants : si l'un est deja sorti
        # (ex. agent vocal qui crashe au warmup), Wait-Process leverait
        # "Impossible de trouver un processus assorti de l'identificateur".
        $alive = @($procs | Where-Object { $_ -and -not $_.HasExited })
        if ($alive) {
            Wait-Process -Id ($alive | ForEach-Object { $_.Id }) -ErrorAction SilentlyContinue
        }
    } finally {
        Write-Host ""
        Write-Host "  arret en cours..." -ForegroundColor DarkGray
        foreach ($p in $procs) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        Stop-Process -Name "livekit-server" -Force -ErrorAction SilentlyContinue
        Write-Host "  Jarvis arrete" -ForegroundColor DarkGray
    }
}

Repair-BundleVenv

switch ($Command.ToLowerInvariant()) {
    { $_ -in @("eclosion", "setup") } {
        & "$PSScriptRoot\setup.ps1"
    }
    "api" {
        Invoke-JarvisPython "-m" "jarvis.app"
    }
    "voice" {
        Invoke-JarvisPython "-m" "jarvis.interfaces.voice.agent" "dev"
    }
    "livekit" {
        $lk = Get-LivekitCommand
        & $lk --dev --node-ip 127.0.0.1 --keys "devkey: devsecretdevsecretdevsecretdevsecret"
    }
    { $_ -in @("run", "start") } {
        Invoke-JarvisRun
    }
    "doctor" {
        $port = Get-DotEnvValue -Key "PORT" -Default "8000"
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:$port/health" -UseBasicParsing -TimeoutSec 3
            Write-Host "  FastAPI  en ligne (:$port)" -ForegroundColor Green
        } catch {
            Write-Host "  FastAPI  eteint (port $port)" -ForegroundColor Yellow
        }
        if (Get-Command livekit-server -ErrorAction SilentlyContinue) {
            Write-Host "  LiveKit  binaire installe" -ForegroundColor Green
        } else {
            Write-Host "  LiveKit  binaire absent" -ForegroundColor Yellow
            Write-Host "  https://github.com/livekit/livekit/releases" -ForegroundColor DarkGray
        }
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Write-Host "  uv       installe" -ForegroundColor Green
        } else {
            Write-Host "  uv       absent" -ForegroundColor Red
        }
    }
    default {
        Write-Host ""
        Write-Host "  Usage : .\jarvis.ps1 <commande>"
        Write-Host ""
        Write-Host "    run        demarre tout (LiveKit + API + Voice)"
        Write-Host "    api        serveur FastAPI uniquement"
        Write-Host "    voice      pipeline vocal LiveKit"
        Write-Host "    livekit    serveur LiveKit local"
        Write-Host "    setup      assistant web de configuration"
        Write-Host "    eclosion   alias de setup"
        Write-Host "    doctor     diagnostic rapide"
        Write-Host ""
        exit 1
    }
}
