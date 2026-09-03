"""/api/projects/{id}/requirements — 표준 모델 조회.

프런트 project-overview-page.tsx 와 requirements 화면이 같은 경로를 쓴다.
"""

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.standard import service
from app.standard.models import RequirementResponse

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
