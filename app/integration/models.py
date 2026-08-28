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
    deniedItemTypes: list[str] = []  # noqa: N815 — 토큰에 권한이 빠진 항목
    checkedAt: str  # noqa: N815


class ToolConnectionCreateRequest(BaseModel):
    tool: str
    name: str = Field(min_length=1)
    baseUrl: str = Field(min_length=1)  # noqa: N815
    targetResource: str = Field(min_length=1)  # noqa: N815
    credential: ToolCredentialRequest


class ToolConnectionStatusUpdateRequest(BaseModel):
    status: str  # ACTIVE | PAUSED


class SyncJobStats(BaseModel):
    fetched: int = 0
    upserted: int = 0
    unmapped: int = 0
    indexed: int = 0
    skippedUnchanged: int = 0  # noqa: N815


class SyncJobResponse(BaseModel):
    id: str
    connectionId: str  # noqa: N815
    connectionName: str  # noqa: N815
    projectId: str  # noqa: N815
    tool: str
    kind: str
    status: str
    startedAt: str | None  # noqa: N815
    finishedAt: str | None  # noqa: N815
    stats: SyncJobStats
    error: str | None
    retryable: bool


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
