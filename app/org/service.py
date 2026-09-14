"""계정 목록. 사업 등록 화면이 용역사 이름으로 계정을 찾을 때 쓴다.

계정·조직 관리 기능은 범위 밖이다(요구사항정의서 10절). 여기는 읽기만 있다.
"""

from typing import Any

from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.org import repository
from app.org.models import UserResponse


def list_users(
    cur: Any,
    principal: AuthPrincipal,
    role: str | None,
    status: str | None,
    org_id: str | None,
    q: str | None,
    page: PageQuery,
) -> PageResponse[UserResponse]:
    if principal.role not in ("CLIENT", "SUPER_ADMIN"):
        raise errors.ApiError(403, "FORBIDDEN", "발주기관 계정만 볼 수 있습니다.")
    total = repository.count_users(cur, role, status, org_id, q)
    rows = repository.search_users(cur, role, status, org_id, q, page)
    content = [
        UserResponse(
            id=str(r["id"]),
            organizationId=str(r["organization_id"]),
            organizationName=r["organization_name"],
            username=r["username"],
            name=r["name"],
            role=r["role"],
            status=r["status"],
            lastLoginAt=r["last_login_at"].isoformat() if r["last_login_at"] else None,
            createdAt=r["created_at"].isoformat(),
        )
        for r in rows
    ]
    return PageResponse.of(content, page, total)
