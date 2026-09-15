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
    workProduct: ProgressMeasure  # noqa: N815

    behind: list[str]
    warnings: list[str]
    planVersion: str | None  # noqa: N815
    planUpdatedAt: str | None  # noqa: N815


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
    issueTotalCount: int  # noqa: N815
    requirementVerifiedCount: int  # noqa: N815
    requirementTotalCount: int  # noqa: N815
    riskClosedCount: int  # noqa: N815
    riskTotalCount: int  # noqa: N815
    workProductSubmittedCount: int  # noqa: N815
    workProductApprovedCount: int  # noqa: N815
    workProductTotalCount: int  # noqa: N815
    createdAt: str  # noqa: N815
