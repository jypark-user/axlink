"""/api/auth — 프런트 api/auth.ts 가 부르는 경로 그대로다."""

from fastapi import APIRouter, Header, Response

from app.auth import service
from app.auth.deps import Principal
from app.auth.models import LoginRequest, LoginResponse, MeResponse, RefreshTokenRequest
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
