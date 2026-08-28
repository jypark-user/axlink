"""/api/projects — 프런트 project-list-page.tsx 가 q·page·size 로 부른다."""

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.project import service
from app.project.models import ProjectSummaryResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=PageResponse[ProjectSummaryResponse])
def list_projects(
    principal: Principal,
    q: str | None = None,
    status: str | None = None,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    sort: str | None = None,
) -> PageResponse[ProjectSummaryResponse]:
    with tx() as cur:
        return service.list_projects(
            cur, principal, status, q, PageQuery(page=page, size=size, sort=sort)
        )
