@echo off
chcp 65001 > nul
echo.
echo  Inno Setup 컴파일러 찾는 중...

:: dist 폴더 생성
if not exist "..\dist" mkdir "..\dist"

:: Inno Setup 경로 후보
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if %ISCC%=="" (
    echo.
    echo  [오류] Inno Setup 6이 설치되어 있지 않습니다.
    echo  https://jrsoftware.org/isdl.php 에서 설치 후 다시 실행하세요.
    echo.
    pause
    exit /b 1
)

echo  컴파일 시작...
%ISCC% setup.iss

if %errorlevel% equ 0 (
    echo.
    echo  ✅ 완료! dist\웹리서치어시스턴트_설치.exe 생성됨
    echo.
    explorer "..\dist"
) else (
    echo.
    echo  ❌ 컴파일 실패. 위 오류 메시지를 확인하세요.
    echo.
)
pause
