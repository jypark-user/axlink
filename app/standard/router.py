"""/api/projects/{id}/requirements — 표준 모델 조회.

프런트 project-overview-page.tsx 와 requirements 화면이 같은 경로를 쓴다.
"""

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.standard import service
from app.standard.models import (
    IssueResponse,
    RequirementResponse,
    WorkProductChecklistResponse,
)

router = APIRouter(prefix="/api/projects", tags=["requirements"])


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
