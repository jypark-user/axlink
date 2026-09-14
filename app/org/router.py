"""/api/users — 읽기 전용 계정 목록. 프런트 contractor-picker.tsx 가 부른다."""

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.org import service
from app.org.models import UserResponse

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users", response_model=PageResponse[UserResponse])
def list_users(
    principal: Principal,
    role: str | None = None,
    status: str | None = None,
    organizationId: str | None = None,  # noqa: N803 — 프런트 쿼리 파라미터명
    q: str | None = None,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResponse[UserResponse]:
    with tx() as cur:
        return service.list_users(
            cur, principal, role, status, organizationId, q, PageQuery(page=page, size=size)
        )
