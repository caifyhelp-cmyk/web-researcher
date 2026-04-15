; 웹 리서치 어시스턴트 — Inno Setup 설치 스크립트
; 컴파일: build_installer.bat 실행 or Inno Setup IDE에서 setup.iss 열고 Build

#define AppName "웹 리서치 어시스턴트"
#define AppVersion "1.0"
#define AppPublisher "caify.ai"
#define AppExeName "launcher.bat"

[Setup]
AppId={{A7F2E3B1-9C4D-4E5F-8A6B-3D2C1E0F9A7B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\WebResearcher
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=웹리서치어시스턴트_설치
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
WizardResizable=no
ShowLanguageDialog=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checked

[Files]
; 앱 소스
Source: "..\app.py";            DestDir: "{app}"; Flags: ignoreversion
Source: "..\web_researcher.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\_local_keys.py";    DestDir: "{app}"; Flags: ignoreversion
; 런처
Source: "launcher.bat";         DestDir: "{app}"; Flags: ignoreversion
; 패키지 설치 스크립트
Source: "install_packages.bat"; DestDir: "{app}"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{userdesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"

[Run]
; 패키지 설치
Filename: "cmd.exe"; \
    Parameters: "/c ""{app}\install_packages.bat"""; \
    WorkingDir: "{app}"; \
    StatusMsg: "Python 패키지 설치 중... (1~3분 소요)"; \
    Flags: waituntilterminated runhidden

; 설치 완료 후 바로 실행 (선택)
Filename: "{app}\{#AppExeName}"; \
    Description: "지금 바로 실행하기"; \
    WorkingDir: "{app}"; \
    Flags: nowait postinstall skipifsilent shellexec

[Code]
function IsPythonInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsPythonInstalled() then
  begin
    if MsgBox(
      '⚠️  Python이 설치되어 있지 않습니다.' + #13#10 + #13#10 +
      'python.org 에서 Python 3.9 이상을 설치한 후 다시 실행해주세요.' + #13#10 + #13#10 +
      '지금 python.org를 열까요?',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
    end;
    Result := False;
  end;
end;
