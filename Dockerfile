FROM python:3.11-slim

# Chromium 설치 (Selenium 서버 실행용)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-nanum \
    fonts-noto-cjk \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 데이터 디렉토리 (Render Disk 마운트 포인트)
RUN mkdir -p /app/data

EXPOSE 8501

CMD sh -c "streamlit run app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false"
