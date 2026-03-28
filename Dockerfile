# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY backend/ .

# React build output → served by FastAPI SPA fallback
COPY --from=frontend-builder /frontend/dist ./frontend_build

# Create upload directory
RUN mkdir -p /data/uploads

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
