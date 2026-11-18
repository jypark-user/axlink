"""진척·대시보드·위젯 DTO. 프런트 types/api.ts 와 필드가 1:1 이다."""

from pydantic import BaseModel

from app.semantic.models import WidgetDataResponse, WidgetFilter, WidgetSpec

# 측정의 성격. 화면에서 자기신고와 관측을 구분해 보여야 한다 —
# 셋이 어긋날 때 어느 쪽을 의심할지가 이 구분에서 갈린다.
SELF_REPORTED = "SELF_REPORTED"
OBSERVED = "OBSERVED"


class ProgressMeasure(BaseModel):
    """진척 한 갈래. 분모가 셋 다 달라서 값만 나란히 두면 오해를 부른다."""

    value: float | None
    numerator: int | None
    denominator: int | None
    label: str
    unit: str
    kind: str
    note: str | None
    # 진척도가 없어 0 으로 센 이슈 수. 이슈 기반 추정 진척률(DEC-17)에만 있다
    missing: int | None = None


class ProgressResponse(BaseModel):
    baseDate: str  # noqa: N815 — 프런트 계약 필드명
    level: str
    representative: float | None
    basis: str
    gap: float | None

    wbs: ProgressMeasure
    wbsPlanned: float | None  # noqa: N815
    wbsDeviation: float | None  # noqa: N815
    wbsDeclaredPlanned: float | None  # noqa: N815

    issue: ProgressMeasure
    # 이슈 기반 추정 진척률(DEC-17). WBS 없는 사업(L3)의 대표값이다. 해결률(issue)과 다른 지표다
    issueEstimate: ProgressMeasure | None = None  # noqa: N815
    workProduct: ProgressMeasure  # noqa: N815
    # 결함 처리율(DEC-02). 품질 축의 값이고 대표 진척률·격차에는 쓰지 않는다
    defect: ProgressMeasure | None = None

    behind: list[str]
    # 지연 작업(종료일 지남·실적 100% 미만). 스냅샷 「지연 작업 수」와 같은 기준
    delayed: list[str] = []
    warnings: list[str]
    planVersion: str | None  # noqa: N815
    planUpdatedAt: str | None  # noqa: N815

    # 대표값이 WBS 실적(L1)이 아니면 True. 화면·답변이 「추정」을 붙인다(DEC-19, DEF-V037)
    estimated: bool = False
    # 대표값의 산출 근거 한 문장. 산출 불가면 그 이유다
    basisNote: str | None = None  # noqa: N815
    # 일정 준수율(DEC-01): 기한이 기준일 이전인 마일스톤 중 기한 안에 닫힌 것
    scheduleCompliance: ProgressMeasure | None = None  # noqa: N815
    # 산출물 승인률(DEC-12): WBS 가 정한 산출물 중 현행 버전이 승인된 것
    deliverableApproval: ProgressMeasure | None = None  # noqa: N815
    deliverableSubmission: ProgressMeasure | None = None  # noqa: N815  산출물 제출률(V70)


# ---------------------------------------------------------------- 대시보드 · 위젯


class GridItem(BaseModel):
    i: str
    x: int
    y: int
    w: int
    h: int
    minW: int | None = None  # noqa: N815
    minH: int | None = None  # noqa: N815


class DashboardLayout(BaseModel):
    lg: list[GridItem] = []
    md: list[GridItem] = []
    sm: list[GridItem] = []


class WidgetResponse(BaseModel):
    id: str
    dashboardId: str  # noqa: N815
    template: str
    title: str
    spec: WidgetSpec
    createdAt: str  # noqa: N815
    updatedAt: str  # noqa: N815


class DashboardSummaryResponse(BaseModel):
    id: str
    name: str
    projectId: str | None  # noqa: N815
    projectName: str | None  # noqa: N815
    isDefault: bool  # noqa: N815
    widgetCount: int  # noqa: N815
    editable: bool
    updatedAt: str  # noqa: N815


class DashboardDetailResponse(BaseModel):
    id: str
    name: str
    projectId: str | None  # noqa: N815
    projectName: str | None  # noqa: N815
    isDefault: bool  # noqa: N815
    editable: bool
    layout: DashboardLayout
    widgets: list[WidgetResponse]
    updatedAt: str  # noqa: N815


class DashboardLayoutUpdateRequest(BaseModel):
    layout: DashboardLayout


