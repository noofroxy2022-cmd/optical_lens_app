; Eyzon Optics - Windows Setup
;
; Packages the already-approved, already-tested standalone release folder
; (release\EyzonOptics.exe, release\release_runtime.db) together with the
; tracked launcher source (installer\"Start Eyzon Optics.cmd") into a
; normal Windows installer.
;
; Installs per-user (no admin required) so the app can write its own
; database, backups, and uploads at runtime without hitting Program Files
; permission restrictions.
;
; DATABASE SAFETY: release_runtime.db is installed with "onlyifdoesntexist",
; so a reinstall/upgrade NEVER overwrites an existing operational database -
; only a fresh install (where no DB is present yet) copies the approved one.
; It also carries "uninsneveruninstall" so uninstalling the app never
; deletes the user's live business data.
;
; RUNNING-INSTANCE SAFETY (2026-09-22): AppMutex names the EXACT SAME named
; mutex EyzonOptics.exe itself holds while running (release_runtime_guard.
; MUTEX_NAME) - Setup detects a running current-version instance by that
; precise identity and asks the user to close it before continuing.
; CloseApplications (Restart Manager) is a complementary, file-level safety
; net scoped by CloseApplicationsFilter to ONLY this app's own installed exe
; path - it can never match, and therefore can never close, the unrelated
; old 1.4.5 executable at a completely different path (C:\Program Files\
; Eyzon Optics\EyzonOptics.exe). Neither mechanism ever force-kills by bare
; process name.

#define MyAppName "Eyzon Optics"
#define MyAppVersion "1.5.0"
#define MyAppExeName "EyzonOptics.exe"
#define MyLauncherName "Start Eyzon Optics.cmd"
#define ReleaseDir "..\release"

[Setup]
AppId={{6C7B7F0E-6C64-4B7B-9C63-8E9E9C6E1A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={userappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..
OutputBaseFilename=Eyzon-Optics-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
AppMutex=Local\EyzonOpticsRuntimeV1
CloseApplications=yes
CloseApplicationsFilter={app}\{#MyAppExeName}
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#ReleaseDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyLauncherName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\release_runtime.db"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyLauncherName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyLauncherName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyLauncherName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
