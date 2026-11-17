# Claims Onboarding and Exception Management Platform. Synthetic data only; not HIPAA-compliant.
FROM node:22-slim AS web
WORKDIR /web
COPY claims_platform_web/package.json claims_platform_web/package-lock.json claims_platform_web/.npmrc ./
RUN npm ci
COPY claims_platform_web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CLAIMS_ENV=production CLAIMS_SIMULATION=0 \
    CLAIMS_STORAGE_DIR=/data/files CLAIMS_WEB_DIST=/app/claims_platform_web/dist
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY claims_onboarding/ claims_onboarding/
COPY orders_assistant/ orders_assistant/
COPY claims_platform/ claims_platform/
COPY --from=web /web/dist claims_platform_web/dist
RUN useradd --create-home --uid 10001 app && mkdir -p /data/files && chown -R app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'))"
# One worker: background runs and start-up recovery assume a single process (see docs/platform/architecture.md).
# Hosts such as Render set PORT; locally it defaults to 8000.
CMD ["sh", "-c", "exec uvicorn claims_platform.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