class WidgetCreateRequest(BaseModel):
    spec: WidgetSpec
    gridItem: GridItem | None = None  # noqa: N815


class WidgetUpdateRequest(BaseModel):
    spec: WidgetSpec


class WidgetPreviewRequest(BaseModel):
    spec: WidgetSpec


class WidgetDataRequest(BaseModel):
    projectScopeOverride: list[str] | None = None  # noqa: N815
    periodOverride: WidgetFilter | None = None  # noqa: N815


class WidgetGenerateRequest(BaseModel):
    prompt: str
    template: str | None = None
    projectScope: list[str] = []  # noqa: N815
    dashboardId: str | None = None  # noqa: N815


class WidgetGenerationRejection(BaseModel):
    reason: str
    unmatchedTerms: list[str]  # noqa: N815
    suggestedAction: str | None  # noqa: N815
    suggestedQuestion: str | None  # noqa: N815


class WidgetGenerateResponse(BaseModel):
    status: str  # GENERATED | NOT_EXPRESSIBLE
    spec: WidgetSpec | None
    preview: WidgetDataResponse | None
    rejection: WidgetGenerationRejection | None


# ---------------------------------------------------------------- 스냅샷


class ProgressSnapshotResponse(BaseModel):
    projectId: str  # noqa: N815
    snapshotDate: str  # noqa: N815
    level: str
    representativePct: float | None  # noqa: N815
    wbsActualPct: float | None  # noqa: N815
    wbsPlannedPct: float | None  # noqa: N815
    behindTaskCount: int  # noqa: N815
    issueResolvedCount: int  # noqa: N815
    issueTotalCount: int  # noqa: N815 — 일반 이슈(V63 전 행은 결함을 가르지 않은 값)
    defectResolvedCount: int | None = None  # noqa: N815 — 결함(DEC-02). null 이면 가르기 전
    defectTotalCount: int | None = None  # noqa: N815
    requirementVerifiedCount: int  # noqa: N815
    requirementTotalCount: int  # noqa: N815
    riskClosedCount: int  # noqa: N815
    riskTotalCount: int  # noqa: N815
    workProductSubmittedCount: int  # noqa: N815
    workProductApprovedCount: int  # noqa: N815
    workProductTotalCount: int  # noqa: N815
    createdAt: str  # noqa: N815
    # 대표값의 산식(DEC-17, V65). 비어 있으면 V65 전 행이다. 이름은 서버가 붙인다
    representativeBasis: str | None = None  # noqa: N815
    representativeBasisLabel: str | None = None  # noqa: N815
    issueEstimatePct: float | None = None  # noqa: N815
    issueEstimateMissingCount: int | None = None  # noqa: N815
    # 지표별 진척률(11-18 사용자 지시). 계획·WBS 는 위 두 칸, 산출물·요구사항은 그날 센 건수에서
    # 대시보드 카탈로그(snapshot_*_pct)와 같은 식으로 낸다. 분모가 없으면 null
    deliverableApprovedCount: int | None = None  # noqa: N815
    deliverableTotalCount: int | None = None  # noqa: N815
    deliverableSubmittedCount: int | None = None  # noqa: N815  V70
    deliverableSubmissionPct: float | None = None  # noqa: N815  V70
    deliverableApprovalPct: float | None = None  # noqa: N815
    requirementFulfillmentPct: float | None = None  # noqa: N815


# ---------------------------------------------------------------- 일정 (WBS)

# 일정 화면의 원천. 화면은 이 값으로 제목과 고지문을 바꾼다.
WBS_SOURCE_FILE = "WBS_FILE"  # 용역사가 낸 WBS 파일 (사업수행계획서)
WBS_SOURCE_REDMINE = "REDMINE"  # Redmine 이슈의 시작일·종료일·진척률
WBS_SOURCE_NONE = "NONE"  # 둘 다 없다. 작업 줄을 만들지 않는다


class LinkedIssue(BaseModel):
    """WBS 항목에 이어진 이슈 한 건(ARC-016 3-4). 상태는 표준 이슈 상태다."""

    key: str | None
    title: str
    status: str  # OPEN | IN_PROGRESS | RESOLVED | CLOSED
    url: str | None


