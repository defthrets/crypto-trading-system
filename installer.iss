[Setup]
AppName=0xrex
AppVersion=1.0.0
AppPublisher=0xrex
AppPublisherURL=https://0xrex.one
DefaultDirName={autopf}\0xrex
DefaultGroupName=0xrex
OutputDir=dist
OutputBaseFilename=0xrex-windows-setup
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayName=0xrex
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
WizardStyle=modern
WizardSizePercent=120

[Files]
Source: "dist\0xrex\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\0xrex"; Filename: "{app}\0xrex.exe"
Name: "{autodesktop}\0xrex"; Filename: "{app}\0xrex.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\0xrex.exe"; Description: "Launch 0xrex"; Flags: nowait postinstall skipifsilent
