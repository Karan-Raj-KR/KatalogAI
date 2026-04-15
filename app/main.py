from contextvars import copy_context
from typing import Any

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp

import app.models  # noqa: F401 — registers all ORM models with the mapper
from app.config import settings
from app.core.exceptions import KatalogError
from app.core.logging import RequestIDMiddleware, request_id_var
from app.api.v1.router import router as v1_router


def create_app() -> FastAPI:
    app = FastAPI(title="KatalogAI", version="0.1.0")

    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=0.0,
        )

    app.add_middleware(RequestIDMiddleware)

    app.include_router(v1_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.exception_handler(KatalogError)
    async def katalog_error_handler(request: Request, exc: KatalogError) -> JSONResponse:
        request_id = request_id_var.get()
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "request_id": request_id,
                }
            },
        )

    return app


app = create_app()
