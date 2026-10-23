; Inno Setup 6 script. Built by packaging\build_windows.ps1 after the PyInstaller step.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{8F6C1E2A-6C55-4C59-9C0E-3B2D7A1C4E10}
AppName=CellLab
AppVersion={#AppVersion}
AppPublisher=CellLab project
DefaultDirName={autopf}\CellLab
DefaultGroupName=CellLab
OutputDir=..\build
OutputBaseFilename=CellLab-{#AppVersion}-win64-setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=cellab.ico
UninstallDisplayIcon={app}\CellLab.exe
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\dist\CellLab\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\CellLab"; Filename: "{app}\CellLab.exe"
Name: "{group}\Uninstall CellLab"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CellLab"; Filename: "{app}\CellLab.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CellLab.exe"; Description: "{cm:LaunchProgram,CellLab}"; Flags: nowait postinstall skipifsilent
