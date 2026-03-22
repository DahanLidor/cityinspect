"""
Auth routes: login + /me.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import DbSession
from app.core.security import create_access_token, get_current_user, verify_password
from app.models import User
from app.schemas import AuthResponse, LoginRequest, UserOut
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: DbSession):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_pw):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="שם משתמש או סיסמה שגויים")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="חשבון מושבת")

    token = create_access_token(subject=user.username)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
