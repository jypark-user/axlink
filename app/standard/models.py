"""표준 모델 조회 DTO. 프런트 types/api.ts 와 필드가 1:1 이어야 한다."""

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """이 레코드가 어느 도구의 무엇에서 왔는지. SWFR.PIP.002 의 원천 보존이 이 필드다."""

    tool: str  # GITHUB | REDMINE | UPLOAD | MANUAL
    connectionId: str | None  # noqa: N815 — 프런트 계약 필드명
    externalId: str | None  # noqa: N815
    externalUrl: str | None  # noqa: N815
    # 같은 도구의 연결이 여럿이면 tool 만으로는 어디서 왔는지 모른다(GH-140)
    connectionName: str | None = None  # noqa: N815
    target: str | None = None  # 저장소(owner/repo)나 Redmine 프로젝트 식별자
    number: str | None = None  # 원천 번호. externalId 의 종류 접두(issue: 등)를 뗀 것


class RequirementDecision(BaseModel):
    """발주기관이 사유와 함께 지정한 상태(ARC-025). 근거 상태와 따로 남는다."""

    status: str
    reason: str
    decidedBy: str | None  # noqa: N815 — 지정한 사람 이름. 계정이 지워졌으면 None
    decidedAt: str  # noqa: N815


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
    # 상태가 어디서 왔는지. GitHub 이슈를 닫아 생긴 IMPLEMENTED 는 SOURCE_ISSUE_CLOSED,
    # 발주기관이 지정한 상태는 CLIENT_DECIDED 다. 그 밖에는 None
    statusBasis: str | None = None  # noqa: N815
    # 근거가 정한 상태. 지정이 없으면 status 와 같다
    evidenceStatus: str | None = None  # noqa: N815
    decision: RequirementDecision | None = None
    # 확정된 요구사항 기준선에 들었는지(GH-139). 기준선이 없거나 명세서에 없던 코드면 False
    inBaseline: bool = False  # noqa: N815


class IssueMilestone(BaseModel):
    """이슈에 원천이 지정한 마일스톤(ARC-023). 이름·기한·상태는 원천 값 그대로다."""

    title: str
    dueOn: str | None  # noqa: N815
    state: str  # OPEN | CLOSED
    url: str | None


class IssueRelation(BaseModel):
    """도구가 만든 이슈 사이 관계(Redmine 이슈관계). 출발점 쪽에만 싣는다."""

    type: str  # relates | precedes | follows | blocks | duplicates ...
    issueKey: str  # noqa: N815 — RM-203 같은 상대 이슈 키


class IssueResponse(BaseModel):
    """작업·결함 한 건. 도구가 달라도 같은 모양이다(GitHub 이슈, Redmine 작업·결함)."""

    id: str
    projectId: str  # noqa: N815
    key: str
    title: str
    status: str
    severity: str | None  # None 이면 원천에 근거가 없다(미지정). 낮은 위험이라는 뜻이 아니다
    sourcePriority: str | None = None  # noqa: N815 — 원천 우선순위 원문(Redmine '보통' 등)
    assignee: str | None
    resolvedAt: str | None  # noqa: N815
    source: SourceRef
    updatedAt: str  # noqa: N815
    milestone: IssueMilestone | None = None
    # 원천 분류·연결 정보(SWFR.CON.004, AC-043-2). Redmine 트래커 이름, 요구사항 ID 커스텀 필드,
    # 이슈관계. GitHub 은 라벨을 tracker 자리에 쓰지 않는다(None)
    tracker: str | None = None
    requirementRefs: list[str] = []  # noqa: N815
    relations: list[IssueRelation] = []


class IssueSummaryResponse(BaseModel):
    """이슈 화면 카드. 목록 페이지와 상관없이 사업 전체를 서버에서 센다.

    issue 테이블만 센다. 명세서 전에 이슈로 만든 요구사항의 출처 이슈는 여기 없다.
    """

    total: int
    open: int  # OPEN · IN_PROGRESS
    closed: int  # RESOLVED · CLOSED
    heavyOpen: int  # noqa: N815 — 열린 것 중 BLOCKER · CRITICAL · MAJOR
    unassignedOpen: int  # noqa: N815 — 열린 것 중 담당 없음
    unspecifiedOpen: int = 0  # noqa: N815 — 열린 것 중 심각도 미지정. 고위험에서 빼고 따로 센다
    sources: list["IssueSourceCount"] = []  # 연결 고르기. 연결을 골라 물어도 사업 전체를 낸다


