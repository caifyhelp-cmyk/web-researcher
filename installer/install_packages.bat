@echo off
chcp 65001 > nul
echo Python 패키지 설치 중...
python -m pip install --upgrade pip -q
python -m pip install ^
    "streamlit>=1.35.0" ^
    "openai>=1.30.0,<2.0.0" ^
    "anthropic>=0.28.0" ^
    "selenium>=4.20.0" ^
    "webdriver-manager>=4.0.0" ^
    "requests>=2.31.0" ^
    "beautifulsoup4>=4.12.0" ^
    "openpyxl>=3.1.0" ^
    "pandas>=2.0.0" ^
    "duckduckgo-search>=6.2.0" ^
    "reportlab>=4.2.0" ^
    "python-pptx>=0.6.23" ^
    -q
echo 완료.
