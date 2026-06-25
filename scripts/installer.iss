; QuickLauncher Installer Script
#ifndef MyAppName
  #define MyAppName "QuickLauncher"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "1.6.3.7"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "Layton"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "QuickLauncher.exe"
#endif
#ifndef MyAppFileVersion
  #define MyAppFileVersion "1.6.3.7"
#endif
#ifndef OutputBaseFilename
  #define OutputBaseFilename "QuickLauncher_Setup_" + MyAppVersion
#endif

[Setup]
AppId={{4F6C9B2A-55B0-4CB9-9AC9-0798A02A7D88}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppFileVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCopyright=Copyright (C) {#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
UsePreviousAppDir=yes
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\_inno_setup
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMADictionarySize=65536
LZMANumFastBytes=273
PrivilegesRequired=admin
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; Flags: unchecked
Name: "startupicon"; Description: "Start with Windows"; Flags: unchecked

[Files]
Source: "..\dist\QuickLauncher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "icons\*,icons\*.*,config\*.log,config\*.log.*,temp_icons\favicons\*,temp_icons\favicons\*.*"
; VC++ Redistributable package (if needed)
; Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Dirs]
Name: "{app}\config"; Permissions: users-modify
Name: "{app}\icons"; Permissions: users-modify
Name: "{app}\temp_icons"; Permissions: users-modify
Name: "{app}\temp_icons\favicons"; Permissions: users-modify
Name: "{app}\plugins"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; Registry method removed, using helper + Task Scheduler

[Run]
; Configure autostart (if startup task is checked)
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Parameters: "--configure-autostart enable --target-exe ""{app}\{#MyAppExeName}"" --target-cwd ""{app}"""; StatusMsg: "Configuring startup task..."; Flags: runasoriginaluser runhidden waituntilterminated; Tasks: startupicon

; Launch application after install
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "Launch QuickLauncher"; Flags: runasoriginaluser nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Parameters: "--autostart-helper disable --target-exe ""{app}\{#MyAppExeName}"" --target-cwd ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "UninstallAutoStart"

[Code]
procedure StopServiceIfRunning();
var
  ResultCode: Integer;
begin
  // Stop service if running
  Exec('net', 'stop QuickLauncherService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
end;

function IsQuickLauncherRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Exec(
    ExpandConstant('{cmd}'),
    '/c tasklist /FI "IMAGENAME eq {#MyAppExeName}" | find /I "{#MyAppExeName}" >nul',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Result := (ResultCode = 0);
end;

function WaitForQuickLauncherExit(TimeoutMs: Integer): Boolean;
var
  ElapsedMs: Integer;
begin
  ElapsedMs := 0;
  while (ElapsedMs < TimeoutMs) and IsQuickLauncherRunning() do
  begin
    Sleep(250);
    ElapsedMs := ElapsedMs + 250;
  end;

  Result := not IsQuickLauncherRunning();
end;

procedure KillRunningProcesses();
var
  ResultCode: Integer;
begin
  // Stop QuickLauncher itself only. Never use taskkill /T here: applications
  // launched by QuickLauncher have an independent lifetime and must survive
  // upgrades or reinstalls.
  if not IsQuickLauncherRunning() then
    Exit;

  Exec(ExpandConstant('{cmd}'), '/c taskkill /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if WaitForQuickLauncherExit(3000) then
  begin
    Sleep(400);
    Exit;
  end;

  Exec(ExpandConstant('{cmd}'), '/c taskkill /F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  WaitForQuickLauncherExit(5000);
  Sleep(800);
end;

procedure CleanOldVersionFiles();
var
  FindRec: TFindRec;
  FilePath: String;
  InstallDir: String;
  OldContextMenusDir: String;
begin
  InstallDir := ExpandConstant('{app}');

  if not DirExists(InstallDir) then
    Exit;

  Log('Cleaning old version files: ' + InstallDir);

  // Clean old config\ContextMenus directory
  OldContextMenusDir := InstallDir + '\config\ContextMenus';
  if DirExists(OldContextMenusDir) then
  begin
    Log('Cleaning old ContextMenus: ' + OldContextMenusDir);
    DelTree(OldContextMenusDir, True, True, True);
  end;

  if FindFirst(InstallDir + '\*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') and
           (FindRec.Name <> 'config') and (FindRec.Name <> 'assets') and (FindRec.Name <> 'icons') and
           (FindRec.Name <> 'temp_icons') and (FindRec.Name <> 'plugins') and
           (FindRec.Name <> '.plugins') then
        begin
          FilePath := InstallDir + '\' + FindRec.Name;

          if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY = FILE_ATTRIBUTE_DIRECTORY then
            DelTree(FilePath, True, True, True)
          else
            DeleteFile(FilePath);

          Log('Deleted: ' + FilePath);
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function CopyDirectory(SourceDir, DestDir: String): Boolean;
var
  FindRec: TFindRec;
  SourcePath, DestPath: String;
begin
  Result := True;
  if FindFirst(SourceDir + '\*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          SourcePath := SourceDir + '\' + FindRec.Name;
          DestPath := DestDir + '\' + FindRec.Name;

          if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY = FILE_ATTRIBUTE_DIRECTORY then
          begin
            ForceDirectories(DestPath);
            if CopyDirectory(SourcePath, DestPath) then
              DelTree(SourcePath, True, True, True)
            else
              Result := False;
          end
          else
          begin
            if CopyFile(SourcePath, DestPath, False) then
              DeleteFile(SourcePath)
            else
            begin
              Log('Failed to migrate file: ' + SourcePath);
              Result := False;
            end;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

procedure MigrateConfigFromAppData();
var
  OldConfigDir, NewConfigDir: String;
begin
  OldConfigDir := ExpandConstant('{userappdata}\QuickLauncher');
  NewConfigDir := ExpandConstant('{app}\config');

  if DirExists(OldConfigDir) then
  begin
    Log('Old config detected, migrating...');
    ForceDirectories(NewConfigDir);
    if CopyDirectory(OldConfigDir, NewConfigDir) then
    begin
      RemoveDir(OldConfigDir);
      Log('Config migration complete');
    end
    else
      Log('Config migration incomplete; source files were preserved');
  end;
end;

function CheckVCRedist(): Boolean;
var
  VCRedistInstalled: Boolean;
  SystemPath: String;
  MissingDlls: String;
  DllsToCheck: array[0..6] of String;
  I: Integer;
  DllPath: String;
  ErrorCode: Integer;
begin
  Result := True;
  VCRedistInstalled := True;
  MissingDlls := '';

  // Required DLL list
  DllsToCheck[0] := 'msvcp140.dll';
  DllsToCheck[1] := 'vcruntime140.dll';
  DllsToCheck[2] := 'vcruntime140_1.dll';
  DllsToCheck[3] := 'msvcp140_1.dll';
  DllsToCheck[4] := 'msvcp140_2.dll';
  DllsToCheck[5] := 'concrt140.dll';
  DllsToCheck[6] := 'vcomp140.dll';

  // Check System32 directory
  SystemPath := ExpandConstant('{sys}');

  for I := 0 to 6 do
  begin
    DllPath := SystemPath + '\' + DllsToCheck[I];
    if not FileExists(DllPath) then
    begin
      VCRedistInstalled := False;
      if MissingDlls <> '' then
        MissingDlls := MissingDlls + ', ';
      MissingDlls := MissingDlls + DllsToCheck[I];
      Log('Missing DLL: ' + DllsToCheck[I]);
    end;
  end;

  // Prompt user if not installed
  if not VCRedistInstalled then
  begin
    Log('Missing DLLs detected: ' + MissingDlls);

    if MsgBox('Missing required runtime components (Microsoft Visual C++ Redistributable).' + #13#10 + #13#10 +
              'Missing files: ' + MissingDlls + #13#10 + #13#10 +
              'These components are required for the application to run properly.' + #13#10 + #13#10 +
              'Download and install now?' + #13#10 + #13#10 +
              '(If you choose "No", installation will continue but the application may not start)',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      // Open download page
      ShellExec('open', 'https://aka.ms/vs/17/release/vc_redist.x64.exe', '', '', SW_SHOW, ewNoWait, ErrorCode);
      MsgBox('Please download and install VC++ Redistributable, then re-run the QuickLauncher installer.', mbInformation, MB_OK);
      Result := False;
    end;
  end
  else
  begin
    Log('VC++ Redistributable is installed');
  end;
end;

function InitializeSetup(): Boolean;
begin
  // Stop service and processes before installation
  StopServiceIfRunning();
  KillRunningProcesses();

  // Check VC++ Redistributable
  Result := CheckVCRedist();
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PrevInstallDir: String;
  CurrentInstallDir: String;
begin
  if CurStep = ssInstall then
  begin
    // Check if upgrading to the same path
    PrevInstallDir := '';
    if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4F6C9B2A-55B0-4CB9-9AC9-0798A02A7D88}_is1', 'InstallLocation', PrevInstallDir) or
       RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4F6C9B2A-55B0-4CB9-9AC9-0798A02A7D88}_is1', 'InstallLocation', PrevInstallDir) then
    begin
      CurrentInstallDir := ExpandConstant('{app}');
      if CompareText(RemoveBackslashUnlessRoot(PrevInstallDir), RemoveBackslashUnlessRoot(CurrentInstallDir)) = 0 then
      begin
        Log('Same-path upgrade detected, cleaning old version files');
        CleanOldVersionFiles();
      end
      else
        Log('Install path changed, skipping cleanup');
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    // Migrate config after installation
    MigrateConfigFromAppData();
  end;
end;
