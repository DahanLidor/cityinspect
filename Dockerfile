FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
RUN mkdir -p /data/uploads
CMD python seed_demo.py && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
