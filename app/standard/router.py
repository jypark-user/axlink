"""/api/projects/{id}/requirements — 표준 모델 조회.

프런트 project-overview-page.tsx 와 requirements 화면이 같은 경로를 쓴다.
"""

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.standard import service, trace_service
from app.standard.models import (
    IssueResponse,
    RequirementDetailResponse,
    RequirementResponse,
    TraceabilityRowResponse,
    WorkProductChecklistResponse,
)

router = APIRouter(prefix="/api/projects", tags=["requirements"])


@router.get("/{project_id}/traceability", response_model=PageResponse[TraceabilityRowResponse])
def traceability(
    project_id: str,
    principal: Principal,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResponse[TraceabilityRowResponse]:
    """추적표. 요구사항마다 이슈·커밋·산출물이 어느 칸에 걸려 있는지(SWFR.WEB.002)."""
    with tx() as cur:
        return trace_service.traceability_rows(
            cur, principal, project_id, PageQuery(page=page, size=size)
        )


@router.get("/{project_id}/requirements/{requirement_id}", response_model=RequirementDetailResponse)
def requirement_detail(
    project_id: str, requirement_id: str, principal: Principal
) -> RequirementDetailResponse:
    """요구사항 하나와 걸린 링크 전부. 링크마다 근거 원문과 위치가 붙는다."""
    with tx() as cur:
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
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResponse[IssueResponse]:
    """이슈·위험 화면. 도구에서 승격된 작업·결함이 여기로 나온다."""
    with tx() as cur:
        return service.list_issues(
            cur, principal, project_id, q, status, PageQuery(page=page, size=size)
        )


@router.get("/{project_id}/work-products", response_model=WorkProductChecklistResponse)
def list_work_products(
    project_id: str, principal: Principal
) -> WorkProductChecklistResponse:
    """산출물 체크리스트. 저장소에서 수집한 파일도 여기 항목을 채운다."""
    with tx() as cur:
        return service.work_product_checklist(cur, principal, project_id)
