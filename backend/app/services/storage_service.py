"""
File storage service — saves uploaded images, validates MIME type & size.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

import aiofiles
from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Map allowed MIME types to canonical file extensions
_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# Magic-byte signatures for server-side MIME validation
_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # partial check — good enough for MVP
}


def _detect_mime(header: bytes) -> Optional[str]:
    for sig, mime in _MAGIC.items():
        if header.startswith(sig):
            return mime
    return None


async def save_upload(file: UploadFile) -> tuple[str, str]:
    """
    Validate and persist an uploaded image.
    Returns (image_url, image_hash).
    Raises HTTPException on bad input.
    """
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Read entire file (bounded by max size + 1 to detect oversized uploads)
    raw = await file.read(max_bytes + 1)

    if len(raw) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {settings.max_upload_size_mb} MB limit",
        )

    # Server-side magic-byte check
    detected_mime = _detect_mime(raw[:16])
    if detected_mime not in settings.allowed_image_types:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {settings.allowed_image_types}",
        )

    ext = _MIME_TO_EXT[detected_mime]
    image_hash = hashlib.sha256(raw).hexdigest()[:16]
    filename = f"{image_hash}.{ext}"
    dest = os.path.join(settings.upload_path, filename)

    async with aiofiles.open(dest, "wb") as fh:
        await fh.write(raw)

    logger.info("Image saved", extra={"filename": filename, "size": len(raw)})
    return f"/uploads/{filename}", image_hash
