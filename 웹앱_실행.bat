@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo  패키지 확인 중...
pip install streamlit openai anthropic selenium webdriver-manager ^
    openpyxl requests beautifulsoup4 pandas ^
    duckduckgo-search reportlab python-pptx ^
    "openai>=1.30.0,<2.0.0" -q

echo.
echo  웹 리서치 어시스턴트 실행 중...
echo  브라우저가 자동으로 열립니다.
echo.

streamlit run app.py ^
    --server.headless false ^
    --server.port 8501 ^
    --browser.gatherUsageStats false

pause