class WbsItemResponse(BaseModel):
    """일정 화면의 작업 한 줄. 프런트 ScheduleTask 와 1:1 이다."""

    wbsId: str  # noqa: N815
    name: str
    level: int  # 들여쓰기 깊이. 0 이 최상위
    owner: str
    deliverable: str | None
    startDate: str | None  # noqa: N815
    endDate: str | None  # noqa: N815
    weight: float | None  # 상위 항목·Redmine 이슈는 없다
    progress: int  # 0~100
    planned: int  # 기준일의 계획 진척. 0~100
    externalUrl: str | None  # noqa: N815
    # 산출물 판정(ARC-016 2단계). 묶음·산출물 열 없음은 NONE
    deliverableStatus: str = "NONE"  # noqa: N815  NONE | SUBMITTED | MISSING | OVERDUE
    deliverableRule: str | None = None  # noqa: N815  REPO_PATH | FILE_NAME | PRODUCT_TYPE
    deliverableRef: str | None = None  # noqa: N815  맞춘 경로·파일명·유형
    deliverableUrl: str | None = None  # noqa: N815
    # 번호 토큰이 정확히 맞은 이슈. 이어지지 않은 이슈는 사업 이슈 목록에 그대로 있다
    linkedIssues: list[LinkedIssue] = []  # noqa: N815
    # 작업 단위 격차 경고(DEC-20, ARC-016 4절): 실적 80 이상인데 산출물 미제출이거나 열린 연결
    # 이슈가 있다. 경고일 뿐 진척률을 깎지 않는다
    gapWarning: str | None = None  # noqa: N815


class WbsDeliverableDocument(BaseModel):
    """항목에 붙었거나 이름이 맞은 문서."""

    id: str
    fileName: str  # noqa: N815
    status: str
    uploadedAt: str  # noqa: N815
    proposedType: str | None  # noqa: N815  초안이 추정한 29110 유형. 확정 전이라도 태그로 보인다
    confirmed: bool


class DesignatedVersion(BaseModel):
    """지정 항목에 이어 올린 제출본 하나(UC-033). 확정해야 제출이다(DEC-14)."""

    documentId: str  # noqa: N815
    fileName: str  # noqa: N815
    uploadedAt: str  # noqa: N815
    state: str  # REGISTERED(확정 전) | SUBMITTED | APPROVED | REJECTED
    workProductId: str | None  # noqa: N815
    version: str | None
    rejectReason: str | None  # noqa: N815
    decidedAt: str | None  # noqa: N815  승인 시각
    isCurrent: bool  # noqa: N815  그 유형의 현행 버전인가. 승인·반려는 현행 버전에만 한다
    # 확정 전(REGISTERED)일 때 다음 할 일. READY: 초안이 있어 「산출물로 제출」할 수 있다 ·
    # PROCESSING: 아직 읽는 중 · NO_DRAFT: 초안이 없다(읽기 실패 등). 제출된 버전은 None
    submit: str | None = None


class DesignatedDeliverable(BaseModel):
    """발주기관이 WBS 작업에 정한 산출물 항목과 양식(UC-033). 양식은 제출본이 아니다."""

    id: str
    taskKey: str  # noqa: N815
    wbsIdAt: str  # noqa: N815  지정할 때의 번호
    taskNameAt: str  # noqa: N815
    name: str
    description: str | None
    productType: str | None  # noqa: N815  22종 분류. 필수 목록이 아니다
    guide: str | None
    templateFileName: str | None  # noqa: N815
    templateSize: int | None  # noqa: N815
    status: str  # MISSING | REGISTERED | SUBMITTED | APPROVED | REJECTED
    needsRedesignation: bool  # noqa: N815  계획서 교체로 작업 정체가 끊겼다
    versions: list[DesignatedVersion]


class DesignateRequest(BaseModel):
    taskKey: str  # noqa: N815
    name: str
    description: str | None = None
    productType: str | None = None  # noqa: N815
    guide: str | None = None


class DesignationUpdateRequest(BaseModel):
    """보낸 칸만 고친다. taskKey 를 보내면 다른 작업으로 옮긴다(재지정)."""

    name: str | None = None
    description: str | None = None
    productType: str | None = None  # noqa: N815
    guide: str | None = None
    taskKey: str | None = None  # noqa: N815


class DesignationEvent(BaseModel):
    kind: str  # CREATED | UPDATED | TEMPLATE | REASSIGNED | REMOVED
    at: str
    actorName: str  # noqa: N815
    actorRole: str  # noqa: N815
    detail: dict


