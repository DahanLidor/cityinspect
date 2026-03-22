"""
Authentication helpers: JWT creation/decoding + Argon2 password hashing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)
_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)


# ── Passwords ────────────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.access_token_expire_days)
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[str]:
    """Returns username (sub) or None on failure."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except JWTError:
        return None


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Dependency: resolve JWT → User ORM object.  Raises 401 on failure."""
    # Avoid circular import — import model here
    from app.models import User

    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    username = decode_token(creds.credentials)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user
