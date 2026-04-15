from typing import AsyncGenerator

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError
from app.core.security import verify_api_key
from app.db.session import async_session_maker
from app.models.api_key import APIKey

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_current_api_key(
    raw_key: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    """
    Validate the ``X-API-Key`` header and return the matching APIKey row.

    Flow:
    1. Extract the prefix (first 8 chars) for an indexed DB lookup.
    2. Bcrypt-verify the raw key against every non-revoked candidate.
    3. Raise 401 on any failure so callers never see which step failed.
    """
    if not raw_key:
        raise AuthError("Missing X-API-Key header")

    prefix = raw_key[:8]

    result = await db.execute(
        select(APIKey).where(
            APIKey.key_prefix == prefix,
            APIKey.revoked_at.is_(None),
        )
    )
    candidates = result.scalars().all()

    for api_key in candidates:
        if verify_api_key(raw_key, api_key.key_hash):
            return api_key

    raise AuthError("Invalid or revoked API key")
