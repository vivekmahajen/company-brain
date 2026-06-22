# Company Brain API (FastAPI) — Railway deploy image.
# Build context is the repo root so `apps.api.*` imports resolve.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching.
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install -r apps/api/requirements.txt

# App code + fixtures (needed for the demo seed).
COPY . .

EXPOSE 8000

# Railway injects $PORT.
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
