$script:BundleReleaseVersion = "v0.3.2"
$script:BundleZipBytes = 657929168

function Get-JarvisBundleZipUrl {
    param([string]$Version = $script:BundleReleaseVersion)
    return "https://techalchemy.fr/jarvis-bundle-windows-$Version/bundle.zip"
}

function Test-JarvisBundlePresent {
    param([string]$ProjectRoot)
    $manifest = Join-Path $ProjectRoot "bundle\manifest.json"
    $venvPy = Join-Path $ProjectRoot "bundle\.venv\Scripts\python.exe"
    return (Test-Path $manifest) -and (Test-Path $venvPy)
}

function Get-JarvisZipMemberRelPath {
    param([string]$EntryName)
    $normalized = $EntryName.Replace("\", "/")
    if (-not $normalized -or $normalized.EndsWith("/")) { return $null }
    if ($normalized.StartsWith("bundle/")) {
        $normalized = $normalized.Substring(7)
    }
    if (-not $normalized) { return $null }
    # Meme jeu de rejets que _zip_member_dest cote Python (kernel/bundle_download.py) :
    # lettre de lecteur, remontee `..`, et chemin enracine. Join-Path ne traite pas
    # une partie droite enracinee comme absolue, donc le "/" ne s'echappe pas ici —
    # on le rejette quand meme pour que les deux implementations acceptent
    # exactement le meme ensemble de membres, et pour ne pas dependre de ce detail.
    if ($normalized -match '^[A-Za-z]:' -or
        $normalized.Contains("..") -or
        $normalized.StartsWith("/")) { return $null }
    return $normalized
}

function Expand-JarvisBundleZip {
    param(
        [string]$ZipPath,
        [string]$BundleDest
    )
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $written = 0
        foreach ($entry in $zip.Entries) {
            $rel = Get-JarvisZipMemberRelPath -EntryName $entry.FullName
            if (-not $rel) { continue }
            $dest = Join-Path $BundleDest $rel
            $destDir = Split-Path $dest -Parent
            if ($destDir -and -not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            if ($entry.FullName.EndsWith("/")) { continue }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
            $written++
        }
        if ($written -eq 0) {
            throw "Invalid archive: no files to extract"
        }
    } finally {
        $zip.Dispose()
    }
    $manifest = Join-Path $BundleDest "manifest.json"
    if (-not (Test-Path $manifest)) {
        throw "Invalid archive: manifest.json missing after extraction"
    }
}

function Install-JarvisBundle {
    param([string]$ProjectRoot)
    if (Test-JarvisBundlePresent -ProjectRoot $ProjectRoot) { return }
    $url = Get-JarvisBundleZipUrl
    Write-Host ""
    Write-Host "  Bundle offline introuvable, telechargement..." -ForegroundColor Yellow
    Write-Host "  $url" -ForegroundColor DarkGray
    Write-Host ""
    $staging = Join-Path $env:TEMP "jarvis-bundle-download"
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $zipPath = Join-Path $staging "bundle.zip"
    $bundleDest = Join-Path $ProjectRoot "bundle"
    try {
        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        $size = (Get-Item $zipPath).Length
        if ($size -ne $script:BundleZipBytes) {
            throw "Invalid bundle.zip size: expected $($script:BundleZipBytes), got $size"
        }
        if (Test-Path $bundleDest) {
            Remove-Item $bundleDest -Recurse -Force
        }
        New-Item -ItemType Directory -Path $bundleDest -Force | Out-Null
        Expand-JarvisBundleZip -ZipPath $zipPath -BundleDest $bundleDest
        # Rehome ici meme si jarvis.ps1 rappelle Repair-BundleVenv juste apres :
        # Install-JarvisBundle doit rendre un bundle utilisable a elle seule. Le
        # re-ancrage est idempotent, et le rejouer coute infiniment moins qu'une
        # fonction publique qui depend de ce que fait son appelant.
        $rehome = Join-Path $ProjectRoot "scripts\release\rehome_bundle.ps1"
        if (Test-Path $rehome) {
            & $rehome -ProjectRoot $ProjectRoot
        }
        Write-Host "  Bundle installe dans $bundleDest" -ForegroundColor Green
        Write-Host ""
    } catch {
        Write-Host "  Echec du telechargement : $_" -ForegroundColor Red
        Write-Host "  Lance .\jarvis.ps1 setup et utilise le bouton Telecharger du wizard." -ForegroundColor White
        exit 1
    } finally {
        Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}
