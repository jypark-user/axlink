"""발주기관 조직과 담당자 계정 발급 (GH-187, SER.SEC.003).

용역사는 사업 초대 링크로 가입하면서 조직이 함께 생긴다. 발주기관에는 그런 길이 없어서, 새
발주기관을 들이거나 담당자가 바뀔 때마다 서버 안에서 손으로 넣어야 했다. 여기서는 최고관리자가
발주기관 조직을 만들고 그 담당자 계정을 발급·중지한다.

- 첫 비밀번호는 서버가 만들어 응답에 한 번만 담는다. 저장은 해시로만 하고 로그에 남기지 않는다.
  받은 사람은 로그인 뒤 스스로 바꾼다(`POST /api/auth/password`).
- 용역사 조직·계정은 여기서 만들지 않는다. 초대 링크 경로를 그대로 쓴다.
- 계정은 지우지 않고 중지한다. 판정·승인 기록의 행위자가 남아야 한다. 중지하면 로그인과 토큰
  갱신이 막힌다.
- 만들기·이름 변경·중지·재개는 변경 이력(entity_history)에 남는다.
"""

import secrets
from datetime import UTC, datetime
from typing import Any

import bcrypt
import psycopg
from pydantic import BaseModel, Field

from app.auth import repository as auth_repository
from app.auth import throttle
from app.auth.models import AuthPrincipal
from app.common import errors
from app.db import fetch_all, fetch_one
from app.project import repository as project_repository
from app.standard import repository as standard_repository

USER_STATUSES = ("ACTIVE", "DISABLED")


class OrganizationResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    userCount: int  # noqa: N815
    activeUserCount: int  # noqa: N815
    projectCount: int  # noqa: N815
    createdAt: str  # noqa: N815


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ClientUserCreateRequest(BaseModel):
    organizationId: str  # noqa: N815
    username: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=100)


class ClientUserCreatedResponse(BaseModel):
    id: str
    organizationId: str  # noqa: N815
    username: str
    name: str
    role: str
    status: str
    # 이 응답에만 있다. 다시 볼 수 없다
    temporaryPassword: str  # noqa: N815


class UserStatusRequest(BaseModel):
    status: str


def require_admin(principal: AuthPrincipal) -> None:
    if principal.role != "SUPER_ADMIN":
        raise errors.ApiError(403, "FORBIDDEN", "플랫폼 관리자만 할 수 있습니다.")


def _actor(cur: Any, principal: AuthPrincipal) -> str:
    row = fetch_one(cur, "select name from app_user where id = %s", (principal.user_id,))
    return (row or {}).get("name") or "플랫폼 관리자"


def _history(cur: Any, principal: AuthPrincipal, entity_type: str, entity_id: str,
             field: str, before: str | None, after: str | None) -> None:
    standard_repository.insert_entity_history(
        cur, entity_type=entity_type, entity_id=entity_id, project_id=None, field=field,
        from_value=before, to_value=after, actor=_actor(cur, principal),
    )


def list_organizations(
    cur: Any, principal: AuthPrincipal, org_type: str | None
) -> list[OrganizationResponse]:
    require_admin(principal)
    rows = fetch_all(
        cur,
        """
        select o.id, o.name, o.type, o.status, o.created_at,
               (select count(*) from app_user u where u.organization_id = o.id) as users,
               (select count(*) from app_user u
                 where u.organization_id = o.id and u.status = 'ACTIVE') as active_users,
               (select count(*) from project p where p.client_org_id = o.id) as projects
          from organization o
         where (%(type)s::text is null or o.type = %(type)s)
         order by o.type, o.name
        """,
        {"type": org_type},
    )
    return [_org(r) for r in rows]


def _org(r: dict[str, Any]) -> OrganizationResponse:
    return OrganizationResponse(
        id=str(r["id"]), name=r["name"], type=r["type"], status=r["status"],
        userCount=r["users"], activeUserCount=r["active_users"], projectCount=r["projects"],
        createdAt=r["created_at"].isoformat(),
    )


def _find_org(cur: Any, org_id: str) -> dict[str, Any]:
    row = fetch_one(
        cur,
        """
        select o.id, o.name, o.type, o.status, o.created_at,
               (select count(*) from app_user u where u.organization_id = o.id) as users,
               (select count(*) from app_user u
                 where u.organization_id = o.id and u.status = 'ACTIVE') as active_users,
               (select count(*) from project p where p.client_org_id = o.id) as projects
          from organization o where o.id::text = %s
        """,
        (org_id,),
    )
    if row is None:
        raise errors.not_found("조직", org_id)
    return row


def create_organization(
    cur: Any, principal: AuthPrincipal, req: OrganizationCreateRequest
) -> OrganizationResponse:
    require_admin(principal)
    name = req.name.strip()
    if not name:
        raise errors.validation_failed("기관 이름을 입력하세요.")
    if project_repository.find_organization_by_name(cur, name) is not None:
        raise errors.ApiError(409, "ORGANIZATION_EXISTS", "같은 이름의 조직이 이미 있습니다.")
    org_id = project_repository.insert_organization(cur, name, "CLIENT")
    _history(cur, principal, "ORGANIZATION", org_id, "created", None, name)
    return _org(_find_org(cur, org_id))


