# Multi-stage: build del frontend → runtime Python con assets estáticos servidos por FastAPI.

# ─── Stage 1: build frontend ────────────────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: runtime ───────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

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

CMD ["python", "-m", "app.main"]
