"""커넥터 DTO. 필드명은 프런트 types/api.ts 계약과 1:1 이다."""

from pydantic import BaseModel, Field

TOOLS = ("GITHUB", "REDMINE")


class ToolCredentialRequest(BaseModel):
    accessToken: str  # noqa: N815 — 프런트 계약 필드명


class ToolConnectionTestRequest(BaseModel):
    tool: str
    baseUrl: str  # noqa: N815
    targetResource: str  # noqa: N815
    credential: ToolCredentialRequest


class ToolConnectionTestResponse(BaseModel):
    reachable: bool
    resourceName: str  # noqa: N815
    detectedItemTypes: list[str]  # noqa: N815
    checkedAt: str  # noqa: N815


class ToolConnectionCreateRequest(BaseModel):
    tool: str
    name: str = Field(min_length=1)
    baseUrl: str = Field(min_length=1)  # noqa: N815
    targetResource: str = Field(min_length=1)  # noqa: N815
    credential: ToolCredentialRequest


class ToolConnectionStatusUpdateRequest(BaseModel):
    status: str  # ACTIVE | PAUSED


class ToolConnectionResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815
    tool: str
    name: str
    baseUrl: str  # noqa: N815
    targetResource: str  # noqa: N815
    credentialMasked: str  # noqa: N815
    status: str
    lastSyncedAt: str | None  # noqa: N815
    lastSyncStatus: str | None  # noqa: N815
    lastSyncError: str | None  # noqa: N815
    ingestedCount: int  # noqa: N815
    mappingRuleCount: int  # noqa: N815
    createdAt: str  # noqa: N815
