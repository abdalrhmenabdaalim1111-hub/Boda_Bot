# =============================================================================
#  Dockerfile — Boda Bot System (v5.1) — صورة إنتاجية بلا واجهة رسومية
#  تشغّل server_runner.py (كل البوتات) + api_server + monitor_agent
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت المكتبات أولاً للاستفادة من كاش الطبقات
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# نسخ ملفات المشروع
COPY . .

RUN mkdir -p Data Logs Backups

# منفذ Webhook المشترك + (اختياري) خادم API
EXPOSE 8443 8080

# إيقاف نظيف عند docker stop
STOPSIGNAL SIGTERM

# المشغّل الإنتاجي (Polling افتراضياً، Webhook عند USE_WEBHOOK=true)
CMD ["python", "server_runner.py"]
