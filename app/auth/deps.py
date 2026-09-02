"""Bearer 토큰에서 호출자를 꺼낸다. Spring Security JwtAuthenticationFilter 자리다."""

from typing import Annotated

from fastapi import Depends, Request

from app.auth import jwt_codec
from app.auth.models import AuthPrincipal
from app.common import errors


def current_principal(request: Request) -> AuthPrincipal:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise errors.unauthorized()
    claims = jwt_codec.verify(header[7:].strip())
    try:
        return AuthPrincipal(
            user_id=claims["sub"],
            org_id=claims["orgId"],
            org_type=claims["orgType"],
            role=claims["role"],
        )
    except KeyError as exc:
        raise errors.token_invalid() from exc


Principal = Annotated[AuthPrincipal, Depends(current_principal)]
