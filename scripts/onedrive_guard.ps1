function Test-JarvisPathUnderOneDrive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    $root = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $bases = @(
        $env:OneDrive,
        $env:OneDriveCommercial,
        $env:OneDriveConsumer
    ) | Where-Object { $_ -and $_.Trim() -ne "" }
    foreach ($base in $bases) {
        $normalized = [System.IO.Path]::GetFullPath($base.TrimEnd('\')).TrimEnd('\')
        if ($root.Equals($normalized, [StringComparison]::OrdinalIgnoreCase) -or
            $root.StartsWith($normalized + '\', [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return ($root -match '\\OneDrive\\' -or $root -match '\\OneDrive - ')
}

function Test-JarvisOneDriveInstall {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )
    return Test-JarvisPathUnderOneDrive -Path $ProjectRoot
}

function Get-JarvisLocalInstallDestination {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )
    $folderName = Split-Path -Leaf $ProjectRoot
    if ([string]::IsNullOrWhiteSpace($folderName)) {
        $folderName = "jarvis-OS"
    }

    $candidates = @(
        [Environment]::GetFolderPath("MyDocuments"),
        (Join-Path $env:USERPROFILE "Documents")
    ) | Where-Object { $_ -and $_.Trim() -ne "" } | Select-Object -Unique

    foreach ($docs in $candidates) {
        if (-not (Test-Path $docs)) { continue }
        if (Test-JarvisPathUnderOneDrive -Path $docs) { continue }
        return [System.IO.Path]::GetFullPath((Join-Path $docs $folderName))
    }

    return [System.IO.Path]::GetFullPath((Join-Path $env:USERPROFILE $folderName))
}

function Stop-JarvisInstallProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )
    Stop-Process -Name "livekit-server" -Force -ErrorAction SilentlyContinue

    $rootPattern = [regex]::Escape([System.IO.Path]::GetFullPath($ProjectRoot))
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return }
        $kill = $false
        if ($_.Name -eq "python.exe") {
            if ($cmd -match "jarvis\.(app|setup_app|interfaces\.voice\.agent|kernel\.preflight)") { $kill = $true }
            elseif ($cmd -match $rootPattern) { $kill = $true }
        }
        if ($_.Name -eq "cmd.exe" -and $cmd -match "Temp\\jarvis") { $kill = $true }
        if ($kill) {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Milliseconds 400
}

function Move-JarvisInstallToLocal {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$DestinationRoot
    )
    $source = [System.IO.Path]::GetFullPath($SourceRoot).TrimEnd('\')
    $destination = [System.IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')

    if ($source.Equals($destination, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source and destination paths are identical."
    }
    if ($destination.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Destination cannot be inside the current install folder."
    }

    Stop-JarvisInstallProcesses -ProjectRoot $source

    if (Test-Path $destination) {
        $existing = Get-ChildItem -Path $destination -Force -ErrorAction SilentlyContinue
        if ($existing -and $existing.Count -gt 0) {
            $destination = "${destination}-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
        }
    }

    $parent = Split-Path -Parent $destination
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    Write-Host ""
    Write-Host "  Deplacement en cours..." -ForegroundColor Yellow
    Write-Host "    $source" -ForegroundColor DarkGray
    Write-Host "    -> $destination" -ForegroundColor DarkGray
    Write-Host ""

    $robocopy = Start-Process -FilePath "robocopy.exe" -ArgumentList @(
        "`"$source`"", "`"$destination`"", "/E", "/MOVE", "/XJ", "/R:2", "/W:2",
        "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np"
    ) -Wait -PassThru -NoNewWindow

    if ($robocopy.ExitCode -ge 8) {
        throw "Robocopy failed with exit code $($robocopy.ExitCode)."
    }

    if (Test-Path $source) {
        Remove-Item -Path $source -Recurse -Force -ErrorAction SilentlyContinue
    }

    return $destination
}

function Show-JarvisOneDriveManualInstructions {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$SuggestedDestination
    )
    Write-Host ""
    Write-Host "  Deplacement manuel :" -ForegroundColor White
    Write-Host "    1. Ferme cette fenetre et tout process Jarvis en cours." -ForegroundColor DarkGray
    Write-Host "    2. Deplace le dossier complet vers un emplacement local, par exemple :" -ForegroundColor DarkGray
    Write-Host "         $SuggestedDestination" -ForegroundColor Cyan
    Write-Host "       ou C:\jarvis-OS" -ForegroundColor Cyan
    Write-Host "    3. Relance setup.bat ou run.bat depuis le nouveau dossier." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Emplacement actuel (OneDrive) :" -ForegroundColor DarkGray
    Write-Host "    $ProjectRoot" -ForegroundColor DarkGray
    Write-Host ""
}

function Invoke-JarvisOneDriveGuard {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [switch]$NonInteractive,
        [string]$RelaunchCommand = "setup"
    )
    if (-not (Test-JarvisOneDriveInstall -ProjectRoot $ProjectRoot)) { return }

    $current = [System.IO.Path]::GetFullPath($ProjectRoot)
    $destination = Get-JarvisLocalInstallDestination -ProjectRoot $ProjectRoot

    Write-Host ""
    Write-Host "  Jarvis ne peut pas s'installer depuis OneDrive." -ForegroundColor Red
    Write-Host "  OneDrive casse les liens symboliques du bundle Python (.venv)." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Emplacement detecte :" -ForegroundColor White
    Write-Host "    $current" -ForegroundColor DarkGray
    Write-Host ""

    if ($NonInteractive) {
        Show-JarvisOneDriveManualInstructions -ProjectRoot $current -SuggestedDestination $destination
        exit 1
    }

    Write-Host "  [1] Deplacer automatiquement vers (recommande) :" -ForegroundColor White
    Write-Host "      $destination" -ForegroundColor Cyan
    Write-Host "  [2] Instructions de deplacement manuel" -ForegroundColor White
    Write-Host "  [Q] Quitter" -ForegroundColor White
    Write-Host ""

    $choice = (Read-Host "  Choix [1/2/Q]").Trim().ToLowerInvariant()
    if ($choice -eq "") { $choice = "1" }
    if ($choice -in @("q", "quit")) {
        Write-Host ""
        Write-Host "  Installation annulee." -ForegroundColor DarkGray
        Write-Host ""
        exit 1
    }

    if ($choice -eq "2") {
        Show-JarvisOneDriveManualInstructions -ProjectRoot $current -SuggestedDestination $destination
        exit 1
    }

    try {
        $movedTo = Move-JarvisInstallToLocal -SourceRoot $current -DestinationRoot $destination
    } catch {
        Write-Host ""
        Write-Host "  Echec du deplacement automatique : $_" -ForegroundColor Red
        Show-JarvisOneDriveManualInstructions -ProjectRoot $current -SuggestedDestination $destination
        exit 1
    }

    $launcher = Join-Path $movedTo "jarvis.ps1"
    if (-not (Test-Path $launcher)) {
        Write-Host ""
        Write-Host "  Deplacement termine mais jarvis.ps1 introuvable dans $movedTo" -ForegroundColor Red
        exit 1
    }

    $cmd = if ([string]::IsNullOrWhiteSpace($RelaunchCommand)) { "setup" } else { $RelaunchCommand }

    Write-Host ""
    Write-Host "  Deplacement termine." -ForegroundColor Green
    Write-Host "  Relance de Jarvis depuis :" -ForegroundColor White
    Write-Host "    $movedTo" -ForegroundColor Cyan
    Write-Host ""

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "`"$launcher`"", $cmd
    ) -WorkingDirectory $movedTo | Out-Null

    exit 0
}
