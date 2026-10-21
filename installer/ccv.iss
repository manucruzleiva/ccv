; Inno Setup script for CCV (Capture Card Viewer).
;
; Built by CI (.github/workflows/release.yml) from the PyInstaller --onedir
; output. Local build, from the repo root, after `python ccv.py build --onedir`:
;
;   iscc /DAppVersion=0.8.0 installer\ccv.iss
;
; Per-user install (no admin / UAC): lands in %LOCALAPPDATA%\Programs\CCV.
; That is what lets the in-app updater run this setup silently over an
; existing install without an elevation prompt.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\ccv"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
; AppId must never change: it is how upgrades find the previous install.
AppId={{8F3B6C2E-5D41-4A7B-9E2C-1C0A7D3F4B21}
AppName=CCV - Capture Card Viewer
AppVersion={#AppVersion}
AppVerName=CCV {#AppVersion}
AppPublisher=manucruzleiva
AppPublisherURL=https://github.com/manucruzleiva/ccv
AppSupportURL=https://github.com/manucruzleiva/ccv/issues
AppUpdatesURL=https://github.com/manucruzleiva/ccv/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\CCV
DefaultGroupName=CCV
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=ccv-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\ccv.exe
UninstallDisplayName=CCV - Capture Card Viewer
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Drop the previous version's runtime so stale DLLs never linger after an upgrade.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CCV"; Filename: "{app}\ccv.exe"
Name: "{autodesktop}\CCV"; Filename: "{app}\ccv.exe"; Tasks: desktopicon

[Run]
; Silent installs (the in-app updater) skip this: the updater relaunches CCV itself.
Filename: "{app}\ccv.exe"; Description: "{cm:LaunchProgram,CCV}"; Flags: nowait postinstall skipifsilent
