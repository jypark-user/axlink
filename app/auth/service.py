"""로그인·리프레시·로그아웃. 파일럿 AuthService 의 동작을 그대로 옮겼다.

리프레시 토큰은 쓰는 즉시 폐기하고 새로 발급한다(회전). 프런트 lib/http.ts 가
리프레시를 한 번에 하나만 보내는 것도 같은 이유다.
"""

from datetime import UTC, datetime
from typing import Any

import bcrypt

from app.auth import jwt_codec, repository, throttle
from app.auth.models import (
    AcceptInvitationRequest,
    AuthPrincipal,
    InvitationPreviewResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordChangeRequest,
)
from app.common import errors
from app.common.hashes import random_token, sha256_hex
from app.config import settings
from app.project import participants
from app.project import repository as project_repository

# 09.17 실측(Windows · Python 3.13 · bcrypt 4.0~4.3): hashpw 가 같은 입력에 다른 값을 내는
# 일이 있다. 4.3.0 은 500번 중 80번, 4.2.1 은 1번. Python 3.9 에서는 300번 중 0번이라
# 3.13 빌드의 문제다. 틀린 비밀번호가 통과하는 쪽으로는 한 번도 흔들리지 않았으므로,
# 거부됐을 때만 몇 번 더 확인한다. 정상 환경에서는 첫 번에 끝나 비용이 없다.
_VERIFY_ATTEMPTS = 5


def _verify_password(raw: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        for _ in range(_VERIFY_ATTEMPTS):
            if bcrypt.checkpw(raw.encode("utf-8"), stored_hash.encode("utf-8")):
                return True
        return False
    except ValueError:
        # 해시 형식이 깨진 계정이다. 인증 실패로 다룬다.
        return False


def login(cur: Any, req: LoginRequest, user_agent: str | None) -> LoginResponse:
    wait = throttle.locked_for(req.username)
    if wait:
        # 잠긴 동안은 비밀번호를 확인하지 않는다. 맞는지 틀린지 알려 주지 않기 위해서다
        raise errors.ApiError(
            429,
            "LOGIN_LOCKED",
            f"로그인 실패가 이어져 잠시 막았습니다. {(wait + 59) // 60}분 뒤에 다시 시도하십시오.",
        )
    user = repository.find_user_by_username(cur, req.username)
    if user is None or not _verify_password(req.password, user["password_hash"]):
        throttle.fail(req.username)
        raise errors.credentials_invalid()
    if user["status"] != "ACTIVE":
        raise errors.credentials_invalid()
    throttle.succeed(req.username)
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
        contractorOrgName=invite.get("contractor_org_name"),
    )


def accept_invitation(
    cur: Any, req: AcceptInvitationRequest, user_agent: str | None
) -> LoginResponse:
    """용역사가 직접 계정을 만들고 그 사업에 붙는다(S2-1). 링크는 소진되지 않는다.

    업체를 지정한 초대(GH-138)면 적은 회사명과 상관없이 그 업체로 들어간다. 지정하지 않은
    (V54 이전) 초대는 새 업체 등록만 받는다. 이미 있는 회사명을 적어 그 업체에 끼어드는 것을
    막는다 — 업체 이름만 알면 다른 업체의 연결 권한을 얻게 되기 때문이다.
    """
    now = datetime.now(UTC)
    invite = _valid_invite(cur, req.token, now)
    org_name = (req.contractorOrgName or "").strip()
    username = (req.username or "").strip()
    name = (req.name or "").strip()
    bound = invite.get("organization_id")
    if (not bound and not org_name) or not username or not name:
        raise errors.validation_failed("회사명·아이디·이름을 모두 입력하세요.")
    if repository.find_user_by_username(cur, username) is not None:
        raise errors.validation_failed("이미 쓰고 있는 아이디입니다.")

    project_id = str(invite["project_id"])
    if bound:
        if participants.active_participant(cur, project_id, str(bound)) is None:
            raise errors.ApiError(
                404, "NOT_FOUND", "초대한 업체가 이 사업에서 빠졌습니다. 새 초대 링크를 받으세요."
            )
        org_id = str(bound)
    else:
        org = project_repository.find_organization_by_name(cur, org_name)
        if org is not None and org["type"] != "CONTRACTOR":
            raise errors.validation_failed("용역사 회사명이 아닙니다.")
        if org is not None:
            raise errors.ApiError(
                409, "ORGANIZATION_EXISTS",
                "이미 등록된 업체입니다. 발주기관에 업체를 지정한 초대 링크를 요청하세요.",
            )
        org_id = project_repository.insert_organization(cur, org_name, "CONTRACTOR")
    participants.ensure(cur, project_id, org_id, None)

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


def change_password(cur: Any, principal: AuthPrincipal, req: PasswordChangeRequest) -> None:
    """지금 비밀번호를 맞춰야 바꾼다. 다른 기기의 로그인은 그대로 둔다."""
    user = repository.find_user_by_id(cur, principal.user_id)
    if user is None or not _verify_password(req.currentPassword, user["password_hash"]):
        raise errors.ApiError(400, "PASSWORD_MISMATCH", "지금 비밀번호가 맞지 않습니다.")
    if req.newPassword == req.currentPassword:
        raise errors.validation_failed("지금과 다른 비밀번호를 입력하세요.")
    if len(req.newPassword.encode("utf-8")) > 72:
        raise errors.validation_failed("비밀번호가 너무 깁니다.")
    password_hash = bcrypt.hashpw(req.newPassword.encode("utf-8"), bcrypt.gensalt()).decode()
    cur.execute(
        "update app_user set password_hash = %s, updated_at = now() where id = %s",
        (password_hash, principal.user_id),
    )

