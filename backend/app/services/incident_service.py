"""Core business logic for incident creation, duplicate detection, and querying."""

from __future__ import annotations

import uuid
from datetime import datetime

import imagehash
from PIL import Image
from io import BytesIO
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.models import Incident, IncidentReport
from app.services.ai_client import AIServiceClient
from app.services.duplicate_detection import DuplicateDetector
from app.utils.storage import StorageBackend

settings = get_settings()


class IncidentService:
    def __init__(self, db: AsyncSession, storage: StorageBackend):
        self.db = db
        self.storage = storage
        self.ai_client = AIServiceClient()
        self.dup_detector = DuplicateDetector(db)

    async def process_upload(
        self,
        user_id: uuid.UUID,
        image_bytes: bytes,
        depth_map_bytes: bytes | None,
        latitude: float,
        longitude: float,
        captured_at: datetime,
        device_info: dict | None = None,
        lidar_measurements: dict | None = None,
    ) -> Incident:
        """Full pipeline: store files → AI detect → LiDAR → dedup → create/merge."""

        # 1. Store files
        image_url = await self.storage.upload(image_bytes, "incident.jpg", "image/jpeg")
        depth_map_url = None
        if depth_map_bytes:
            depth_map_url = await self.storage.upload(depth_map_bytes, "depthmap.bin", "application/octet-stream")

        # 2. AI detection
        ai_result = await self.ai_client.detect_hazard(image_bytes)

        # 3. Compute image hash for dedup
        img_hash = str(imagehash.phash(Image.open(BytesIO(image_bytes))))

        # 4. Check for duplicates
        duplicates = await self.dup_detector.find_duplicates(
            latitude=latitude,
            longitude=longitude,
            image_bytes=image_bytes,
            lidar_measurements=lidar_measurements,
        )

        best_match = duplicates[0] if duplicates and duplicates[0].combined_score >= 0.65 else None

        # 5. Build the report record
        location_str = f"POINT({longitude} {latitude})"
        report = IncidentReport(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            location=location_str,
            image_url=image_url,
            depth_map_url=depth_map_url,
            image_hash=img_hash,
            ai_hazard_type=ai_result.hazard_type,
            ai_confidence=ai_result.confidence,
            ai_raw_output={"hazard_type": ai_result.hazard_type, "confidence": ai_result.confidence},
            lidar_depth_m=lidar_measurements.get("depth_m") if lidar_measurements else None,
            lidar_width_m=lidar_measurements.get("width_m") if lidar_measurements else None,
            lidar_length_m=lidar_measurements.get("length_m") if lidar_measurements else None,
            lidar_area_m2=lidar_measurements.get("surface_area_m2") if lidar_measurements else None,
            lidar_raw_output=lidar_measurements,
            device_info=device_info,
            captured_at=captured_at,
        )

        if best_match:
            # Merge into existing incident
            report.incident_id = best_match.incident_id
            self.db.add(report)
            await self.dup_detector.merge_into_cluster(
                canonical_id=best_match.incident_id,
                new_incident_id=best_match.incident_id,  # same canonical
                score=best_match,
            )
            incident = await self.db.get(Incident, best_match.incident_id)
        else:
            # Create new incident
            severity = self._compute_severity(ai_result.confidence, lidar_measurements)
            incident = Incident(
                hazard_type=ai_result.hazard_type,
                severity=severity,
                location=location_str,
                latitude=latitude,
                longitude=longitude,
                ai_confidence=ai_result.confidence,
                ai_model_version=ai_result.model_version,
                depth_m=lidar_measurements.get("depth_m") if lidar_measurements else None,
                width_m=lidar_measurements.get("width_m") if lidar_measurements else None,
                length_m=lidar_measurements.get("length_m") if lidar_measurements else None,
                surface_area_m2=lidar_measurements.get("surface_area_m2") if lidar_measurements else None,
                volume_m3=lidar_measurements.get("volume_m3") if lidar_measurements else None,
                image_url=image_url,
                depth_map_url=depth_map_url,
                created_by=user_id,
            )
            self.db.add(incident)
            await self.db.flush()
            report.incident_id = incident.id
            self.db.add(report)

        return incident

    async def get_incident(self, incident_id: uuid.UUID) -> Incident | None:
        return await self.db.get(Incident, incident_id)

    async def get_incidents_for_map(
        self, min_lat: float = -90, max_lat: float = 90,
        min_lon: float = -180, max_lon: float = 180,
        limit: int = 500,
    ) -> list[Incident]:
        query = (
            select(Incident)
            .where(
                Incident.latitude.between(min_lat, max_lat),
                Incident.longitude.between(min_lon, max_lon),
                Incident.status.notin_(["dismissed"]),
            )
            .order_by(Incident.last_reported_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _compute_severity(confidence: float, lidar: dict | None) -> str:
        score = confidence * 50
        if lidar:
            depth = lidar.get("depth_m", 0) or 0
            area = lidar.get("surface_area_m2", 0) or 0
            if depth > 0.10:
                score += 20
            if area > 0.50:
                score += 15
            if depth > 0.20 and area > 1.0:
                score += 15

        if score >= 80:
            return "critical"
        elif score >= 60:
            return "high"
        elif score >= 35:
            return "medium"
        return "low"
