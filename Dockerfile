# Multi-stage: build del frontend → runtime Python con assets estáticos servidos por FastAPI.

# ─── Stage 1: build frontend ────────────────────────────────────
FROM node:22-trixie-slim AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: runtime ───────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# node no es opcional: yt-dlp necesita un runtime JS para resolver el desafío
# de YouTube (ver JS_RUNTIMES en app/services/downloader.py). Sin él cae a un
# cliente de respaldo cuyas URLs YouTube rechaza con 403.
# Se copia el binario de la etapa de build en lugar de instalar el paquete de
# Debian: ese es node 20 e yt-dlp lo marca "unsupported" (necesita 22+).
# Ambas imágenes son trixie, comparten glibc y basta con el binario.
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /build/build /app/frontend/build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BBEAT_HOST=0.0.0.0 \
    BBEAT_PORT=8787

WORKDIR /app/backend
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8787/api/health || exit 1

CMD ["python", "-m", "app.main"]
