"""액세스 토큰 서명·검증. 클레임은 파일럿 JwtCodec 과 동일하게 맞춘다.

    sub · orgId · orgType · role · iss · iat · exp
"""

from datetime import datetime
from typing import Any

import jwt

from app.common import errors
from app.config import settings

_ALGORITHM = "HS256"


def sign(claims: dict[str, Any]) -> str:
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def verify(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise errors.token_invalid() from exc


def access_claims(
    user_id: str, org_id: str, org_type: str, role: str, now: datetime, expiry: datetime
) -> dict[str, Any]:
    return {
        "sub": user_id,
        "orgId": org_id,
        "orgType": org_type,
        "role": role,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
    }
