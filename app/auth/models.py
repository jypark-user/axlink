"""인증 DTO. 필드명은 프런트 types/api.ts 와 1:1 이어야 한다 — camelCase 그대로 쓴다."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # 형식을 강요하지 않는다. 이메일 주소를 아이디로 쓰는 것도 그대로 된다.
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1)


class RefreshTokenRequest(BaseModel):
    refreshToken: str | None = None  # noqa: N815 — 프런트 계약 필드명


class MeResponse(BaseModel):
    userId: str  # noqa: N815
    username: str
    name: str
    role: str
    organizationId: str  # noqa: N815
    organizationName: str  # noqa: N815
    organizationType: str  # noqa: N815
    allowedProjectIds: list[str]  # noqa: N815


class LoginResponse(BaseModel):
    accessToken: str  # noqa: N815
    refreshToken: str  # noqa: N815
    expiresIn: int  # noqa: N815
    user: MeResponse


class AuthPrincipal(BaseModel):
    user_id: str
    org_id: str
    org_type: str
    role: str
