"""계정 DTO. 프런트 types/api.ts 의 UserResponse 와 1:1 이다."""

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    organizationId: str  # noqa: N815 — 프런트 계약 필드명
    organizationName: str  # noqa: N815
    username: str
    name: str
    role: str
    status: str
    lastLoginAt: str | None  # noqa: N815
    createdAt: str  # noqa: N815
