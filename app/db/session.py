"""Datenbank-Engine und Sitzungen (asynchron, asyncpg)."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

# Kleiner Pool: auf dem MOROS.neo zählt jedes MB, und mehr als eine Handvoll
# gleichzeitiger Zugriffe (Display, Admin, Hintergrunddienste) gibt es nicht.
engine = create_async_engine(
    get_settings().database_url, pool_size=5, max_overflow=2, pool_pre_ping=True
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-Abhängigkeit: eine Sitzung pro Anfrage."""
    async with SessionFactory() as session:
        yield session
