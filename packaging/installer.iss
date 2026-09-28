; Inno Setup script for Codex Account Manager.
; Build the PyInstaller bundle first (see packaging/README.md), then compile:
;   iscc packaging/installer.iss
;
; Produces installer/Output/CodexAccountManager-Setup-x.y.z.exe
; User-level install (no admin required), Start Menu shortcut, optional
; start-with-Windows, and an uninstaller.

#define AppName "Codex Account Manager"
#define AppVersion "0.1.0"
#define AppExe "CodexAccountManager.exe"
#define AppPublisher "Codex Account Manager contributors"
#ifndef BundleRoot
  #define BundleRoot "..\dist"
#endif

[Setup]
SetupIconFile=assets\app.ico
AppId={{7C2E5F3A-1D2B-4E6A-9C11-590DBC049B83}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={userpf}\CodexAccountManager
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=CodexAccountManager-Setup-{#AppVersion}
OutputDir=..\installer\Output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
english.StartOnLogin=Start Codex Account Manager when I log in
turkish.StartOnLogin=Windows oturumu açıldığında Codex Hesap Yöneticisi başlasın
english.DesktopShortcut=Create a desktop shortcut
turkish.DesktopShortcut=Masaüstü kısayolu oluştur
english.LaunchApp=Launch Codex Account Manager
turkish.LaunchApp=Codex Hesap Yöneticisi uygulamasını aç
english.UninstallApp=Uninstall Codex Account Manager
turkish.UninstallApp=Codex Hesap Yöneticisi uygulamasını kaldır

[Tasks]
Name: "startupicon"; Description: "{cm:StartOnLogin}"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; Flags: unchecked

[Files]
; Copy the entire PyInstaller COLLECT output for the GUI app.
Source: "{#BundleRoot}\CodexAccountManager\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Include the console CLI alongside it.
Source: "{#BundleRoot}\cx\*"; DestDir: "{app}\cli"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "CodexAccountManager.Desktop"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "CodexAccountManager.Desktop"; Tasks: desktopicon
Name: "{group}\{cm:UninstallApp}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CodexAccountManager"; ValueData: """{app}\{#AppExe}"""; Tasks: startupicon; Flags: uninsdeletevalue
