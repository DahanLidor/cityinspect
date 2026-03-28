FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (includes pre-built frontend_build/)
COPY backend/ .

# Protocol YAML files (workflow engine)
COPY municipalities/ /municipalities

# Create upload directory
RUN mkdir -p /data/uploads

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
