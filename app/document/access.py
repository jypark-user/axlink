"""문서 API 의 접근 범위. 문서는 사업에 속하므로 사업 접근 권한이 곧 문서 접근 권한이다."""

from typing import Any

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors


def require_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
