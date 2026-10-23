# Build CellLab for Windows (run from any directory in PowerShell 5+ or pwsh):
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 [-SkipTests] [-NoPackage]
# Produces build\dist\CellLab\CellLab.exe (must pass its own self-test), then
# build\CellLab-<version>-win64-portable.zip and, when Inno Setup 6 is installed,
# build\CellLab-<version>-win64-setup.exe. -NoPackage stops after the self-tested executable.
param([switch]$SkipTests, [switch]$NoPackage)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Invoke-Native([string]$What, [scriptblock]$Command) {
    Write-Host "==> $What" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "==> Installing uv (Python package manager) for the current user" -ForegroundColor Cyan
    powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv installation failed - check the internet connection" }
}

Invoke-Native "Installing Python 3.12 and dependencies (first run downloads ~400 MB)" { uv sync --frozen }
if (-not $SkipTests) { Invoke-Native "Running tests" { uv run pytest -q } }
$version = (uv run python -c "import cellab; print(cellab.__version__)").Trim()

Invoke-Native "Writing licence notices" { uv run python scripts/gen_notices.py }
Invoke-Native "Building CellLab.exe (PyInstaller)" {
    uv run pyinstaller packaging/cellab.spec --noconfirm --distpath build/dist --workpath build/work
}
Copy-Item THIRD_PARTY_NOTICES.md, README.md, docs\USER_MANUAL.md build\dist\CellLab\

Write-Host "==> Self-testing the packaged application" -ForegroundColor Cyan
$report = Join-Path (Get-Location) "build\self_test.json"
Remove-Item $report -ErrorAction SilentlyContinue
$p = Start-Process -FilePath "build\dist\CellLab\CellLab.exe" -ArgumentList "--self-test", "--report", "`"$report`"" -Wait -PassThru
Get-Content $report -ErrorAction SilentlyContinue
if ($p.ExitCode -ne 0) { throw "packaged self-test failed (exit $($p.ExitCode))" }
Write-Host "Executable: build\dist\CellLab\CellLab.exe" -ForegroundColor Green
if ($NoPackage) { return }

$zip = "build\CellLab-$version-win64-portable.zip"
Compress-Archive -Path build\dist\CellLab -DestinationPath $zip -Force
Write-Host "Portable build: $zip"

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (Test-Path $iscc) {
    Invoke-Native "Building the installer (Inno Setup)" { & $iscc "/DAppVersion=$version" packaging\installer.iss }
} else {
    Write-Warning "Inno Setup 6 not found - skipped the installer (https://jrsoftware.org/isinfo.php)"
}
