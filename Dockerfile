FROM python:3.11-slim
WORKDIR /app
RUN mkdir -p /data/uploads
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/main.py .
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
