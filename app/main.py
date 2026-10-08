"""AX Link 백엔드 진입점.

    uvicorn app.main:app --reload --port 8080

프런트 vite dev 서버가 /api 를 8080 으로 프록시한다(frontend/vite.config.ts).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.activity.router import router as activity_router
from app.admin.router import router as admin_router
from app.ai.embedding import embedding_port
from app.ai.router import router as ai_router
from app.auth.router import router as auth_router
from app.common.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.config import settings
from app.dashboard.board_router import router as board_router
from app.dashboard.router import router as dashboard_router
from app.db import close_pool, pool, tx
from app.document.router import router as document_router
from app.instance import router as instance_router
from app.integration.router import router as integration_router
from app.org.router import router as org_router
from app.project.router import router as project_router
from app.project.schedule import router as schedule_router
from app.rag.indexing import verify_dimension
from app.rag.router import router as ask_router
from app.review.router import router as review_router
from app.semantic.router import router as semantic_router
from app.standard.router import router as standard_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 운영에서 비밀값이 빠진 채 뜨면 누구나 토큰을 위조하거나, 재기동 뒤 인증정보를 못 푼다
    if problems := settings.production_problems():
        raise RuntimeError("운영 설정이 빠졌다: " + "; ".join(problems))
    pool()
    # 임베딩 차원이 컬럼과 어긋난 채 뜨면 색인은 되는데 검색이 조용히 망가진다.
    # 기동 때 막는 편이 낫다.
    with tx() as cur:
        verify_dimension(cur, embedding_port())
    # 일별 스냅샷과 주기 수집은 스스로 돌아야 한다(SWFR.PIP.005·CON.005). 앱과 함께 뜨고 진다
    task = stop = None
    if settings.scheduler_enabled:
        from app import scheduler

        task, stop = scheduler.start()
    # 문서 처리 작업자(GH-121). 업로드는 접수만 하고 추출·색인·초안은 여기서 뒤에서 한다
    doc_task = doc_stop = None
    if settings.document_processing == "background":
        from app.document import worker

        doc_task, doc_stop = worker.start()
    try:
        yield
    finally:
        for s_, t_ in ((stop, task), (doc_stop, doc_task)):
            if s_ is not None and t_ is not None:
                s_.set()
                t_.cancel()
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
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(auth_router)
app.include_router(project_router)
app.include_router(org_router)
app.include_router(integration_router)
app.include_router(document_router)
app.include_router(standard_router)
app.include_router(dashboard_router)
app.include_router(board_router)
app.include_router(semantic_router)
app.include_router(review_router)
app.include_router(ask_router)
app.include_router(ai_router)
app.include_router(admin_router)
app.include_router(activity_router)
app.include_router(schedule_router)
app.include_router(instance_router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "UP", "version": settings.app_version}
