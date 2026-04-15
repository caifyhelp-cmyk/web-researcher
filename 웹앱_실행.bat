@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
echo [browser] > "%USERPROFILE%\.streamlit\config.toml"
echo gatherUsageStats = false >> "%USERPROFILE%\.streamlit\config.toml"
echo.
echo  웹 리서치 어시스턴트 시작 중...
echo  브라우저가 자동으로 열립니다. (5-10초)
echo  이 창을 닫으면 앱이 종료됩니다.
echo.
"C:\Users\조경일\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m streamlit run app.py --server.headless false --server.port 8501 --browser.gatherUsageStats false
pause