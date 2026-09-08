"""/api/projects/{id}/progress — 세 갈래 진척 조회.

메뉴 직접 접근과 자연어 질의가 이 한 경로를 함께 쓴다. 두 경로의 수치가 어긋나면
그건 버그다 — 그래서 화면이 따로 계산하지 않는다.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.dashboard import service
from app.dashboard.models import ProgressResponse
from app.db import tx

router = APIRouter(prefix="/api/projects", tags=["progress"])

# 기준일을 넘길 수 있게 둔다. 추이 화면이 과거 시점의 계획선을 다시 그릴 때 쓴다.
BaseDate = Annotated[date | None, Query(description="기준일. 비우면 오늘")]


@router.get("/{project_id}/progress", response_model=ProgressResponse)
def project_progress(
    project_id: str, principal: Principal, at: BaseDate = None
) -> ProgressResponse:
    """WBS 기반 · 이슈 해결률 · 산출물 제출률을 함께 낸다.

    하나로 합치지 않는다. 셋의 격차가 감독이 봐야 할 신호이기 때문이다.
    """
    with tx() as cur:
        return service.project_progress(cur, principal, project_id, at)
