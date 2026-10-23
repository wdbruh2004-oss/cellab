# One-click CellLab setup for Windows, started by SETUP_CellLab.bat in the project root.
# Builds and self-tests CellLab.exe, installs it to %LOCALAPPDATA%\Programs\CellLab,
# creates a desktop shortcut and starts the application.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host ""
Write-Host "CellLab setup - the first run needs internet and takes about 5-15 minutes." -ForegroundColor Green
Write-Host "Afterwards CellLab runs completely offline." -ForegroundColor Green
Write-Host ""

& "$PSScriptRoot\build_windows.ps1" -SkipTests -NoPackage

$src = Join-Path (Get-Location) "build\dist\CellLab"
$dest = Join-Path $env:LOCALAPPDATA "Programs\CellLab"
Write-Host "==> Installing to $dest" -ForegroundColor Cyan
Get-Process CellLab -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
Copy-Item $src $dest -Recurse

$exe = Join-Path $dest "CellLab.exe"
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @($desktop, (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
    $lnk = $shell.CreateShortcut((Join-Path $folder "CellLab.lnk"))
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $dest
    $lnk.IconLocation = "$exe,0"
    $lnk.Description = "CellLab - offline 3D cellular laboratory"
    $lnk.Save()
}
Write-Host ""
Write-Host "Done. CellLab is on your desktop and in the Start menu." -ForegroundColor Green
Start-Process $exe