def rename_organization(
    cur: Any, principal: AuthPrincipal, org_id: str, req: OrganizationUpdateRequest
) -> OrganizationResponse:
    require_admin(principal)
    org = _find_org(cur, org_id)
    if org["type"] != "CLIENT":
        raise errors.ApiError(
            409, "NOT_CLIENT_ORG", "용역사 조직 이름은 여기서 바꾸지 않습니다."
        )
    name = req.name.strip()
    if not name:
        raise errors.validation_failed("기관 이름을 입력하세요.")
    if name != org["name"]:
        other = project_repository.find_organization_by_name(cur, name)
        if other is not None:
            raise errors.ApiError(409, "ORGANIZATION_EXISTS", "같은 이름의 조직이 이미 있습니다.")
        cur.execute(
            "update organization set name = %s, updated_at = now() where id = %s", (name, org_id)
        )
        _history(cur, principal, "ORGANIZATION", org_id, "name", org["name"], name)
    return _org(_find_org(cur, org_id))


def create_client_user(
    cur: Any, principal: AuthPrincipal, req: ClientUserCreateRequest
) -> ClientUserCreatedResponse:
    require_admin(principal)
    org = _find_org(cur, req.organizationId)
    if org["type"] != "CLIENT":
        raise errors.ApiError(
            409, "NOT_CLIENT_ORG", "용역사 계정은 사업 초대 링크로 가입합니다."
        )
    if org["status"] != "ACTIVE":
        raise errors.ApiError(
            409, "ORGANIZATION_DISABLED", "중지된 조직에는 계정을 만들 수 없습니다."
        )
    username, name = req.username.strip(), req.name.strip()
    if not name:
        raise errors.validation_failed("이름을 입력하세요.")
    temporary = secrets.token_urlsafe(12)
    password_hash = bcrypt.hashpw(temporary.encode("utf-8"), bcrypt.gensalt()).decode()
    try:
        with cur.connection.transaction():
            user_id = project_repository.insert_user(
                cur, str(org["id"]), username, name, password_hash, "CLIENT"
            )
    except psycopg.errors.UniqueViolation as exc:
        raise errors.ApiError(409, "USERNAME_EXISTS", "이미 쓰고 있는 아이디입니다.") from exc
    _history(cur, principal, "APP_USER", user_id, "created", None, f"{username} ({org['name']})")
    return ClientUserCreatedResponse(
        id=user_id, organizationId=str(org["id"]), username=username, name=name,
        role="CLIENT", status="ACTIVE", temporaryPassword=temporary,
    )


def set_user_status(
    cur: Any, principal: AuthPrincipal, user_id: str, req: UserStatusRequest
) -> None:
    require_admin(principal)
    if req.status not in USER_STATUSES:
        raise errors.validation_failed("상태는 ACTIVE 또는 DISABLED 입니다.")
    if user_id == principal.user_id:
        raise errors.ApiError(409, "SELF_STATUS", "자기 계정은 중지할 수 없습니다.")
    user = fetch_one(
        cur, "select id, role, status from app_user where id::text = %s", (user_id,)
    )
    if user is None:
        raise errors.not_found("계정", user_id)
    if user["role"] == "SUPER_ADMIN":
        raise errors.ApiError(409, "ADMIN_STATUS", "플랫폼 관리자 계정은 여기서 바꾸지 않습니다.")
    if user["status"] == req.status:
        return
    cur.execute(
        "update app_user set status = %s, updated_at = now() where id = %s", (req.status, user_id)
    )
    _history(cur, principal, "APP_USER", user_id, "status", user["status"], req.status)


def reset_password(cur: Any, principal: AuthPrincipal, user_id: str) -> ClientUserCreatedResponse:
    """임시 비밀번호를 다시 발급한다(IM-002 AC-001-5, GH-206).

    새 비밀번호는 이 응답에만 담는다. 옛 비밀번호와 살아 있는 갱신 토큰은 전부 무효가 된다.
    발급 사실은 이력에 남기되 비밀번호 자체는 어디에도 적지 않는다.
    """
    require_admin(principal)
    if user_id == principal.user_id:
        raise errors.ApiError(409, "SELF_RESET", "자기 비밀번호는 비밀번호 바꾸기에서 바꿉니다.")
    user = fetch_one(
        cur,
        """
        select u.id, u.organization_id, u.username, u.name, u.role, u.status
          from app_user u
         where u.id::text = %s
        """,
        (user_id,),
    )
    if user is None:
        raise errors.not_found("계정", user_id)
    if user["role"] == "SUPER_ADMIN":
        raise errors.ApiError(
            409, "ADMIN_RESET", "플랫폼 관리자 계정은 여기서 재설정하지 않습니다."
        )
    temporary = secrets.token_urlsafe(12)
    password_hash = bcrypt.hashpw(temporary.encode("utf-8"), bcrypt.gensalt()).decode()
    cur.execute(
        "update app_user set password_hash = %s, updated_at = now() where id = %s",
        (password_hash, user_id),
    )
    auth_repository.revoke_all_for_user(cur, user_id, datetime.now(UTC))
    throttle.succeed(user["username"])  # 실패가 쌓여 잠긴 계정도 새 비밀번호로 바로 들어온다
    _history(cur, principal, "APP_USER", user_id, "password_reset", None, "임시 비밀번호 재발급")
    return ClientUserCreatedResponse(
        id=str(user["id"]),
        organizationId=str(user["organization_id"]),
        username=user["username"],
        name=user["name"],
        role=user["role"],
        status=user["status"],
        temporaryPassword=temporary,
    )
