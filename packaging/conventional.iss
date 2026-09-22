; Conventional installer; shares the guided configuration with the BAT edition.
#define AppName "TVPaint Layer Exporter"
[Setup]
AppId={{AABEE845-6716-45CF-A26A-9222A2F3808A}
AppName={#AppName}
AppVersion=2.0.0
AppPublisher=Fabien Glasse
SetupIconFile=..\portable_exporter\TVPaint_Exporter_Logo.ico
UninstallDisplayIcon={app}\TVPaint_Exporter_Logo.ico
DefaultDirName={localappdata}\TVPaintLayerExporter
DisableDirPage=yes
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Compression=zip
SolidCompression=no
OutputDir=..\dist\conventional
OutputBaseFilename=TVPaintLayerExporterSetup
UninstallDisplayName={#AppName}
SetupLogging=yes
CloseApplications=yes

[Files]
Source: "Install.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "setup_steps.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\portable_exporter\export_layers.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\portable_exporter\export_options.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\portable_exporter\exporter_ui.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "Uninstall.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "component_cleanup.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\portable_exporter\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\portable_exporter\TVPaint_Exporter_Logo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\portable_exporter\TVPaint_Exporter_Logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "User Guide.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "Freelancer Guide.pdf"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}\Configure exporter"; Filename: "{app}\Install.bat"; IconFilename: "{app}\TVPaint_Exporter_Logo.ico"
Name: "{autoprograms}\{#AppName}\Instructions"; Filename: "{app}\Freelancer Guide.pdf"
Name: "{autoprograms}\{#AppName}\Uninstall"; Filename: "{uninstallexe}"

[Run]
Filename: "{cmd}"; Parameters: "/D /C """"{app}\Install.bat"""""; Description: "Configure Python and TVPaint now (asks before each step)"; Flags: postinstall shellexec skipifsilent

[Registry]
; Replace a previous BAT uninstall registration with this installer's entry.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\TVPaintLayerExporter"; Flags: deletekey

[UninstallDelete]
Type: files; Name: "{autodesktop}\TVPaint Layer Exporter.lnk"
Type: filesandordirs; Name: "{app}\venv"
Type: files; Name: "{app}\downloads\tvpaint-rpc-1.1.0-tvp-11.dll"
Type: files; Name: "{app}\downloads\tvpaint-rpc-1.2.0-tvp-12.1.zip"
Type: files; Name: "{app}\settings.json"
Type: files; Name: "{app}\settings.tmp"
Type: files; Name: "{app}\installation.json"
Type: files; Name: "{app}\python_path.txt"
Type: files; Name: "{app}\setup.log"
; Shared components are handled by the explicit choices below, never wildcards.

[Code]
function CleanupPython(Param: String): String;
var
  Path: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(ExpandConstant('{app}\python_path.txt'), Path) then
    Result := Trim(UTF8Decode(Path));
  if FileExists(ExtractFileDir(Result) + '\pythonw.exe') then
    Result := ExtractFileDir(Result) + '\pythonw.exe';
end;

function CanOfferComponentCleanup: Boolean;
begin
  Result := (not UninstallSilent) and FileExists(CleanupPython('')) and FileExists(ExpandConstant('{app}\installation.json'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ExitCode: Integer;
begin
  if (CurUninstallStep = usUninstall) and CanOfferComponentCleanup then begin
    if not Exec(CleanupPython(''), '-I "' + ExpandConstant('{app}\uninstall.py') +
      '" --components-only --gui', ExpandConstant('{app}'), SW_SHOWNORMAL,
      ewWaitUntilTerminated, ExitCode) then
      MsgBox('Optional component removal could not start. Python and the TVPaint connection component will be kept.', mbInformation, MB_OK);
  end;
end;
