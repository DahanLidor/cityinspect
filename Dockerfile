FROM node:18-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json .
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
RUN mkdir -p /data/uploads
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/main.py .
# Dashboard v2
COPY dashboard/ ./dashboard/
COPY --from=frontend /frontend/build ./frontend/build
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
