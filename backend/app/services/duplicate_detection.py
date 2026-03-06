"""Duplicate incident detection using GPS proximity, image hashing, and LiDAR similarity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

import imagehash
import numpy as np
from PIL import Image
from io import BytesIO
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.models import Incident, IncidentCluster, IncidentReport

settings = get_settings()


@dataclass
class SimilarityScore:
    incident_id: uuid.UUID
    gps_distance_m: float
    image_similarity: float
    lidar_similarity: float
    combined_score: float


class DuplicateDetector:
    """Detects whether a new report matches an existing incident."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_duplicates(
        self,
        latitude: float,
        longitude: float,
        image_bytes: bytes,
        lidar_measurements: Optional[dict] = None,
        radius_m: float = None,
    ) -> list[SimilarityScore]:
        """Return nearby incidents ranked by combined similarity."""

        radius = radius_m or settings.DUPLICATE_GPS_RADIUS_M
        candidates = await self._find_nearby_incidents(latitude, longitude, radius)

        if not candidates:
            return []

        new_hash = self._compute_image_hash(image_bytes)
        scores: list[SimilarityScore] = []

        for incident in candidates:
            gps_dist = await self._gps_distance(latitude, longitude, incident.latitude, incident.longitude)

            # Image similarity via perceptual hash
            img_sim = 0.0
            reports = await self._get_reports_for_incident(incident.id)
            for report in reports:
                if report.image_hash:
                    existing_hash = imagehash.hex_to_hash(report.image_hash)
                    distance = new_hash - existing_hash
                    sim = max(0.0, 1.0 - distance / 64.0)
                    img_sim = max(img_sim, sim)

            # LiDAR geometric similarity
            lidar_sim = self._lidar_similarity(lidar_measurements, incident)

            combined = self._weighted_score(gps_dist, img_sim, lidar_sim, radius)

            scores.append(SimilarityScore(
                incident_id=incident.id,
                gps_distance_m=gps_dist,
                image_similarity=img_sim,
                lidar_similarity=lidar_sim,
                combined_score=combined,
            ))

        scores.sort(key=lambda s: s.combined_score, reverse=True)
        return scores

    async def merge_into_cluster(
        self,
        canonical_id: uuid.UUID,
        new_incident_id: uuid.UUID,
        score: SimilarityScore,
    ) -> IncidentCluster:
        """Merge a duplicate incident into an existing cluster."""

        result = await self.db.execute(
            select(IncidentCluster).where(IncidentCluster.canonical_incident == canonical_id)
        )
        cluster = result.scalar_one_or_none()

        if cluster is None:
            cluster = IncidentCluster(
                canonical_incident=canonical_id,
                report_count=2,
                gps_similarity=1.0 - (score.gps_distance_m / settings.DUPLICATE_GPS_RADIUS_M),
                image_similarity=score.image_similarity,
                lidar_similarity=score.lidar_similarity,
                merged_incident_ids=[new_incident_id],
            )
            self.db.add(cluster)
        else:
            cluster.merged_incident_ids = cluster.merged_incident_ids + [new_incident_id]
            cluster.report_count += 1
            cluster.image_similarity = max(cluster.image_similarity or 0, score.image_similarity)

        # Update canonical incident report count
        canonical = await self.db.get(Incident, canonical_id)
        if canonical:
            canonical.report_count += 1
            canonical.last_reported_at = func.now()

        return cluster

    # ── Private helpers ──────────────────────────────────────

    async def _find_nearby_incidents(
        self, lat: float, lon: float, radius_m: float
    ) -> list[Incident]:
        query = text("""
            SELECT id FROM incidents
            WHERE status NOT IN ('resolved', 'dismissed')
              AND ST_DWithin(
                  location,
                  ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                  :radius
              )
            ORDER BY location <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            LIMIT 10
        """)
        result = await self.db.execute(query, {"lat": lat, "lon": lon, "radius": radius_m})
        ids = [row[0] for row in result.fetchall()]

        if not ids:
            return []

        incidents_result = await self.db.execute(
            select(Incident).where(Incident.id.in_(ids))
        )
        return list(incidents_result.scalars().all())

    async def _get_reports_for_incident(self, incident_id: uuid.UUID) -> list[IncidentReport]:
        result = await self.db.execute(
            select(IncidentReport).where(IncidentReport.incident_id == incident_id)
        )
        return list(result.scalars().all())

    async def _gps_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        query = text("""
            SELECT ST_Distance(
                ST_SetSRID(ST_MakePoint(:lon1, :lat1), 4326)::geography,
                ST_SetSRID(ST_MakePoint(:lon2, :lat2), 4326)::geography
            )
        """)
        result = await self.db.execute(query, {"lat1": lat1, "lon1": lon1, "lat2": lat2, "lon2": lon2})
        return float(result.scalar())

    @staticmethod
    def _compute_image_hash(image_bytes: bytes) -> imagehash.ImageHash:
        img = Image.open(BytesIO(image_bytes))
        return imagehash.phash(img)

    @staticmethod
    def _lidar_similarity(new_lidar: Optional[dict], incident: Incident) -> float:
        if not new_lidar or not incident.depth_m:
            return 0.0

        comparisons = []
        for key, inc_val in [
            ("depth_m", incident.depth_m),
            ("width_m", incident.width_m),
            ("length_m", incident.length_m),
        ]:
            new_val = new_lidar.get(key)
            if new_val and inc_val:
                ratio = min(new_val, inc_val) / max(new_val, inc_val)
                comparisons.append(ratio)

        return float(np.mean(comparisons)) if comparisons else 0.0

    @staticmethod
    def _weighted_score(gps_dist: float, img_sim: float, lidar_sim: float, radius: float) -> float:
        gps_score = max(0.0, 1.0 - gps_dist / radius)
        return 0.40 * gps_score + 0.40 * img_sim + 0.20 * lidar_sim
