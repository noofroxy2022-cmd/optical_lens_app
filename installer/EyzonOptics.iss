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
; RUNNING-INSTANCE SAFETY (2026-09-23): layered, fail-closed, never kills.
;  1. AppMutex names the EXACT SAME named mutex EyzonOptics.exe itself holds
;     while running (release_runtime_guard.MUTEX_NAME) - an early notice for
;     mutex-aware builds, at Setup and Uninstall startup.
;  2. The [Code] gate (PrepareToInstall / InitializeUninstall) runs before any
;     file is replaced or removed. It enumerates EyzonOptics.exe candidates via
;     WMI Win32_Process and treats a process as the installed app ONLY if its
;     normalized ExecutablePath equals the normalized {app}\EyzonOptics.exe -
;     so it also sees pre-mutex (legacy) builds and the PyInstaller bootloader
;     before the mutex exists, while a same-named exe at any other path (e.g.
;     the unrelated old C:\Program Files\Eyzon Optics\EyzonOptics.exe) is
;     ignored. The mutex is an additional "still running" signal, never proof
;     of safety. If WMI cannot be queried, or a candidate's path cannot be
;     read, the gate BLOCKS (detection failure is never "not running").
;     Interactive: Retry/Cancel, Retry re-checks immediately. Silent: Setup
;     stops at Preparing to Install before touching any file.
;  3. CloseApplications (Restart Manager) stays as a backstop. Its filter is a
;     list of FILE NAME wildcards (Inno docs); Restart Manager itself always
;     checks the exact destination path {app}\EyzonOptics.exe.

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
CloseApplicationsFilter={#MyAppExeName}
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

[Code]
const
  EyzonRuntimeMutex = 'Local\EyzonOpticsRuntimeV1';
  GateSafe = 0;
  GateRunningApp = 1;
  GateDetectionFailure = 2;
  LongPathBufferSize = 1024;

function GetLongPathNameW(lpszShortPath: String; lpszLongPath: String; cchBuffer: Cardinal): Cardinal;
  external 'GetLongPathNameW@kernel32.dll stdcall';

{ Canonical form for comparing executable paths: unquoted, backslashes,
  no \\?\ prefix, absolute, 8.3 segments expanded (when the file exists),
  no trailing backslash, lower case. }
function NormalizeExePath(const Path: String): String;
var
  S, LongPath: String;
  Len: Cardinal;
begin
  S := Trim(Path);
  if (Length(S) >= 2) and (S[1] = '"') and (S[Length(S)] = '"') then
    S := Copy(S, 2, Length(S) - 2);
  StringChangeEx(S, '/', '\', True);
  if Pos('\\?\', S) = 1 then
    S := Copy(S, 5, Length(S) - 4);
  S := ExpandFileName(S);
  SetLength(LongPath, LongPathBufferSize);
  Len := GetLongPathNameW(S, LongPath, LongPathBufferSize);
  if (Len > 0) and (Len < LongPathBufferSize) then
    S := Copy(LongPath, 1, Len);
  Result := LowerCase(RemoveBackslashUnlessRoot(S));
end;

// Returns GateSafe only when the WMI scan completed, no process executes the
// installed app-dir EyzonOptics.exe, every candidate's path was verifiable,
// and the runtime mutex is absent. Never kills or signals any process.
function DetectInstalledRuntime(var Detail: String): Integer;
var
  Locator, Service, Items, Item, PathValue: Variant;
  Target, Candidate, Pid, Matches: String;
  I, Count: Integer;
  ScanOk, Unverifiable, MutexPresent: Boolean;
begin
  Target := NormalizeExePath(ExpandConstant('{app}\{#MyAppExeName}'));
  Log('EYZON_GATE target=' + Target);
  Matches := '';
  Unverifiable := False;
  ScanOk := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Items := Service.ExecQuery('SELECT ProcessId, ExecutablePath FROM Win32_Process WHERE Name = ''{#MyAppExeName}''');
    Count := Items.Count;
    for I := 0 to Count - 1 do
    begin
      Item := Items.ItemIndex(I);
      Pid := Item.ProcessId;
      PathValue := Item.ExecutablePath;
      if VarIsNull(PathValue) or VarIsEmpty(PathValue) then
        Candidate := ''
      else
        Candidate := PathValue;
      if Trim(Candidate) = '' then
      begin
        Unverifiable := True;
        Log('EYZON_GATE candidate pid=' + Pid + ' path=<unreadable>');
      end
      else if NormalizeExePath(Candidate) = Target then
      begin
        Matches := Matches + ' ' + Pid;
        Log('EYZON_GATE candidate pid=' + Pid + ' path=' + Candidate + ' => INSTALLED_APP');
      end
      else
        Log('EYZON_GATE candidate pid=' + Pid + ' path=' + Candidate + ' => ignored (different path)');
    end;
    ScanOk := True;
  except
    Detail := 'WMI process scan failed: ' + GetExceptionMessage;
  end;

  MutexPresent := CheckForMutexes(EyzonRuntimeMutex);
  if MutexPresent then
    Log('EYZON_GATE mutex=present')
  else
    Log('EYZON_GATE mutex=absent');

  if not ScanOk then
    Result := GateDetectionFailure
  else if Matches <> '' then
  begin
    Result := GateRunningApp;
    Detail := 'installed EyzonOptics.exe running, pid(s)' + Matches;
  end
  else if Unverifiable then
  begin
    Result := GateDetectionFailure;
    Detail := 'an EyzonOptics.exe process path could not be verified';
  end
  else if MutexPresent then
  begin
    Result := GateRunningApp;
    Detail := 'Eyzon Optics runtime mutex present';
  end
  else
    Result := GateSafe;
end;

{ Fail-closed gate. Returns '' only when SAFE_TO_REPLACE is proven; otherwise
  the reason, after which the caller must not touch any file. }
function EyzonRuntimeGate(const Silent: Boolean; const Action: String): String;
var
  State: Integer;
  Detail, Msg: String;
begin
  repeat
    Detail := '';
    State := DetectInstalledRuntime(Detail);
    if State = GateSafe then
    begin
      Log('EYZON_GATE result=SAFE_TO_REPLACE');
      Result := '';
      Exit;
    end;

    if State = GateRunningApp then
    begin
      Log('EYZON_GATE result=RUNNING_APP ' + Detail);
      Msg := 'Eyzon Optics is currently running.' + #13#10#13#10 +
        'Close Eyzon Optics, then click Retry to continue the ' + Action + '.';
      Result := 'Eyzon Optics is currently running. Close Eyzon Optics and run ' +
        'Setup again. No files were changed. [EYZON_GATE: RUNNING_APP]';
    end
    else
    begin
      Log('EYZON_GATE result=DETECTION_FAILURE ' + Detail);
      Msg := 'Setup could not verify that Eyzon Optics is closed.' + #13#10 +
        Detail + #13#10#13#10 + 'No files have been changed. Click Retry to ' +
        'check again, or Cancel to stop the ' + Action + '.';
      Result := 'Setup could not verify that Eyzon Optics is closed (' + Detail +
        '). No files were changed. [EYZON_GATE: DETECTION_FAILURE]';
    end;

    if Silent then
      Exit;
    if MsgBox(Msg, mbError, MB_RETRYCANCEL) <> IDRETRY then
    begin
      Log('EYZON_GATE user chose Cancel');
      Exit;
    end;
    Log('EYZON_GATE user chose Retry - re-checking');
  until False;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  NeedsRestart := False;
  Result := EyzonRuntimeGate(WizardSilent, 'upgrade');
end;

function InitializeUninstall(): Boolean;
begin
  Result := EyzonRuntimeGate(UninstallSilent, 'uninstall') = '';
end;
