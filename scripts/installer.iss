; QuickLauncher 安装程序脚本
#ifndef MyAppName
  #define MyAppName "QuickLauncher"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "1.6.2.0"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "Layton"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "QuickLauncher.exe"
#endif
#ifndef MyAppFileVersion
  #define MyAppFileVersion "1.6.2.0"
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
Source: "..\dist\QuickLauncher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config\*.log,config\*.log.*,temp_icons\favicons\*,temp_icons\favicons\*.*"
; VC++ Redistributable 安装包（如果需要的话）
; Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Dirs]
Name: "{app}\config"; Permissions: users-modify
Name: "{app}\icons"; Permissions: users-modify
Name: "{app}\temp_icons"; Permissions: users-modify
Name: "{app}\temp_icons\favicons"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; 不再使用注册表方式，改用 helper + Task Scheduler

[Run]
; 配置开机自启（如果勾选了开机自启）
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
  // 停止服务（如果正在运行）
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
  // 强制关闭所有 QuickLauncher 进程 (使用 cmd 调用 taskkill 避免环境变量路径引发的问题)
  if not IsQuickLauncherRunning() then
    Exit;

  Exec(ExpandConstant('{cmd}'), '/c taskkill /IM {#MyAppExeName} /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if WaitForQuickLauncherExit(3000) then
  begin
    Sleep(400);
    Exit;
  end;

  Exec(ExpandConstant('{cmd}'), '/c taskkill /F /IM {#MyAppExeName} /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
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

  Log('清理旧版本文件: ' + InstallDir);

  // 清理旧版本的 config\ContextMenus 目录
  OldContextMenusDir := InstallDir + '\config\ContextMenus';
  if DirExists(OldContextMenusDir) then
  begin
    Log('清理旧版本 ContextMenus: ' + OldContextMenusDir);
    DelTree(OldContextMenusDir, True, True, True);
  end;

  if FindFirst(InstallDir + '\*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') and
           (FindRec.Name <> 'config') and (FindRec.Name <> 'assets') and (FindRec.Name <> 'icons') and
           (FindRec.Name <> 'temp_icons') and (FindRec.Name <> 'plugins') then
        begin
          FilePath := InstallDir + '\' + FindRec.Name;

          if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY = FILE_ATTRIBUTE_DIRECTORY then
            DelTree(FilePath, True, True, True)
          else
            DeleteFile(FilePath);

          Log('已删除: ' + FilePath);
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

procedure CopyDirectory(SourceDir, DestDir: String);
var
  FindRec: TFindRec;
  SourcePath, DestPath: String;
begin
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
            CopyDirectory(SourcePath, DestPath);
            DelTree(SourcePath, True, True, True);
          end
          else
          begin
            CopyFile(SourcePath, DestPath, False);
            DeleteFile(SourcePath);
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
    Log('检测到旧配置，开始迁移...');
    ForceDirectories(NewConfigDir);
    CopyDirectory(OldConfigDir, NewConfigDir);
    RemoveDir(OldConfigDir);
    Log('配置迁移完成');
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

  // 需要检测的 DLL 列表
  DllsToCheck[0] := 'msvcp140.dll';
  DllsToCheck[1] := 'vcruntime140.dll';
  DllsToCheck[2] := 'vcruntime140_1.dll';
  DllsToCheck[3] := 'msvcp140_1.dll';
  DllsToCheck[4] := 'msvcp140_2.dll';
  DllsToCheck[5] := 'concrt140.dll';
  DllsToCheck[6] := 'vcomp140.dll';

  // 检查 System32 目录
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
      Log('缺少 DLL: ' + DllsToCheck[I]);
    end;
  end;

  // 如果未安装，提示用户
  if not VCRedistInstalled then
  begin
    Log('检测到缺少以下 DLL: ' + MissingDlls);

    if MsgBox('检测到系统缺少必需的运行时组件 (Microsoft Visual C++ Redistributable)。' + #13#10 + #13#10 +
              '缺少的文件: ' + MissingDlls + #13#10 + #13#10 +
              '程序需要这些组件才能正常运行。' + #13#10 + #13#10 +
              '是否现在下载并安装？' + #13#10 + #13#10 +
              '(如果选择"否"，安装将继续，但程序可能无法启动)',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      // 打开下载页面
      ShellExec('open', 'https://aka.ms/vs/17/release/vc_redist.x64.exe', '', '', SW_SHOW, ewNoWait, ErrorCode);
      MsgBox('请下载并安装 VC++ Redistributable 后，再继续安装 QuickLauncher。' + #13#10 + #13#10 +
             '安装完成后，请重新运行此安装程序。', mbInformation, MB_OK);
      Result := False;
    end;
  end
  else
  begin
    Log('检测到 VC++ Redistributable 已安装');
  end;
end;

function InitializeSetup(): Boolean;
begin
  // 安装前停止服务和进程
  StopServiceIfRunning();
  KillRunningProcesses();

  // 检查 VC++ Redistributable
  Result := CheckVCRedist();
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PrevInstallDir: String;
  CurrentInstallDir: String;
begin
  if CurStep = ssInstall then
  begin
    // 检查是否是同路径升级
    PrevInstallDir := '';
    if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4F6C9B2A-55B0-4CB9-9AC9-0798A02A7D88}_is1', 'InstallLocation', PrevInstallDir) or
       RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4F6C9B2A-55B0-4CB9-9AC9-0798A02A7D88}_is1', 'InstallLocation', PrevInstallDir) then
    begin
      CurrentInstallDir := ExpandConstant('{app}');
      if CompareText(RemoveBackslashUnlessRoot(PrevInstallDir), RemoveBackslashUnlessRoot(CurrentInstallDir)) = 0 then
      begin
        Log('检测到同路径升级，清理旧版本文件');
        CleanOldVersionFiles();
      end
      else
        Log('安装路径已更改，跳过清理');
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    // 安装完成后执行配置迁移
    MigrateConfigFromAppData();
  end;
end;
