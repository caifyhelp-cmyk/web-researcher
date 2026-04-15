@echo off
chcp 65001 > nul
echo.
echo ╔══════════════════════════════════════════╗
echo ║    웹 리서치 어시스턴트 — 설치파일 빌드   ║
echo ╚══════════════════════════════════════════╝
echo.

:: dist 폴더
if not exist "..\dist" mkdir "..\dist"

:: ── 1. Inno Setup 확인 ──────────────────────
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if not %ISCC%=="" goto :BUILD

:: ── 2. Inno Setup 없으면 자동 다운로드 + 설치 ──
echo  Inno Setup 6이 없습니다. 자동으로 다운로드합니다...
echo  (약 5MB, 30초 정도 소요)
echo.

set INNO_INSTALLER=%TEMP%\innosetup6.exe
powershell -NoProfile -Command ^
    "Invoke-WebRequest 'https://files.jrsoftware.org/is/6/innosetup-6.3.3.exe' -OutFile '%INNO_INSTALLER%' -UseBasicParsing"

if not exist "%INNO_INSTALLER%" (
    echo  [오류] 다운로드 실패. 인터넷 연결을 확인하거나
    echo  https://jrsoftware.org/isdl.php 에서 직접 설치 후 다시 실행하세요.
    pause
    exit /b 1
)

echo  Inno Setup 설치 중...
"%INNO_INSTALLER%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
del "%INNO_INSTALLER%"

:: 재확인
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if %ISCC%=="" (
    echo  [오류] Inno Setup 설치에 실패했습니다.
    pause
    exit /b 1
)
echo  Inno Setup 설치 완료.
echo.

:: ── 3. 컴파일 ──────────────────────────────
:BUILD
echo  EXE 설치파일 빌드 중...
%ISCC% "%~dp0setup.iss"

if %errorlevel% equ 0 (
    echo.
    echo ✅ 완료!
    echo    dist\웹리서치어시스턴트_설치.exe 가 생성됐습니다.
    echo    이 EXE를 배포하면 됩니다.
    echo.
    explorer "%~dp0..\dist"
) else (
    echo.
    echo ❌ 빌드 실패. 위 오류를 확인하세요.
    echo.
)
pause
