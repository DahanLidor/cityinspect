"""HTTP client for the AI hazard detection microservice."""

from __future__ import annotations

import httpx
from app.config import get_settings
from app.models.schemas import AIDetectionResult

settings = get_settings()


class AIServiceClient:
    """Calls the AI detection microservice over HTTP."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.AI_SERVICE_URL).rstrip("/")

    async def detect_hazard(self, image_bytes: bytes, filename: str = "image.jpg") -> AIDetectionResult:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/detect",
                files={"file": (filename, image_bytes, "image/jpeg")},
            )
            resp.raise_for_status()
            data = resp.json()

        return AIDetectionResult(
            hazard_type=data["hazard_type"],
            confidence=data["confidence"],
            bounding_box=data.get("bounding_box"),
            model_version=data.get("model_version", ""),
        )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False
