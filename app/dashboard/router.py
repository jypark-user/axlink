"""/api/projects/{id}/progress — 세 갈래 진척 조회.

메뉴 직접 접근과 자연어 질의가 이 한 경로를 함께 쓴다. 두 경로의 수치가 어긋나면
그건 버그다 — 그래서 화면이 따로 계산하지 않는다.
"""

from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from app.auth.deps import Principal
from app.common import clock
from app.dashboard import completion, designation, iso29110, plan_upload, service, snapshot
from app.dashboard.models import (
    CompletionSummaryResponse,
    DesignateRequest,
    DesignationEvent,
    DesignationUpdateRequest,
    Iso29110Response,
    ProgressResponse,
    ProgressSnapshotResponse,
    WbsDeliverablesResponse,
    WbsPlanUploadResponse,
    WbsScheduleResponse,
)
from app.db import tx

router = APIRouter(prefix="/api/projects", tags=["progress"])

# 기준일을 넘길 수 있게 둔다. 추이 화면이 과거 시점의 계획선을 다시 그릴 때 쓴다.
BaseDate = Annotated[date | None, Query(description="기준일. 비우면 오늘")]


@router.get("/{project_id}/wbs/completion", response_model=CompletionSummaryResponse)
def wbs_completion(
    project_id: str, principal: Principal, at: BaseDate = None
) -> CompletionSummaryResponse:
    """보고 진척률과 완료 확인율, 작업별 근거 사실(ARC-019). 시맨틱 지표와 같은 뷰를 읽는다."""
    with tx() as cur:
        service.require_project(cur, principal, project_id)
        return CompletionSummaryResponse(**completion.summary(cur, project_id, at or clock.today()))


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
    """오늘 스냅샷을 찍는다(SWFR.PIP.005). 같은 날 다시 찍으면 덮어쓴다.

    매일 기록은 스케줄러가 한다. 이 경로는 시연·점검 때 손으로 찍는 용도로, 발주기관 담당자와
    관리자만 쓴다. at 은 오늘(사업 시간대)만 받는다.
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


@router.get("/{project_id}/wbs/iso29110", response_model=Iso29110Response)
def iso29110_coverage(project_id: str, principal: Principal) -> Iso29110Response:
    """ISO/IEC 29110 22종 충족 현황. 예상 산출물에 계획됐는지와 제출·승인을 본다(11-19)."""
    with tx() as cur:
        return iso29110.build(cur, principal, project_id)


# ---- 작업별 지정 산출물·양식 (UC-033). 목록은 산출물 화면 응답(wbs/deliverables)에 함께 온다


@router.post("/{project_id}/wbs/designated-deliverables", status_code=201)
def designate_deliverable(
    project_id: str, req: DesignateRequest, principal: Principal
) -> dict[str, str]:
    """작업에 내야 할 산출물 항목을 정한다. 발주기관만."""
    with tx() as cur:
        return {"id": designation.designate(cur, principal, project_id, req)}


@router.patch("/{project_id}/wbs/designated-deliverables/{designated_id}", status_code=204)
def update_designated_deliverable(
    project_id: str, designated_id: str, req: DesignationUpdateRequest, principal: Principal
) -> Response:
    """항목을 고치거나 다른 작업으로 옮긴다(재지정)."""
    with tx() as cur:
        designation.update(cur, principal, project_id, designated_id, req)
    return Response(status_code=204)


@router.delete("/{project_id}/wbs/designated-deliverables/{designated_id}", status_code=204)
def remove_designated_deliverable(
    project_id: str, designated_id: str, principal: Principal
) -> Response:
    """지정을 거둔다. 제출 이력은 남는다."""
    with tx() as cur:
        designation.remove(cur, principal, project_id, designated_id)
    return Response(status_code=204)


@router.post("/{project_id}/wbs/designated-deliverables/{designated_id}/template", status_code=204)
def put_designated_template(
    project_id: str, designated_id: str, principal: Principal,
    file: Annotated[UploadFile, File()],
) -> Response:
    """양식 파일을 올리거나 바꾼다. 제출본이 아니다."""
    content = file.file.read(designation.TEMPLATE_MAX_BYTES + 1)
    with tx() as cur:
        designation.put_template(
            cur, principal, project_id, designated_id, file.filename or "", content
        )
    return Response(status_code=204)


@router.get("/{project_id}/wbs/designated-deliverables/{designated_id}/template")
def get_designated_template(project_id: str, designated_id: str, principal: Principal) -> Response:
    with tx() as cur:
        row = designation.get_template(cur, principal, project_id, designated_id)
    name = quote(row["template_filename"])
    return Response(
        content=bytes(row["template_bytes"]),
        media_type=row["template_content_type"],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )


@router.get(
    "/{project_id}/wbs/designated-deliverables/{designated_id}/history",
    response_model=list[DesignationEvent],
)
def designated_history(
    project_id: str, designated_id: str, principal: Principal
) -> list[DesignationEvent]:
    with tx() as cur:
        return designation.history(cur, principal, project_id, designated_id)


@router.get("/{project_id}/wbs", response_model=WbsScheduleResponse)
def project_wbs(project_id: str, principal: Principal, at: BaseDate = None) -> WbsScheduleResponse:
    """일정 화면의 작업 줄. 용역사 WBS 파일 → Redmine 이슈 일정 → 없음(고지) 순이다.
    표준 산출물 목록으로 WBS 를 흉내 내지 않는다 — WBS 는 사업마다 다르다.
    """
    with tx() as cur:
        return service.wbs_schedule(cur, principal, project_id, at)


@router.post("/{project_id}/wbs/plan", response_model=WbsPlanUploadResponse, status_code=201)
def upload_wbs_plan(
    project_id: str,
    principal: Principal,
    file: Annotated[UploadFile, File()],
    version: Annotated[str | None, Form()] = None,
) -> WbsPlanUploadResponse:
    """일정 화면에서 WBS 파일을 올린다(11-24). 곧바로 사업수행계획서의 현행 버전이 된다."""
    from app.document import service as document_service

    content = file.file.read(document_service.MAX_BYTES + 1)
    with tx() as cur:
        return plan_upload.upload_plan(
            cur, principal, project_id, file.filename or "", content, version
        )
