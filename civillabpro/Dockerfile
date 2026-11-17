# CivilLabPro OS: one image that serves the API and the built web client.
#   docker build -t civillabpro -f civillabpro/Dockerfile civillabpro
# Not built in the session that wrote it (no Docker daemon there); the same steps were run by hand
# and verified: npm ci && npm run build, pip install ., alembic upgrade head, uvicorn with CLP_STATIC_DIR.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
RUN pip install .
COPY --from=web /web/dist ./static
ENV CLP_ENV=production CLP_STATIC_DIR=/app/static
RUN useradd --system --uid 10001 clp && chown -R clp /app
USER clp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"
# Migrations run on start so a new release upgrades its own schema.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
