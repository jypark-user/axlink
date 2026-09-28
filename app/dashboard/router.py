"""/api/projects/{id}/progress — 세 갈래 진척 조회.

메뉴 직접 접근과 자연어 질의가 이 한 경로를 함께 쓴다. 두 경로의 수치가 어긋나면
그건 버그다 — 그래서 화면이 따로 계산하지 않는다.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.dashboard import service, snapshot
from app.dashboard.models import (
    ProgressResponse,
    ProgressSnapshotResponse,
    WbsDeliverablesResponse,
    WbsScheduleResponse,
)
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


@router.get("/{project_id}/snapshots", response_model=list[ProgressSnapshotResponse])
def list_snapshots(
    project_id: str, principal: Principal, limit: Annotated[int, Query(ge=1, le=366)] = 90
) -> list[ProgressSnapshotResponse]:
    """스냅샷 이력. 최근 것이 앞이다."""
    with tx() as cur:
        return snapshot.list_recent(cur, principal, project_id, limit)


@router.post("/{project_id}/snapshots", response_model=ProgressSnapshotResponse)
def take_snapshot(
    project_id: str, principal: Principal, at: BaseDate = None
) -> ProgressSnapshotResponse:
    """일별 스냅샷을 찍는다(SWFR.PIP.005). 같은 날 다시 찍으면 덮어쓴다.

    스케줄러는 없다. 운영에서는 이 경로를 하루 한 번 부른다.
    """
    with tx() as cur:
        return snapshot.take(cur, principal, project_id, at)


@router.get("/{project_id}/wbs/deliverables", response_model=WbsDeliverablesResponse)
def wbs_deliverables(
    project_id: str, principal: Principal, at: Annotated[date | None, Query()] = None
) -> WbsDeliverablesResponse:
    """산출물 화면. WBS 가 정한 산출물과 제출 판정(ARC-016)."""
    with tx() as cur:
        return service.wbs_deliverables(cur, principal, project_id, at)


@router.get("/{project_id}/wbs", response_model=WbsScheduleResponse)
def project_wbs(project_id: str, principal: Principal, at: BaseDate = None) -> WbsScheduleResponse:
    """일정 화면의 작업 줄. 용역사 WBS 파일 → Redmine 이슈 일정 → 없음(고지) 순이다.
    표준 산출물 목록으로 WBS 를 흉내 내지 않는다 — WBS 는 사업마다 다르다.
    """
    with tx() as cur:
        return service.wbs_schedule(cur, principal, project_id, at)
