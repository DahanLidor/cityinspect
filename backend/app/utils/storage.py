"""File storage abstraction supporting local filesystem and S3-compatible backends."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

settings = get_settings()


class StorageBackend:
    """Abstract storage interface."""

    async def upload(self, file_bytes: bytes, filename: str, content_type: str) -> str:
        raise NotImplementedError

    def get_url(self, key: str) -> str:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.UPLOAD_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def upload(self, file_bytes: bytes, filename: str, content_type: str) -> str:
        unique = f"{uuid.uuid4().hex[:12]}_{filename}"
        dest = self.base_dir / unique
        dest.write_bytes(file_bytes)
        return f"/uploads/{unique}"

    def get_url(self, key: str) -> str:
        return key


class S3Storage(StorageBackend):
    def __init__(self):
        kwargs = {
            "region_name": settings.S3_REGION,
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
        }
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        self.client = boto3.client("s3", **kwargs)
        self.bucket = settings.S3_BUCKET

    async def upload(self, file_bytes: bytes, filename: str, content_type: str) -> str:
        key = f"uploads/{uuid.uuid4().hex[:12]}_{filename}"
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
        except ClientError as e:
            raise RuntimeError(f"S3 upload failed: {e}") from e
        return key

    def get_url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600,
        )


def get_storage() -> StorageBackend:
    if settings.STORAGE_BACKEND == "s3":
        return S3Storage()
    return LocalStorage()
