#define MyAppName "Adaptation Compiler"
#define MyAppVersion "0.2.0-alpha.1"
#define MyAppPublisher "Adaptation Compiler"
#define MyAppExeName "AdaptationCompiler.exe"

[Setup]
AppId={{E8148709-EB33-4BDA-A53E-615D5B0BC312}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Adaptation Compiler
DefaultGroupName=Adaptation Compiler
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
OutputBaseFilename=AdaptationCompiler-{#MyAppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\..\dist\AdaptationCompiler.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Adaptation Compiler"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Adaptation Compiler"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Adaptation Compiler"; Flags: nowait postinstall skipifsilent
