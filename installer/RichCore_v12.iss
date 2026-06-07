#define MyAppName "RichCore"
#define MyAppExeName "RichCore_v12.exe"
#define MyAppVersion "1.0.7"

[Setup]
AppId={{8C558550-8E2C-4FC7-B16D-8A5D9D7E2E17}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=RichCore
AppPublisherURL=https://github.com/OlekseiyKolovanov/RichCore
AppSupportURL=https://github.com/OlekseiyKolovanov/RichCore/issues
AppUpdatesURL=https://github.com/OlekseiyKolovanov/RichCore/releases
DefaultDirName={autopf}\RichCore
DefaultGroupName=RichCore
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=RichCore_v12_Setup
SetupIconFile=..\assets\iconka.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartIfNeededByRun=no
VersionInfoCompany=RichCore
VersionInfoDescription=RichCore installer
VersionInfoProductName=RichCore
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столі"; GroupDescription: "Ярлики:"; Flags: unchecked

[Files]
Source: "..\dist\RichCore_v12\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config\*,logs\*"

[Icons]
Name: "{group}\RichCore"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\RichCore"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустити RichCore"; Flags: nowait postinstall skipifsilent
