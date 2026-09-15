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


class IssueResponse(BaseModel):
    """작업·결함 한 건. 도구가 달라도 같은 모양이다(GitHub 이슈, Redmine 작업·결함)."""

    id: str
    projectId: str  # noqa: N815
    key: str
    title: str
    status: str
    severity: str | None
    assignee: str | None
    resolvedAt: str | None  # noqa: N815
    source: SourceRef
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


class TraceLinkResponse(BaseModel):
    """추적관계 하나. externalUrl 은 근거가 적힌 원문의 위치다(SWFR.PIP.004)."""

    id: str
    projectId: str  # noqa: N815
    fromType: str  # noqa: N815
    fromId: str  # noqa: N815
    fromLabel: str  # noqa: N815
    toType: str  # noqa: N815
    toId: str  # noqa: N815
    toLabel: str  # noqa: N815
    linkKind: str  # noqa: N815
    origin: str  # AUTO | MANUAL
    status: str  # ACTIVE | BROKEN
    evidenceKind: str | None  # noqa: N815
    evidenceText: str | None  # noqa: N815
    externalUrl: str | None  # noqa: N815
    createdAt: str  # noqa: N815


class TraceCell(BaseModel):
    targetId: str  # noqa: N815
    label: str
    externalUrl: str | None  # noqa: N815


class TraceabilityRowResponse(BaseModel):
    """추적표 한 줄. 요구사항 하나에 설계·구현·시험 칸이 붙는다."""

    requirementId: str  # noqa: N815
    requirementCode: str  # noqa: N815
    requirementTitle: str  # noqa: N815
    requirementStatus: str  # noqa: N815
    designs: list[TraceCell]
    implementsList: list[TraceCell]  # noqa: N815 — implements 는 예약어라 프런트가 이렇게 부른다
    tests: list[TraceCell]
    brokenAt: list[str]  # noqa: N815


class EntityHistoryResponse(BaseModel):
    id: str
    entityType: str  # noqa: N815
    entityId: str  # noqa: N815
    field: str
    fromValue: str | None  # noqa: N815
    toValue: str | None  # noqa: N815
    actor: str
    actorName: str | None  # noqa: N815
    changedAt: str  # noqa: N815


class RequirementDetailResponse(RequirementResponse):
    body: str
    traceLinks: list[TraceLinkResponse]  # noqa: N815
    history: list[EntityHistoryResponse]
