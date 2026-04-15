@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo  웹 리서치 어시스턴트 시작 중...
echo  잠시 후 브라우저가 자동으로 열립니다.
echo  이 창을 닫으면 앱이 종료됩니다.
echo.

start "" http://localhost:8501

streamlit run app.py ^
    --server.headless false ^
    --server.port 8501 ^
    --browser.gatherUsageStats false ^
    --browser.serverAddress localhost
