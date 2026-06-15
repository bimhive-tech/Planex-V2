# Single Railway service: Django (gunicorn, internal :8000) + Next.js (front door :$PORT).
# Next reverse-proxies /api and /admin to Django via rewrites.

# ── Stage 1: build the Next.js frontend (standalone output) ──────────────
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 2: runtime (python + node together) ────────────────────────────
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NODE_VERSION=22

# Install Node.js 22 alongside Python.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Backend deps.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/

# Collect Django static (admin/DRF) into backend/staticfiles via WhiteNoise.
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN cd backend && DATABASE_URL=sqlite:// DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput || true

# Frontend standalone server + assets.
COPY --from=frontend /app/frontend/.next/standalone ./frontend/
COPY --from=frontend /app/frontend/.next/static ./frontend/.next/static
COPY --from=frontend /app/frontend/public ./frontend/public

COPY start.sh ./start.sh
RUN chmod +x ./start.sh

EXPOSE 3000
CMD ["./start.sh"]
