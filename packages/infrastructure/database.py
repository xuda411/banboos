"""Async PostgreSQL session factory.

Engine creation is lazy so demo/read-only development remains usable without a
running database container. Production startup must provide an explicit URL.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def database_url() -> str:
    return os.getenv(
        "BANBOOS2_DATABASE_URL",
        "postgresql+asyncpg://banboos:banboos-dev-only@127.0.0.1:5432/banboos2",
    )


def create_engine() -> AsyncEngine:
    return create_async_engine(database_url(), pool_pre_ping=True, pool_recycle=1800)


def session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine or create_engine(), expire_on_commit=False)


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
