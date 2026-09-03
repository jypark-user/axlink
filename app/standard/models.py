"""표준 모델 조회 DTO. 프런트 types/api.ts 와 필드가 1:1 이어야 한다."""

from pydantic import BaseModel


class SourceRef(BaseModel):
    """이 레코드가 어느 도구의 무엇에서 왔는지. SWFR.PIP.002 의 원천 보존이 이 필드다."""

    tool: str  # GITHUB | REDMINE | UPLOAD | MANUAL
    connectionId: str | None  # noqa: N815 — 프런트 계약 필드명
    externalId: str | None  # noqa: N815
    externalUrl: str | None  # noqa: N815


class RequirementResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815
    code: str
    title: str
    priority: str
    status: str
    assignee: str | None
    source: SourceRef
    traceComplete: bool  # noqa: N815
    updatedAt: str  # noqa: N815
