"""
Database initialization and seeding.

Creates demo API key (kat_live_...) if not present.
Idempotent: safe to run multiple times.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_api_key
from app.db.base import Base
from app.db.session import async_session_maker, engine
from app.models.api_key import APIKey


async def ensure_demo_key(db: AsyncSession) -> None:
    """Check if demo key exists, create if not."""
    prefix = "kat_live"
    result = await db.execute(
        select(APIKey).where(APIKey.key_prefix == prefix, APIKey.revoked_at.is_(None))
    )
    existing = result.scalars().first()

    if existing:
        print(f"Demo API key already exists (id={existing.id})")
        return

    raw_key, key_prefix = generate_api_key()
    key_hash = hash_api_key(raw_key)

    api_key = APIKey(
        key_prefix=key_prefix,
        key_hash=key_hash,
        name="Demo Key",
        description="Development/demo API key",
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    print(f"\n{'=' * 60}")
    print("DEMO API KEY CREATED")
    print(f"{'=' * 60}")
    print(f"Key: {raw_key}")
    print(f"Prefix: {key_prefix}")
    print(f"ID: {api_key.id}")
    print(f"{'=' * 60}\n")
    print("IMPORTANT: Save this key - it cannot be retrieved!")
    print("Use it as X-API-Key header for requests.\n")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        await ensure_demo_key(session)

    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())
