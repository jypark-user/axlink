"""로그인·리프레시·로그아웃. 파일럿 AuthService 의 동작을 그대로 옮겼다.

리프레시 토큰은 쓰는 즉시 폐기하고 새로 발급한다(회전). 프런트 lib/http.ts 가
리프레시를 한 번에 하나만 보내는 것도 같은 이유다.
"""

from datetime import UTC, datetime
from typing import Any

import bcrypt

from app.auth import jwt_codec, repository
from app.auth.models import (
    AcceptInvitationRequest,
    AuthPrincipal,
    InvitationPreviewResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
)
from app.common import errors
from app.common.hashes import random_token, sha256_hex
from app.config import settings
from app.project import repository as project_repository


def _verify_password(raw: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        # 해시 형식이 깨진 계정이다. 인증 실패로 다룬다.
        return False


def login(cur: Any, req: LoginRequest, user_agent: str | None) -> LoginResponse:
    user = repository.find_user_by_username(cur, req.username)
    if user is None or not _verify_password(req.password, user["password_hash"]):
        raise errors.credentials_invalid()
    if user["status"] != "ACTIVE":
        raise errors.credentials_invalid()
    now = datetime.now(UTC)
    repository.touch_last_login(cur, user["id"], now)
    return _issue(cur, user, now, user_agent)


def refresh(cur: Any, refresh_token: str | None, user_agent: str | None) -> LoginResponse:
    if not refresh_token:
        raise errors.token_invalid()
    now = datetime.now(UTC)
    stored = repository.find_refresh_token(cur, sha256_hex(refresh_token))
    if stored is None or stored["revoked_at"] is not None or stored["expires_at"] <= now:
        raise errors.token_invalid()
    user = repository.find_user_by_id(cur, stored["app_user_id"])
    if user is None or user["status"] != "ACTIVE":
        raise errors.token_invalid()
    repository.revoke_refresh_token(cur, stored["id"], now)
    return _issue(cur, user, now, user_agent)


def logout(cur: Any, refresh_token: str | None, principal: AuthPrincipal) -> None:
    now = datetime.now(UTC)
    if not refresh_token:
        repository.revoke_all_for_user(cur, principal.user_id, now)
        return
    stored = repository.find_refresh_token(cur, sha256_hex(refresh_token))
    if stored is not None and str(stored["app_user_id"]) == principal.user_id:
        repository.revoke_refresh_token(cur, stored["id"], now)


def me(cur: Any, principal: AuthPrincipal) -> MeResponse:
    user = repository.find_user_by_id(cur, principal.user_id)
    if user is None:
        raise errors.token_invalid()
    return _to_me(cur, user, _organization(cur, user))


def _valid_invite(cur: Any, token: str, now: datetime) -> dict[str, Any]:
    invite = project_repository.find_invite_by_hash(cur, sha256_hex(token))
    if invite is None or invite["revoked_at"] is not None or invite["expires_at"] <= now:
        raise errors.ApiError(404, "NOT_FOUND", "초대 링크가 유효하지 않거나 만료되었습니다.")
    return invite


def preview_invitation(cur: Any, token: str) -> InvitationPreviewResponse:
    """로그인 전에 부른다. 어느 사업의 초대인지만 보여 주고 다른 것은 내지 않는다."""
    invite = _valid_invite(cur, token, datetime.now(UTC))
    return InvitationPreviewResponse(
        kind="PROJECT",
        projectName=invite["project_name"],
        organizationName=invite["client_org_name"],
        username=None,
        name=None,
        expiresAt=invite["expires_at"].isoformat(),
    )


def accept_invitation(
    cur: Any, req: AcceptInvitationRequest, user_agent: str | None
) -> LoginResponse:
    """용역사가 직접 계정을 만들고 그 사업에 붙는다(S2-1). 링크는 소진되지 않는다.

    회사명이 이미 있으면 그 조직에 넣는다. 발주사 이름을 적으면 거절한다.
    """
    now = datetime.now(UTC)
    invite = _valid_invite(cur, req.token, now)
    org_name = (req.contractorOrgName or "").strip()
    username = (req.username or "").strip()
    name = (req.name or "").strip()
    if not org_name or not username or not name:
        raise errors.validation_failed("회사명·아이디·이름을 모두 입력하세요.")
    if repository.find_user_by_username(cur, username) is not None:
        raise errors.validation_failed("이미 쓰고 있는 아이디입니다.")

    org = project_repository.find_organization_by_name(cur, org_name)
    if org is None:
        org_id = project_repository.insert_organization(cur, org_name, "CONTRACTOR")
    elif org["type"] != "CONTRACTOR":
        raise errors.validation_failed("용역사 회사명이 아닙니다.")
    else:
        org_id = str(org["id"])

    password_hash = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode()
    user_id = project_repository.insert_user(
        cur, org_id, username, name, password_hash, "CONTRACTOR"
    )
    project_repository.insert_assignment(
        cur, str(invite["project_id"]), org_id, user_id, str(invite["created_by_user_id"])
    )
    user = repository.find_user_by_id(cur, user_id)
    repository.touch_last_login(cur, user["id"], now)
    return _issue(cur, user, now, user_agent)


def _issue(cur: Any, user: dict[str, Any], now: datetime, user_agent: str | None) -> LoginResponse:
    org = _organization(cur, user)
    expiry = now + settings.access_ttl
    access_token = jwt_codec.sign(
        jwt_codec.access_claims(
            str(user["id"]), str(org["id"]), org["type"], user["role"], now, expiry
        )
    )
    refresh_token = random_token()
    repository.insert_refresh_token(
        cur, user["id"], sha256_hex(refresh_token), now + settings.refresh_ttl, user_agent
    )
    return LoginResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        expiresIn=int(settings.access_ttl.total_seconds()),
        user=_to_me(cur, user, org),
    )


def _to_me(cur: Any, user: dict[str, Any], org: dict[str, Any]) -> MeResponse:
    project_ids = repository.allowed_project_ids(
        cur, user["role"], str(user["organization_id"]), str(user["id"])
    )
    return MeResponse(
        userId=str(user["id"]),
        username=user["username"],
        name=user["name"],
        role=user["role"],
        organizationId=str(org["id"]),
        organizationName=org["name"],
        organizationType=org["type"],
        allowedProjectIds=project_ids,
    )


def _organization(cur: Any, user: dict[str, Any]) -> dict[str, Any]:
    org = repository.find_organization(cur, user["organization_id"])
    if org is None:
        raise errors.ApiError(500, "INTERNAL", "계정의 조직 정보를 찾을 수 없습니다.")
    return org
