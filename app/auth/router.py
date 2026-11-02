"""/api/auth — 프런트 api/auth.ts 가 부르는 경로 그대로다."""

from fastapi import APIRouter, Header, Response

from app.auth import service
from app.auth.deps import Principal
from app.auth.models import (
    AcceptInvitationRequest,
    InvitationPreviewResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordChangeRequest,
    RefreshTokenRequest,
)
from app.db import tx

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, user_agent: str | None = Header(default=None)) -> LoginResponse:
    with tx() as cur:
        return service.login(cur, req, user_agent)


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    req: RefreshTokenRequest, user_agent: str | None = Header(default=None)
) -> LoginResponse:
    with tx() as cur:
        return service.refresh(cur, req.refreshToken, user_agent)


@router.post("/logout", status_code=204, response_class=Response)
def logout(principal: Principal, req: RefreshTokenRequest | None = None) -> Response:
    with tx() as cur:
        service.logout(cur, req.refreshToken if req else None, principal)
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
def me(principal: Principal) -> MeResponse:
    with tx() as cur:
        return service.me(cur, principal)


@router.get("/invitations/{token}", response_model=InvitationPreviewResponse)
def preview_invitation(token: str) -> InvitationPreviewResponse:
    """로그인 전에 부른다. 토큰만으로 어느 사업 초대인지 보여 준다."""
    with tx() as cur:
        return service.preview_invitation(cur, token)


@router.post("/invitations/accept", response_model=LoginResponse)
def accept_invitation(
    req: AcceptInvitationRequest, user_agent: str | None = Header(default=None)
) -> LoginResponse:
    with tx() as cur:
        return service.accept_invitation(cur, req, user_agent)


@router.post("/password", status_code=204, response_class=Response)
def change_password(principal: Principal, req: PasswordChangeRequest) -> Response:
    """자기 비밀번호 바꾸기. 발급받은 첫 비밀번호를 받은 사람이 바꾼다."""
    with tx() as cur:
        service.change_password(cur, principal, req)
    return Response(status_code=204)

