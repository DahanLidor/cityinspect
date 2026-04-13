"""
Google Drive integration — creates a folder per ticket with image, PLY, and JSON.

Setup:
  1. Create a Google Cloud project → enable Drive API
  2. Create a Service Account → download JSON key
  3. Share your Drive folder with the service account email
  4. Set env vars:
     GOOGLE_DRIVE_ENABLED=true
     GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service_account.json
     GOOGLE_DRIVE_FOLDER_ID=<root folder id from Drive URL>
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_drive_service = None


def _get_drive():
    """Lazy-init Google Drive API client. Supports file path OR raw JSON string."""
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/drive.file"]

    # Option 1: raw JSON string (for Railway / Docker)
    if settings.google_service_account_json:
        import json as _json
        info = _json.loads(settings.google_service_account_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    # Option 2: file path (for local dev)
    elif settings.google_service_account_file and os.path.exists(settings.google_service_account_file):
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=scopes,
        )
    else:
        logger.warning("Drive: no credentials configured")
        return None

    _drive_service = build("drive", "v3", credentials=creds)
    logger.info("Google Drive API initialized")
    return _drive_service


def _create_folder(name: str, parent_id: str) -> str:
    """Create a folder in Drive, return its ID."""
    drive = _get_drive()
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = drive.files().create(body=meta, fields="id").execute()
    return folder["id"]


def _upload_file(name: str, data: bytes, mime: str, folder_id: str) -> str:
    """Upload a file to a Drive folder, return its ID."""
    from googleapiclient.http import MediaIoBaseUpload

    drive = _get_drive()
    meta = {"name": name, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    f = drive.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
    return f.get("webViewLink", f.get("id", ""))


def export_ticket_to_drive(
    ticket: dict[str, Any],
    detection: dict[str, Any],
    pipeline_notes: dict[str, Any],
    image_path: str | None = None,
    ply_path: str | None = None,
) -> str | None:
    """
    Create a Drive folder for this ticket and upload all artifacts.
    Returns the folder URL or None if Drive is disabled.
    """
    if not settings.google_drive_enabled:
        return None

    drive = _get_drive()
    if not drive:
        logger.warning("Drive: API not available, skipping export")
        return None

    root_folder = settings.google_drive_folder_id
    if not root_folder:
        logger.warning("Drive: no GOOGLE_DRIVE_FOLDER_ID configured")
        return None

    try:
        # Folder name: "Ticket #18 — pothole — 2026-04-13"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        folder_name = f"Ticket #{ticket['id']} — {ticket.get('defect_type', 'unknown')} — {now}"
        folder_id = _create_folder(folder_name, root_folder)
        logger.info("Drive folder created: %s", folder_name)

        # 1. Upload image
        if image_path and os.path.exists(image_path):
            ext = image_path.rsplit(".", 1)[-1].lower()
            mime = f"image/{ext}" if ext in ("png", "webp") else "image/jpeg"
            with open(image_path, "rb") as f:
                _upload_file(f"photo.{ext}", f.read(), mime, folder_id)
            logger.info("Drive: image uploaded")

        # 2. Upload PLY
        if ply_path and os.path.exists(ply_path):
            with open(ply_path, "rb") as f:
                _upload_file("point_cloud.ply", f.read(), "application/octet-stream", folder_id)
            logger.info("Drive: PLY uploaded")

        # 3. Build and upload comprehensive JSON
        report = {
            "ticket": {
                "id": ticket.get("id"),
                "city_id": ticket.get("city_id"),
                "defect_type": ticket.get("defect_type"),
                "severity": ticket.get("severity"),
                "score": ticket.get("score"),
                "status": ticket.get("status"),
                "lat": ticket.get("lat"),
                "lng": ticket.get("lng"),
                "address": ticket.get("address"),
                "created_at": str(ticket.get("created_at", "")),
                "detection_count": ticket.get("detection_count"),
                "sla_deadline": str(ticket.get("sla_deadline", "")),
                "sla_breached": ticket.get("sla_breached"),
            },
            "detection": {
                "id": detection.get("id"),
                "detected_at": str(detection.get("detected_at", "")),
                "reported_by": detection.get("reported_by"),
                "vehicle_id": detection.get("vehicle_id"),
                "vehicle_model": detection.get("vehicle_model"),
                "image_url": detection.get("image_url"),
                "image_caption": detection.get("image_caption"),
                "point_cloud_url": detection.get("point_cloud_url"),
                "defect_length_cm": detection.get("defect_length_cm"),
                "defect_width_cm": detection.get("defect_width_cm"),
                "defect_depth_cm": detection.get("defect_depth_cm"),
                "surface_area_m2": detection.get("surface_area_m2"),
                "defect_volume_m3": detection.get("defect_volume_m3"),
            },
            "sensor_data": _safe_json(detection.get("sensor_data_json", "{}")),
            "weather": {
                "ambient_temp_c": detection.get("ambient_temp_c"),
                "weather_condition": detection.get("weather_condition"),
                "wind_speed_kmh": detection.get("wind_speed_kmh"),
                "humidity_pct": detection.get("humidity_pct"),
                "visibility_m": detection.get("visibility_m"),
            },
            "pipeline": {
                "vlm": pipeline_notes.get("vlm", {}),
                "environment": pipeline_notes.get("environment", {}),
                "dedup": pipeline_notes.get("dedup", {}),
                "scorer": pipeline_notes.get("scorer", {}),
            },
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        json_bytes = json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        _upload_file("report.json", json_bytes, "application/json", folder_id)
        logger.info("Drive: JSON report uploaded")

        # Get folder URL
        folder_meta = drive.files().get(fileId=folder_id, fields="webViewLink").execute()
        folder_url = folder_meta.get("webViewLink", "")
        logger.info("Drive export complete: %s", folder_url)
        return folder_url

    except Exception as exc:
        logger.error("Drive export failed: %s", exc)
        return None


def _safe_json(raw: str | dict) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
