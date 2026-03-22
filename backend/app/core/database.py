"""
Async SQLAlchemy engine + session factory.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

_engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    # SQLite doesn't support concurrency — disable pool for it
    **({} if "sqlite" not in settings.async_database_url else {"connect_args": {"check_same_thread": False}}),
)

_async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables (used in tests and SQLite dev mode)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """Drop all tables (used in tests)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Type alias used in route signatures
DbSession = Annotated[AsyncSession, Depends(get_db)]