class DeliverableReview(BaseModel):
    """작업에 올라온 산출물 하나(V70, 2026-11-18 사용자 결정: 승인 단위는 올라온 산출물).

    발주기관이 산출물 화면에서 승인·반려한다. 22종 분류별 산출물 버전과는 상관없다.
    """

    documentId: str  # noqa: N815
    name: str  # 양식 이름, 양식 없이 올렸으면 파일 이름
    fileName: str  # noqa: N815
    uploadedAt: str  # noqa: N815
    status: str  # SUBMITTED | APPROVED | REJECTED
    rejectReason: str | None  # noqa: N815
    reviewedAt: str | None  # noqa: N815
    latest: bool  # 같은 양식에 다시 올린 것이 있으면 앞의 것은 지난 판이다


class WbsDeliverableItem(BaseModel):
    """산출물 화면의 한 줄. WBS 말단 작업이 정한 산출물과 그 판정(ARC-016)."""

    wbsId: str  # noqa: N815
    name: str
    deliverable: str | None
    endDate: str | None  # noqa: N815
    status: str  # NONE | SUBMITTED | MISSING | OVERDUE
    rule: str | None
    ref: str | None
    url: str | None
    productType: str | None  # noqa: N815  29110 유형 태그. 확정된 산출물이나 초안 추정에서 온다
    documents: list[WbsDeliverableDocument]
    taskKey: str | None = None  # noqa: N815  작업 정체(V46). 지정은 번호가 아니라 이것에 묶인다
    designated: list[DesignatedDeliverable] = []  # 발주기관 지정 항목(UC-033)
    review: list[DeliverableReview] = []  # 승인·반려할 제출본


class WbsDeliverablesResponse(BaseModel):
    baseDate: str  # noqa: N815
    items: list[WbsDeliverableItem]
    summary: "DeliverableSummary"
    # 계획서 교체로 작업이 사라져 「재지정 필요」인 지정 항목. 지우지 않고 여기 모아 보인다
    redesignation: list[DesignatedDeliverable] = []


class DeliverableSummary(BaseModel):
    """말단 항목의 산출물 판정 건수. none 은 산출물 열이 없는 항목이다."""

    submitted: int = 0
    missing: int = 0
    overdue: int = 0
    none: int = 0


class WbsRecognitionColumn(BaseModel):
    field: str
    label: str  # 번호·작업명·산출물·시작일·종료일·가중치·계획·실적
    header: str | None  # 파일의 머리글 글자. 못 찾았으면 None
    column: str | None  # 엑셀 열 이름(A·B…)


class WbsRecognitionResponse(BaseModel):
    """계획서 인식 결과 (UC-030 3단계, DEC-04 (b)). 확인·재지정 단계는 없다."""

    status: str  # OK · FAILED
    planVersion: str | None  # noqa: N815 — 읽으려 한 판
    readAt: str | None  # noqa: N815
    headerRow: int | None  # noqa: N815 — 1부터 센 머리글 행
    columns: list[WbsRecognitionColumn]
    leafCount: int | None  # noqa: N815
    groupCount: int | None  # noqa: N815
    weightTotal: float | None  # noqa: N815
    normalized: bool  # 가중치 합이 1.00 이 아니라 합으로 나눴다
    missingDeliverableCount: int | None  # noqa: N815
    warnings: list[str]
    error: str | None
    # 이 판을 못 읽어 직전 판에서 읽은 작업을 계속 쓰고 있다
    usingPrevious: bool  # noqa: N815
    # 인식 결과를 남기기 전(V61 전)에 읽은 판. 열 매핑은 없고 수는 행에서 셌다
    recordedBeforeTracking: bool = False  # noqa: N815
    guidance: str


class WbsSourceFile(BaseModel):
    """일정·진척 수치를 읽어 온 원천 파일 (2026-11-18 사용자 지시). 수치가 바뀌려면 이 파일이 바뀌어
    다시 수집돼야 한다. 용역사가 어느 파일을 고쳐야 하는지 헷갈리지 않게 화면에 그대로 보인다."""

    origin: str  # REPOSITORY(저장소에서 수집) | UPLOAD(자료로 올림) | OTHER
    path: str | None  # 저장소 안 경로 또는 올린 파일 이름
    url: str | None  # 원본을 여는 주소
    tool: str | None  # GITHUB | GITLAB | REDMINE ...
    repository: str | None  # 저장소(owner/name) 또는 연결 대상
    revision: str | None  # 읽은 판(커밋 등)
    readAt: str | None  # noqa: N815 (이 판을 반영한 시각)
    lastSyncedAt: str | None  # noqa: N815 (그 연결을 마지막으로 수집한 시각)


