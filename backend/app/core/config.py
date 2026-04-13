"""
Application configuration via Pydantic Settings.
All values can be overridden with environment variables or a .env file.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────────
    app_name: str = "CityInspect API"
    version: str = "3.0.0"
    debug: bool = False

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./cityinspect.db"

    # ── Auth ─────────────────────────────────────────────────
    secret_key: str = "cityinspect-dev-secret-CHANGE-IN-PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_days: int = 30

    # ── Storage ──────────────────────────────────────────────
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10
    allowed_image_types: List[str] = ["image/jpeg", "image/png", "image/webp"]

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── AI Services ──────────────────────────────────────────
    ai_service_url: str = "http://localhost:8001"
    anthropic_api_key: str = ""
    google_maps_key: str = ""

    # ── Pipeline ─────────────────────────────────────────────
    duplicate_gps_radius_m: float = 30.0
    duplicate_time_window_hours: int = 48  # ignore same spot after 48h gap
    pipeline_enabled: bool = True

    # ── CORS ─────────────────────────────────────────────────
    allowed_origins: List[str] = ["http://localhost:3000", "http://localhost:3001", "https://cityinspect-production.up.railway.app"]

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_upload: str = "20/minute"
    rate_limit_default: str = "60/minute"

    # ── WhatsApp ──────────────────────────────────────────────
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "cityinspect_dev"

    # ── Google Drive ─────────────────────────────────────────
    google_drive_enabled: bool = False
    google_drive_folder_id: str = ""           # Root folder ID in Drive
    google_service_account_file: str = ""      # Path to service_account.json

    @property
    def async_database_url(self) -> str:
        """Normalise DATABASE_URL to an async-compatible driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("sqlite:///") and "+aiosqlite" not in url:
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return url

    @property
    def upload_path(self) -> str:
        path = self.upload_dir
        if os.path.exists("/data"):
            path = "/data/uploads"
        os.makedirs(path, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
