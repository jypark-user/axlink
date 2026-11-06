"""/api/projects/{id}/requirements — 표준 모델 조회.

프런트 project-overview-page.tsx 와 requirements 화면이 같은 경로를 쓴다.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.standard import (
    approval,
    repository,
    requirement_decision,
    service,
    trace_service,
)
from app.standard.models import (
    IssueResponse,
    IssueSummaryResponse,
    RequirementDecisionRequest,
    RequirementDecisionRevertRequest,
    RequirementDetailResponse,
    RequirementResponse,
    RequirementSummaryResponse,
    TraceabilityRowResponse,
    WorkProductChecklistResponse,
)

router = APIRouter(prefix="/api/projects", tags=["requirements"])


@router.get("/{project_id}/traceability", response_model=PageResponse[TraceabilityRowResponse])
def traceability(
    project_id: str,
    principal: Principal,
    q: str | None = None,
    status: Literal["DEFINED", "DESIGNED", "IMPLEMENTED", "VERIFIED", "ACCEPTED", "REJECTED"]
    | None = None,
    verified: bool | None = None,
    sourceState: Literal["OPEN", "CLOSED", "UNKNOWN", "NONE"] | None = None,  # noqa: N803
    connectionId: str | None = None,  # noqa: N803
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResponse[TraceabilityRowResponse]:
    """추적표. 요구사항마다 이슈·커밋·산출물이 어느 칸에 걸려 있는지(SWFR.WEB.002).

    조건은 요약 카드가 거는 것이다. totalElements 는 조건에 맞는 건수다.
    사업 전체 건수는 summary 가 준다.
    """
    f = repository.RequirementFilter(
        q=q, status=status, verified=verified, source_state=sourceState,
        connection_id=connectionId,
    )
    with tx() as cur:
        return trace_service.traceability_rows(
            cur, principal, project_id, PageQuery(page=page, size=size), f
        )


@router.get("/{project_id}/requirements/summary", response_model=RequirementSummaryResponse)
def requirement_summary(project_id: str, principal: Principal) -> RequirementSummaryResponse:
    """요구사항 화면 요약. 목록 쪽과 상관없이 사업 전체를 센다.

    /requirements/{requirement_id} 보다 먼저 둔다. 뒤에 두면 summary 가 id 로 잡힌다.
    """
    with tx() as cur:
        return trace_service.requirement_summary(cur, principal, project_id)


@router.get("/{project_id}/requirements/{requirement_id}", response_model=RequirementDetailResponse)
def requirement_detail(
    project_id: str, requirement_id: str, principal: Principal
) -> RequirementDetailResponse:
    """요구사항 하나와 걸린 링크 전부. 링크마다 근거 원문과 위치가 붙는다."""
    with tx() as cur:
        return trace_service.requirement_detail(cur, principal, project_id, requirement_id)


@router.put(
    "/{project_id}/requirements/{requirement_id}/status",
    response_model=RequirementDetailResponse,
)
def decide_requirement_status(
    project_id: str, requirement_id: str, req: RequirementDecisionRequest, principal: Principal
) -> RequirementDetailResponse:
    """발주기관이 요구사항 상태를 사유와 함께 지정한다(ARC-025). 근거 상태는 따로 남는다."""
    with tx() as cur:
        requirement_decision.decide(
            cur, principal, project_id, requirement_id, req.status, req.reason
        )
        return trace_service.requirement_detail(cur, principal, project_id, requirement_id)


@router.post(
    "/{project_id}/requirements/{requirement_id}/status/revert",
    response_model=RequirementDetailResponse,
)
def revert_requirement_status(
    project_id: str, requirement_id: str, req: RequirementDecisionRevertRequest,
    principal: Principal,
) -> RequirementDetailResponse:
    """지정을 거두고 근거 상태로 되돌린다."""
    with tx() as cur:
        requirement_decision.revert(cur, principal, project_id, requirement_id, req.reason)
        return trace_service.requirement_detail(cur, principal, project_id, requirement_id)


@router.get("/{project_id}/requirements", response_model=PageResponse[RequirementResponse])
def list_requirements(
    project_id: str,
    principal: Principal,
    q: str | None = None,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResponse[RequirementResponse]:
    with tx() as cur:
        return service.list_requirements(
            cur, principal, project_id, q, PageQuery(page=page, size=size)
        )


@router.get("/{project_id}/issues", response_model=PageResponse[IssueResponse])
def list_issues(
    project_id: str,
    principal: Principal,
    q: str | None = None,
    status: str | None = None,
    connectionId: UUID | None = None,  # noqa: N803 — 화면 계약 이름
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResponse[IssueResponse]:
    """일반 이슈 화면. 도구에서 승격된 작업·결함이 여기로 나온다.

    명세서 전에 이슈로 만든 요구사항의 출처 이슈는 requirements 쪽이라 여기 없다.
    connectionId 는 사업 안에서만 거른다. 사업 접근 검사는 그대로 먼저 한다.
    """
    with tx() as cur:
        return service.list_issues(
            cur, principal, project_id, q, status, PageQuery(page=page, size=size),
            str(connectionId) if connectionId else None,
        )


@router.get("/{project_id}/issues/summary", response_model=IssueSummaryResponse)
def issue_summary(
    project_id: str,
    principal: Principal,
    connectionId: UUID | None = None,  # noqa: N803
) -> IssueSummaryResponse:
    """일반 이슈 화면 카드. 목록 페이지와 상관없이 사업 전체를 센다."""
    with tx() as cur:
        return service.issue_summary(
            cur, principal, project_id, str(connectionId) if connectionId else None
        )


class RejectRequest(BaseModel):
    reason: str


@router.post("/{project_id}/work-products/{work_product_id}/approve", status_code=204)
def approve_work_product(project_id: str, work_product_id: str, principal: Principal) -> Response:
    """발주기관이 현행 버전 하나를 승인한다. 문서 확정과 다른 행위다."""
    with tx() as cur:
        approval.approve(cur, principal, project_id, work_product_id)
    return Response(status_code=204)


@router.post("/{project_id}/work-products/{work_product_id}/reject", status_code=204)
def reject_work_product(
    project_id: str, work_product_id: str, req: RejectRequest, principal: Principal
) -> Response:
    """발주기관이 현행 버전 하나를 반려한다. 사유가 있어야 한다."""
    with tx() as cur:
        approval.reject(cur, principal, project_id, work_product_id, req.reason)
    return Response(status_code=204)


@router.get("/{project_id}/work-products", response_model=WorkProductChecklistResponse)
def list_work_products(
    project_id: str, principal: Principal
) -> WorkProductChecklistResponse:
    """산출물 체크리스트. 저장소에서 수집한 파일도 여기 항목을 채운다."""
    with tx() as cur:
        return service.work_product_checklist(cur, principal, project_id)