class IssueSourceCount(BaseModel):
    """이슈 화면 연결 고르기 한 줄. connectionId 가 없으면 도구에서 오지 않은 이슈다."""

    connectionId: str | None  # noqa: N815
    tool: str | None
    name: str | None
    target: str | None
    count: int


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
    status: str  # ACTIVE | BROKEN | SUPERSEDED
    evidenceKind: str | None  # noqa: N815
    evidenceText: str | None  # noqa: N815
    externalUrl: str | None  # noqa: N815
    createdAt: str  # noqa: N815
    # 근거 위치(설계 문서의 경로·커밋·blob·줄·절·문서 상태 등, ARC-024)
    evidenceMeta: dict | None = None  # noqa: N815
    statusReason: str | None = None  # noqa: N815 — 대체·제외·끊김의 사유
    statusChangedAt: str | None = None  # noqa: N815
    supersededBy: str | None = None  # noqa: N815


class TraceCell(BaseModel):
    targetId: str  # noqa: N815
    label: str
    externalUrl: str | None  # noqa: N815
    # 출발점 종류. REPO_DOCUMENT 는 저장소 설계 문서, WORK_PRODUCT 는 등록 산출물이다
    sourceType: str | None = None  # noqa: N815
    docStatus: str | None = None  # noqa: N815 — 문서에 선언된 상태 CONFIRMED·DRAFT·UNKNOWN
    section: str | None = None  # 근거가 있는 절
    qualifier: str | None = None  # 참조에 붙은 한정어("미결" 등)


class StatusCount(BaseModel):
    status: str
    count: int


class SourceStateSummary(BaseModel):
    """원천 하나의 이슈 상태. 원천 기록(raw_artifact)에서 센다.

    내부 상태에서 거꾸로 짐작하지 않는다.

    connectionId 가 None 이면 출처 이슈가 없는 요구사항(명세서·직접 입력) 묶음이다.
    """

    connectionId: str | None  # noqa: N815
    tool: str  # GITHUB | REDMINE | NONE
    label: str
    total: int
    open: int
    closed: int
    unknown: int  # 연결은 있는데 원천 기록이 없거나 열림·닫힘을 못 읽은 것


class RequirementSummaryResponse(BaseModel):
    """요구사항 화면 요약. 목록 쪽과 상관없이 사업 전체를 서버에서 센다."""

    total: int
    verified: int  # VERIFIED · ACCEPTED. 이행률 분자와 같다
    notVerified: int  # noqa: N815 — total - verified. 미구현이라는 뜻이 아니다
    # IMPLEMENTED 중 출처 이슈가 닫혀서 붙은 것. 구현을 확인했다는 뜻이 아니다
    implementedFromSourceClosed: int  # noqa: N815
    verifiedRate: float | None  # noqa: N815 — total 이 0 이면 None(산출 불가)
    decided: int = 0  # 발주기관이 상태를 지정한 요구사항 수(ARC-025)
    byStatus: list[StatusCount]  # noqa: N815
    sources: list[SourceStateSummary]


class TraceabilityRowResponse(BaseModel):
    """추적표 한 줄. 요구사항 하나에 설계·구현·시험 칸이 붙는다."""

    requirementId: str  # noqa: N815
    requirementCode: str  # noqa: N815
    requirementTitle: str  # noqa: N815
    requirementStatus: str  # noqa: N815
    requirementStatusBasis: str | None = None  # noqa: N815 — RequirementResponse.statusBasis 와 같다
    requirementEvidenceStatus: str | None = None  # noqa: N815 — RequirementResponse.evidenceStatus
    requirementDecision: RequirementDecision | None = None  # noqa: N815
    # 출처 이슈 상태. OPEN | CLOSED | UNKNOWN, 출처 이슈가 없으면 NONE. 요구사항 상태와 따로다
    sourceState: str = "NONE"  # noqa: N815
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


class RequirementBaselineSource(BaseModel):
    """이 요구사항이 들어온 확정 명세서와 원문 위치(GH-158, ARC-028).

    명세서로 확정한 요구사항은 원천 도구가 없다. 출처는 명세서 판본과 그 안의 표·행이다."""

    baselineId: str  # noqa: N815
    version: int
    status: str  # CONFIRMED 만 내보낸다
    confirmedAt: str | None  # noqa: N815
    confirmedBy: str | None  # noqa: N815
    documentId: str | None  # noqa: N815 — 자료 화면에서 열 문서
    sourceFilename: str  # noqa: N815
    sourceDocVersion: str | None  # noqa: N815
    location: str | None  # 명세서 안 위치("표 3 · 2행")
    match: str | None  # 확정 때 판정. NEW · SAME · CHANGED


class RequirementDetailResponse(RequirementResponse):
    body: str
    traceLinks: list[TraceLinkResponse]  # noqa: N815
    history: list[EntityHistoryResponse]
    baselineSource: RequirementBaselineSource | None = None  # noqa: N815


class RequirementDecisionRequest(BaseModel):
    """발주기관 상태 지정. 사유는 반드시 적는다."""

    status: str
    reason: str = Field(min_length=1, max_length=1000)


