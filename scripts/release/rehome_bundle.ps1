param(
    [string]$ProjectRoot
)

# Re-home the bundled relocatable venv to the current machine.
# The bundle ships a standalone Python (bundle/python) and a std venv
# (bundle/.venv) whose pyvenv.cfg `home` and the editable .pth point to the
# build machine's absolute paths. This rewrites them to the local paths so the
# venv works after the bundle is moved/extracted anywhere.

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Join-Path $PSScriptRoot "..\.."
}
$root = (Resolve-Path $ProjectRoot).Path

$venvCfg = Join-Path $root "bundle\.venv\pyvenv.cfg"
$pyHome = Join-Path $root "bundle\python"
$pyExe = Join-Path $pyHome "python.exe"

# Nothing to do for dev installs (no bundle) or legacy bundles without an
# embedded Python — those can't be re-homed offline.
if (-not (Test-Path $venvCfg)) { return }
if (-not (Test-Path $pyExe)) { return }

$venvPath = Join-Path $root "bundle\.venv"
$newCfg = Get-Content $venvCfg | ForEach-Object {
    if ($_ -match '^\s*home\s*=') { "home = $pyHome" }
    elseif ($_ -match '^\s*executable\s*=') { "executable = $pyExe" }
    elseif ($_ -match '^\s*command\s*=') { "command = $pyExe -m venv $venvPath" }
    else { $_ }
}
Set-Content -Path $venvCfg -Value $newCfg -Encoding ascii

$srcPath = Join-Path $root "src"
$sitePackages = Join-Path $venvPath "Lib\site-packages"
if (Test-Path $sitePackages) {
    Get-ChildItem $sitePackages -Filter "*editable*jarvis*.pth" -ErrorAction SilentlyContinue | ForEach-Object {
        Set-Content -Path $_.FullName -Value $srcPath -Encoding ascii
    }
}
