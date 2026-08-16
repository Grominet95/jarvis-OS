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

. (Join-Path $PSScriptRoot "scripts\onedrive_guard.ps1")
. (Join-Path $PSScriptRoot "scripts\download_bundle.ps1")

function Test-BundlePresent {
    return Test-JarvisBundlePresent -ProjectRoot $PSScriptRoot
}

function Test-DevVenvPresent {
    return Test-Path (Join-Path $PSScriptRoot ".venv\Scripts\python.exe")
}

function Require-JarvisBundle {
    if (Test-BundlePresent) { return }
    if (Test-DevVenvPresent) { return }
    Write-Host ""
    Write-Host "  Bundle offline absent." -ForegroundColor Red
    Write-Host "  Lance d'abord : .\jarvis.ps1 setup" -ForegroundColor White
    Write-Host ""
    exit 1
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

function Stop-JarvisRuntime {
    param(
        [int[]]$ExtraPorts = @()
    )
    Stop-Process -Name "livekit-server" -Force -ErrorAction SilentlyContinue

    $apiPort = [int](Get-DotEnvValue -Key "PORT" -Default "8000")
    $ports = @(7880, 7881, 8765, $apiPort) + $ExtraPorts
    Stop-PortListeners -Ports ($ports | Select-Object -Unique)

    $rootPattern = [regex]::Escape($PSScriptRoot)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return }
        $kill = $false
        if ($_.Name -eq "python.exe") {
            if ($cmd -match "jarvis\.(app|setup_app|interfaces\.voice\.agent|kernel\.preflight)") { $kill = $true }
            # Repli : un python du projet lance autrement (main.py, voice_agent.py,
            # interpreteur du bundle). On exige un point d'entree reconnaissable EN PLUS
            # du chemin projet — sinon la regle tue n'importe quel python dont la ligne
            # de commande mentionne le dossier, dont un `pytest` ou un debogueur d'IDE
            # en cours dans le depot.
            elseif ($cmd -match $rootPattern -and
                    $cmd -match "(-m\s+jarvis\b|main\.py|voice_agent\.py|bundle\\\.venv)") { $kill = $true }
        }
        if ($_.Name -eq "cmd.exe" -and $cmd -match "Temp\\jarvis") { $kill = $true }
        if ($kill) {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Clear-JarvisStaleLogDirs {
    Get-ChildItem -Path $env:TEMP -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^jarvis(\.stale\.|[-_])" } |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-6) } |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}

function Initialize-JarvisLogDir {
    Stop-JarvisRuntime
    Clear-JarvisStaleLogDirs
    Start-Sleep -Milliseconds 400

    $preferred = Join-Path $env:TEMP "jarvis"
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            if (Test-Path $preferred) {
                Remove-Item $preferred -Recurse -Force -ErrorAction Stop
            }
            New-Item -ItemType Directory -Path $preferred -Force | Out-Null
            return $preferred
        } catch {
            try {
                if (Test-Path $preferred) {
                    $stale = Join-Path $env:TEMP ("jarvis.stale." + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
                    Move-Item $preferred $stale -Force -ErrorAction Stop
                }
                New-Item -ItemType Directory -Path $preferred -Force | Out-Null
                return $preferred
            } catch {
                Stop-JarvisRuntime
                Start-Sleep -Milliseconds 400
            }
        }
    }

    $fallback = Join-Path $env:TEMP ("jarvis-" + $PID)
    New-Item -ItemType Directory -Path $fallback -Force | Out-Null
    return $fallback
}

function Invoke-JarvisRun {
    $apiPort = [int](Get-DotEnvValue -Key "PORT" -Default "8000")
    Write-Host ""
    Write-Host "  J A R V I S" -ForegroundColor Cyan
    Write-Host "  activation systeme" -ForegroundColor DarkGray
    Write-Host ""

    $logDir = Initialize-JarvisLogDir
    $lkLog = Join-Path $logDir "livekit.log"
    $apiLog = Join-Path $logDir "api.log"
    $voiceLog = Join-Path $logDir "voice.log"

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
        Write-Host "  LiveKit  le serveur LiveKit n'a pas demarre" -ForegroundColor Red
        if (Test-Path $lkLog) {
            Write-Host ""
            Write-Host "  --- dernieres lignes de $lkLog ---" -ForegroundColor DarkGray
            Get-Content $lkLog -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host "  $_" -ForegroundColor DarkGray
            }
            Write-Host "  Causes frequentes : port 7880 occupe, ou livekit-server absent." -ForegroundColor DarkGray
            Write-Host ""
        }
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
        Write-Host "  Vocal    prechauffement long ou echec" -ForegroundColor Yellow
        if (Test-Path $voiceLog) {
            Write-Host "  --- dernieres lignes de $voiceLog ---" -ForegroundColor DarkGray
            Get-Content $voiceLog -Tail 10 -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host "  $_" -ForegroundColor DarkGray
            }
            Write-Host ""
        }
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
        Stop-JarvisRuntime
        Write-Host "  Jarvis arrete" -ForegroundColor DarkGray
    }
}

$guardCommand = if ($Command.Trim() -ne "") { $Command } else { "setup" }
# `doctor` et l'aide (commande vide ou inconnue) ne demarrent rien : ils n'ont pas
# a proposer de deplacer le dossier de l'utilisateur, et sans argument le
# RelaunchCommand vaut "setup" — taper `.\jarvis.ps1` pour lire l'aide aurait
# deplace l'install puis lance le wizard. Sur ces commandes, le garde-fou se
# contente d'expliquer et de sortir.
$guardReadOnly = $Command.Trim() -eq "" -or
                 $Command.ToLowerInvariant() -notin @(
                     "eclosion", "setup", "run", "start", "api", "voice", "livekit"
                 )
Invoke-JarvisOneDriveGuard `
    -ProjectRoot $PSScriptRoot `
    -NonInteractive:($guardReadOnly -or $env:CI -eq "true") `
    -RelaunchCommand $guardCommand

# Restart complet uniquement : `run`/`start` relancent toute la pile, `setup` a
# besoin du port 8765. `api`, `voice` et `livekit` sont documentees comme
# composables (un composant par terminal, cf. l'aide plus bas) — les inclure ici
# ferait que `.\jarvis.ps1 voice` tue l'API et LiveKit lances juste avant.
switch ($Command.ToLowerInvariant()) {
    { $_ -in @("eclosion", "setup", "run", "start") } {
        Stop-JarvisRuntime
    }
}

if ($Command.Trim() -ne "") {
    $cmd = $Command.ToLowerInvariant()
    if ($cmd -in @("eclosion", "setup")) {
        Install-JarvisBundle -ProjectRoot $PSScriptRoot
        Repair-BundleVenv
    } elseif ($cmd -in @("run", "start", "api", "voice", "livekit")) {
        Require-JarvisBundle
        Repair-BundleVenv
    }
}

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
