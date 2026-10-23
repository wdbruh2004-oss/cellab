# Build CellLab for Windows (run from any directory in PowerShell 5+ or pwsh):
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 [-SkipTests]
# Produces build\CellLab-<version>-win64-portable.zip and, when Inno Setup 6 is installed,
# build\CellLab-<version>-win64-setup.exe. The packaged app must pass its own self-test.
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found - installing it for the current user"
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

uv sync --frozen
if (-not $SkipTests) { uv run pytest -q; if ($LASTEXITCODE -ne 0) { throw "tests failed" } }
$version = (uv run python -c "import cellab; print(cellab.__version__)").Trim()

uv run python scripts/gen_notices.py
uv run pyinstaller packaging/cellab.spec --noconfirm --distpath build/dist --workpath build/work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Copy-Item THIRD_PARTY_NOTICES.md, README.md, docs\USER_MANUAL.md build\dist\CellLab\

$report = Join-Path (Get-Location) "build\self_test.json"
$p = Start-Process -FilePath "build\dist\CellLab\CellLab.exe" -ArgumentList "--self-test", "--report", "`"$report`"" -Wait -PassThru
Get-Content $report -ErrorAction SilentlyContinue
if ($p.ExitCode -ne 0) { throw "packaged self-test failed (exit $($p.ExitCode))" }

$zip = "build\CellLab-$version-win64-portable.zip"
Compress-Archive -Path build\dist\CellLab -DestinationPath $zip -Force
Write-Host "Portable build: $zip"

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (Test-Path $iscc) {
    & $iscc "/DAppVersion=$version" packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
} else {
    Write-Warning "Inno Setup 6 not found - skipped the installer (https://jrsoftware.org/isinfo.php)"
}