class WbsScheduleResponse(BaseModel):
    source: str  # WBS_FILE | REDMINE | NONE
    sourceLabel: str  # noqa: N815
    sourceUrl: str | None  # noqa: N815
    baseDate: str  # noqa: N815
    planVersion: str | None  # noqa: N815
    planUpdatedAt: str | None  # noqa: N815
    items: list[WbsItemResponse]
    warnings: list[str]
    # 원천이 없을 때만 채운다. 진척률 산정의 핵심 입력이 빠졌음을 화면이 그대로 보인다.
    notice: str | None
    deliverables: DeliverableSummary = DeliverableSummary()
    recognition: WbsRecognitionResponse | None = None
    sourceFile: WbsSourceFile | None = None  # noqa: N815


# --- 인포 템플릿 카탈로그 (ARC-012) ----------------------------------------------


class WidgetTemplateExample(BaseModel):
    measure: str
    dimensions: list[str]
    title: str


class WidgetTemplateResponse(BaseModel):
    key: str
    label: str
    family: str
    purpose: str
    screen: str
    when: str
    measureTypes: list[str]  # noqa: N815 — 프런트 계약 필드명
    dimsMin: int  # noqa: N815
    dimsMax: int  # noqa: N815
    timeAxis: str  # noqa: N815 — REQUIRED | OPTIONAL | NONE
    categoryMax: int | None  # noqa: N815
    usesTotal: bool  # noqa: N815
    usesTarget: bool  # noqa: N815
    usesPrevious: bool  # noqa: N815
    options: list[str]
    rowCap: int  # noqa: N815
    chat: bool
    note: str
    example: WidgetTemplateExample
    prompts: list[str]  # "표시할 내용" 에 이렇게 적으라는 예시 문장
    # 쇼케이스용 예시 값. 계약에서 만든 결정적 값이라 사업이 없어도 그림이 그려진다
    sample: WidgetDataResponse


class WidgetTemplateListResponse(BaseModel):
    templates: list[WidgetTemplateResponse]


class CompletionItem(BaseModel):
    """WBS 말단 작업 하나의 근거 사실 넷과 완료 확인 상태."""

    wbsId: str  # noqa: N815
    taskKey: str  # noqa: N815
    name: str
    deliverable: str | None
    weight: float
    reportedActual: float | None  # noqa: N815
    keyReason: str  # noqa: N815 — 작업 식별을 이었는가(CONTINUED) 새로 잡았는가
    fileCheck: str | None  # noqa: N815 — MATCHED | MISSING | OVERDUE | NONE
    fileRef: str | None  # noqa: N815
    submission: str  # SUBMITTED | DRAFT | UNKNOWN
    approval: str  # APPROVED | REJECTED | NOT_APPROVED | UNKNOWN
    productVersion: str | None  # noqa: N815
    completionStatus: str  # noqa: N815 — CONFIRMED | RECONFIRM | WITHDRAWN | NONE
    predecessorConfirmed: bool  # noqa: N815 — 같은 번호의 예전 작업 확인이 승계되지 않았다
    confirmedAt: str | None  # noqa: N815
    confirmedBy: str | None  # noqa: N815
    weightAtConfirm: float | None  # noqa: N815
    planVersionAtConfirm: str | None  # noqa: N815
    actualAtConfirm: float | None  # noqa: N815
    evidenceRevised: bool  # noqa: N815 — 확인 뒤 근거 파일·버전이 바뀌었다
    openRequestId: str | None  # noqa: N815
    openRequestStatus: str | None  # noqa: N815


class CompletionSummaryResponse(BaseModel):
    """보고 진척률과 완료 확인율. 분모가 없으면 비율은 None(산출 불가)."""

    reportedPct: float | None  # noqa: N815
    completionRate: float | None  # noqa: N815
    basis: str
    leafCount: int  # noqa: N815
    confirmedCount: int  # noqa: N815
    reconfirmCount: int  # noqa: N815
    reported100Count: int  # noqa: N815
    reported100Pending: int  # noqa: N815
    inProgressCount: int  # noqa: N815
    items: list[CompletionItem]
