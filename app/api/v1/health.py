from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "db": "ok"},
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "db": "error"},
        )
