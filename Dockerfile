# =============================================================================
#  Dockerfile — Boda Bot System (v4.5)
#  بيئة تشغيل خفيفة ومستقرة للبوتات وواجهة API
# =============================================================================
FROM python:3.10-slim

# إعداد المتغيرات الأساسية لبايثون
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=UTC

# تثبيت متطلبات النظام الأساسية
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت مكتبات بايثون أولاً للاستفادة من كاش Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# نسخ ملفات المشروع
COPY . .

# إنشاء المجلدات الضرورية مع الصلاحيات
RUN mkdir -p Data Logs Backups

# فتح المنافذ: 8080 (خادم API وفحص الصحة) و 8443 (Webhook)
EXPOSE 8080 8443

# فحص صحة الحاوية التلقائي عبر خادم API
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# أمر التشغيل الافتراضي
CMD ["python", "StartManager.py"]

