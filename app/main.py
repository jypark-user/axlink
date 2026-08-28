"""AX Link 백엔드 진입점.

    uvicorn app.main:app --reload --port 8080

프런트 vite dev 서버가 /api 를 8080 으로 프록시한다(frontend/vite.config.ts).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.common.errors import (
    ApiError,
    api_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.config import settings
from app.db import close_pool, pool
from app.project.router import router as project_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(title="AX Link", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(auth_router)
app.include_router(project_router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "UP"}
