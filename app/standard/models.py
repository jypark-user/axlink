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


class WorkProductResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815
    type: str
    displayName: str  # noqa: N815 — 유형의 한글 이름. 화면에 코드가 노출되지 않게 서버가 준다
    title: str | None
    version: str | None
    status: str
    pmActivity: str | None  # noqa: N815
    siActivity: str | None  # noqa: N815
    applicable: bool
    dueDate: str | None  # noqa: N815
    fileUri: str | None  # noqa: N815
    externalUrl: str | None  # noqa: N815
    approvedBy: str | None  # noqa: N815
    approvedAt: str | None  # noqa: N815
    updatedAt: str  # noqa: N815


class WorkProductChecklistResponse(BaseModel):
    """산출물 체크리스트. 22종 항목이 미리 있고 수집·업로드가 그 항목을 채운다."""

    projectId: str  # noqa: N815
    approvedCount: int  # noqa: N815
    totalCount: int  # noqa: N815
    items: list[WorkProductResponse]
