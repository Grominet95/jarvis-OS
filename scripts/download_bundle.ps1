function Test-JarvisBundlePresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )
    $manifest = Join-Path $ProjectRoot "bundle\manifest.json"
    $venvPy = Join-Path $ProjectRoot "bundle\.venv\Scripts\python.exe"
    return (Test-Path $manifest) -and (Test-Path $venvPy)
}

function Install-JarvisBundle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )
    if (Test-JarvisBundlePresent -ProjectRoot $ProjectRoot) { return }

    if ($env:OS -notmatch "Windows") {
        Write-Host ""
        Write-Host "  Bundle offline absent." -ForegroundColor Red
        Write-Host "  Telechargement auto : Windows uniquement." -ForegroundColor DarkGray
        Write-Host "  Place un dossier bundle/ complet (manifest.json + .venv) puis relance setup." -ForegroundColor White
        Write-Host ""
        exit 1
    }

    $version = "v0.3.2"
    $url = "https://techalchemy.fr/jarvis-bundle-windows-$version/bundle.zip"
    $expectedBytes = 657929168

    Write-Host ""
    Write-Host "  Bundle offline absent, telechargement..." -ForegroundColor Yellow
    Write-Host "  $url" -ForegroundColor DarkGray
    Write-Host ""

    $staging = Join-Path $env:TEMP "jarvis-bundle-download"
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $zipPath = Join-Path $staging "bundle.zip"

    try {
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($curl) {
            & curl.exe -L --progress-bar -o $zipPath $url
            if ($LASTEXITCODE -ne 0) {
                throw "curl exit code $LASTEXITCODE"
            }
        } else {
            Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        }

        if (-not (Test-Path $zipPath)) {
            throw "Archive not downloaded"
        }
        $size = (Get-Item $zipPath).Length
        if ($size -lt [long]($expectedBytes * 0.95)) {
            throw "Download incomplete ($size bytes, expected ~$expectedBytes)"
        }

        Write-Host ""
        Write-Host "  Extraction..." -ForegroundColor Yellow
        $extractDir = Join-Path $staging "extract"
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

        $bundleSrc = Get-ChildItem -Path $extractDir -Recurse -Directory -Filter "bundle" |
            Where-Object { Test-Path (Join-Path $_.FullName "manifest.json") } |
            Select-Object -First 1
        if (-not $bundleSrc) {
            if (Test-Path (Join-Path $extractDir "manifest.json")) {
                $bundleSrc = Get-Item $extractDir
            } else {
                throw "Invalid archive: bundle/manifest.json not found"
            }
        }

        $bundleDest = Join-Path $ProjectRoot "bundle"
        if (Test-Path $bundleDest) {
            Remove-Item $bundleDest -Recurse -Force
        }
        Copy-Item $bundleSrc.FullName $bundleDest -Recurse -Force
        Write-Host "  Bundle installe dans $bundleDest" -ForegroundColor Green
        Write-Host ""
    } catch {
        Write-Host ""
        Write-Host "  Echec du telechargement : $_" -ForegroundColor Red
        Write-Host "  Verifie ta connexion ou place manuellement le dossier bundle/." -ForegroundColor White
        Write-Host ""
        exit 1
    } finally {
        Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-JarvisBundlePresent -ProjectRoot $ProjectRoot)) {
        Write-Host ""
        Write-Host "  Bundle incomplet apres extraction (manifest.json ou .venv manquant)." -ForegroundColor Red
        Write-Host ""
        exit 1
    }
}