class RequirementDecisionRevertRequest(BaseModel):
    """지정을 거두고 근거 상태로 되돌린다. 되돌리는 사유도 남긴다."""

    reason: str = Field(min_length=1, max_length=1000)


# --- 요구사항 기준선 (GH-139, ARC-028) ----------------------------------------


class BaselineItemRequest(BaseModel):
    """명세서 항목 고치기·더하기. 문제(중복·코드 꼴)는 막지 않고 표시한다. 제출 때 막는다."""

    code: str = Field(max_length=64)
    title: str = Field(max_length=500)
    body: str = Field(default="", max_length=20000)
    priority: str = "SHOULD"


class BaselineCreateRequest(BaseModel):
    documentId: str  # noqa: N815 — 올려 둔 명세서 문서


class BaselineReturnRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class BaselineConfirmRequest(BaseModel):
    """확정. 같은 코드인데 내용이 다른 항목은 기본으로 기존 정의를 둔다.
    명세서 내용으로 바꿀 코드만 적는다."""

    applySpecCodes: list[str] = []  # noqa: N815


class BaselineExisting(BaseModel):
    requirementId: str  # noqa: N815
    code: str
    title: str
    priority: str
    source: str  # 기존 요구사항이 어디서 왔는지: 연결 이름, "문서", "수기"


class BaselineItemResponse(BaseModel):
    id: str
    seq: int
    code: str | None
    title: str
    body: str
    priority: str
    location: str | None  # 명세서 안 위치. 손으로 더한 항목은 없다
    origin: str  # EXTRACTED | MANUAL
    edited: bool  # 추출 결과를 사람이 고쳤는지
    problems: list[str]  # DUPLICATE_CODE · INVALID_CODE · MISSING_TITLE · UNTRACEABLE_CODE
    match: str | None  # NEW · SAME · CHANGED. 확정 전에는 지금 기준 미리보기다
    existing: BaselineExisting | None
    requirementId: str | None  # noqa: N815 — 확정 뒤 붙은 요구사항
    specApplied: bool  # noqa: N815


class BaselineParent(BaseModel):
    """명세서의 상위 요구사항(절 제목의 코드). 요구사항 목록에는 들지 않는다."""

    code: str
    title: str
    location: str | None
    children: list[str]  # 이 상위에 속한 항목 코드. 항목 설명이 상위 코드를 적은 것


class BaselineResponse(BaseModel):
    id: str
    version: int
    status: str  # DRAFT · SUBMITTED · CONFIRMED
    documentId: str | None  # noqa: N815
    sourceFilename: str  # noqa: N815
    sourceDocVersion: str | None  # noqa: N815
    createdBy: str | None  # noqa: N815
    createdAt: str  # noqa: N815
    submittedBy: str | None  # noqa: N815
    submittedAt: str | None  # noqa: N815
    returnedReason: str | None  # noqa: N815
    confirmedBy: str | None  # noqa: N815
    confirmedByRole: str | None  # noqa: N815
    confirmedAt: str | None  # noqa: N815
    items: list[BaselineItemResponse]
    blockingCount: int  # noqa: N815 — 제출 전에 고쳐야 할 항목 수
    extractionEmpty: bool  # noqa: N815 — 명세서에서 한 건도 뽑지 못했다
    counts: dict[str, int]  # NEW · SAME · CHANGED
    # 기존 요구사항 중 명세서에 없는 코드. 지우지 않고 기준선 밖으로 둔다
    missing: list[BaselineExisting]
    parents: list[BaselineParent]


class BaselineStateResponse(BaseModel):
    """사업의 요구사항 기준선 상태. 요구사항 화면 머리와 기준선 화면이 같이 쓴다."""

    state: str  # NONE(미등록) · DRAFT(작성 중) · SUBMITTED(확정 대기) · CONFIRMED
    confirmed: BaselineResponse | None
    working: BaselineResponse | None  # 발주기관에게 작성 중(DRAFT) 목록은 보이지 않는다
    workingStatus: str | None  # noqa: N815
    requirementCount: int  # noqa: N815
    outsideBaselineCount: int  # noqa: N815 — 기준선에 들지 않은 요구사항
    unresolvedCodeCount: int  # noqa: N815


class UnresolvedRefResponse(BaseModel):
    """사업에 없는 요구사항 코드를 가리킨 근거. 잇지 않고 보이기만 한다."""

    code: str
    sourceType: str  # noqa: N815
    sourceId: str  # noqa: N815
    sourceLabel: str  # noqa: N815
    evidenceText: str | None  # noqa: N815
    evidenceUrl: str | None  # noqa: N815
    # 가리킨 코드가 기준선의 상위 요구사항이면 그 명칭. 없는 ID 가 아니라 상위를 가리킨 것이다
    parentTitle: str | None = None  # noqa: N815
