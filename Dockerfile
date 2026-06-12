FROM python:3.11-slim

# 시스템 패키지 설치 (FFmpeg + 한국어 폰트 포함)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p web_jobs

EXPOSE 5000
CMD gunicorn --bind "0.0.0.0:${PORT:-5000}" --workers 1 --threads 4 --timeout 600 app:app
