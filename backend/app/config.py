"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────
    APP_NAME: str = "CityInspect API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Auth ─────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE-ME-in-production-use-openssl-rand-hex-64"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ALGORITHM: str = "HS256"

    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://cityinspect:cityinspect@db:5432/cityinspect"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # ── Storage ──────────────────────────────────────────
    STORAGE_BACKEND: str = "local"  # "local" | "s3"
    UPLOAD_DIR: str = "/data/uploads"
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # ── AI Service ───────────────────────────────────────
    AI_SERVICE_URL: str = "http://ai-service:8001"
    AI_MODEL_PATH: str = "/models/yolov8_hazard.pt"
    AI_CONFIDENCE_THRESHOLD: float = 0.45

    # ── Duplicate Detection ──────────────────────────────
    DUPLICATE_GPS_RADIUS_M: float = 25.0
    DUPLICATE_IMAGE_THRESHOLD: float = 0.85
    DUPLICATE_LIDAR_THRESHOLD: float = 0.80

    # ── Redis ────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
