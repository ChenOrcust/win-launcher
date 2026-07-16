; WinLauncher Inno Setup Installer Script
; Requires Inno Setup (https://jrsoftware.org/isdl.php)

#define MyAppName "WinLauncher"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "WinLauncher"
#define MyAppURL ""
#define MyAppExeName "WinLauncher.exe"

[Setup]
AppId={{B8F4A3D2-5E7C-4A1B-9D6F-2C3E8A0B4F1D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=WinLauncher_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startup"; Description: "&Start with Windows (add to startup)"; GroupDescription: "Startup options:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C ""taskkill /f /im {#MyAppExeName} 2>nul"""; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Add to startup via registry if task selected
    if WizardIsTaskSelected('startup') then
    begin
      SaveStringToFile(ExpandConstant('{userstartup}\WinLauncher.url'),
        '[InternetShortcut]' + #13#10 +
        'URL=file:///' + ExpandConstant('{app}\WinLauncher.exe') + #13#10 +
        'IconIndex=0' + #13#10 +
        'IconFile=' + ExpandConstant('{app}\WinLauncher.exe'),
        False);
    end;
  end;
end;
