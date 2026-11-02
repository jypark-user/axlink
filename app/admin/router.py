"""최고관리자 운영 화면 API. 서버 오류 기록, 발주기관 조직·계정 발급(GH-187)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app.admin import accounts
from app.auth.deps import Principal
from app.common import error_log, errors
from app.common.paging import PageResponse
from app.db import tx

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ErrorLogResponse(BaseModel):
    id: str
    occurredAt: str  # noqa: N815
    method: str
    path: str
    statusCode: int  # noqa: N815
    code: str
    message: str
    exception: str | None
    traceback: str | None
    username: str | None
    userName: str | None  # noqa: N815


def _require_admin(principal) -> None:
    if principal.role != "SUPER_ADMIN":
        raise errors.ApiError(403, "FORBIDDEN", "플랫폼 관리자만 볼 수 있습니다.")


def _to_response(r: dict[str, Any]) -> ErrorLogResponse:
    return ErrorLogResponse(
        id=str(r["id"]),
        occurredAt=r["occurred_at"].isoformat(),
        method=r["method"],
        path=r["path"],
        statusCode=r["status_code"],
        code=r["code"],
        message=r["message"],
        exception=r["exception"],
        traceback=r["traceback"],
        username=r["username"],
        userName=r["user_name"],
    )


@router.get("/errors", response_model=PageResponse[ErrorLogResponse])
def list_errors(
    principal: Principal,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PageResponse[ErrorLogResponse]:
    """서버 오류 기록. 최근 것이 앞이다."""
    _require_admin(principal)
    with tx() as cur:
        rows, total = error_log.list_recent(cur, page, size)
    from app.common.paging import PageQuery

    return PageResponse.of([_to_response(r) for r in rows], PageQuery(page=page, size=size), total)


@router.delete("/errors", status_code=204)
def clear_errors(principal: Principal) -> None:
    """기록을 비운다. 살펴본 뒤 새 오류만 보려고 쓴다."""
    _require_admin(principal)
    with tx() as cur:
        error_log.clear(cur)


# --- 발주기관 조직·계정 (GH-187) ---------------------------------------------


@router.get("/organizations", response_model=list[accounts.OrganizationResponse])
def list_organizations(
    principal: Principal, type: str | None = None  # noqa: A002 — 화면 쿼리 이름
) -> list[accounts.OrganizationResponse]:
    with tx() as cur:
        return accounts.list_organizations(cur, principal, type)


@router.post("/organizations", response_model=accounts.OrganizationResponse, status_code=201)
def create_organization(
    principal: Principal, req: accounts.OrganizationCreateRequest
) -> accounts.OrganizationResponse:
    with tx() as cur:
        return accounts.create_organization(cur, principal, req)


@router.patch("/organizations/{org_id}", response_model=accounts.OrganizationResponse)
def rename_organization(
    org_id: str, principal: Principal, req: accounts.OrganizationUpdateRequest
) -> accounts.OrganizationResponse:
    with tx() as cur:
        return accounts.rename_organization(cur, principal, org_id, req)


@router.post("/users", response_model=accounts.ClientUserCreatedResponse, status_code=201)
def create_client_user(
    principal: Principal, req: accounts.ClientUserCreateRequest
) -> accounts.ClientUserCreatedResponse:
    """발주기관 담당자 계정. 첫 비밀번호는 이 응답에만 담긴다."""
    with tx() as cur:
        return accounts.create_client_user(cur, principal, req)


@router.patch("/users/{user_id}/status", status_code=204, response_class=Response)
def set_user_status(
    user_id: str, principal: Principal, req: accounts.UserStatusRequest
) -> Response:
    with tx() as cur:
        accounts.set_user_status(cur, principal, user_id, req)
    return Response(status_code=204)

