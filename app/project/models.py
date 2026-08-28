"""사업 DTO. 프런트 types/api.ts 의 ProjectSummaryResponse 와 필드가 1:1 이다."""

from pydantic import BaseModel


class ProjectMetrics(BaseModel):
    requirementTotal: int  # noqa: N815
    requirementAccepted: int  # noqa: N815
    issueOpen: int  # noqa: N815
    riskOpen: int  # noqa: N815
    workProductApproved: int  # noqa: N815
    workProductTotal: int  # noqa: N815
    traceabilityCoverage: int  # noqa: N815
    lastSyncedAt: str | None  # noqa: N815


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    description: str
    contractorName: str | None  # noqa: N815
    status: str
    startDate: str  # noqa: N815
    endDate: str  # noqa: N815
    currentSiPhase: str | None  # noqa: N815
    clientOrgId: str  # noqa: N815
    clientOrgName: str  # noqa: N815
    assignmentCount: int  # noqa: N815
    connectionCount: int  # noqa: N815
    defaultDashboardId: str | None  # noqa: N815
    metrics: ProjectMetrics
    createdAt: str  # noqa: N815
    updatedAt: str  # noqa: N815


class ProjectSummaryResponse(BaseModel):
    id: str
    name: str
    status: str
    startDate: str  # noqa: N815 — 프런트 계약 필드명
    endDate: str  # noqa: N815
    currentSiPhase: str | None  # noqa: N815
    clientOrgId: str  # noqa: N815
    clientOrgName: str  # noqa: N815
    contractorName: str | None  # noqa: N815
    requiredWorkProductApproved: int  # noqa: N815
    requiredWorkProductTotal: int  # noqa: N815
    openCorrectionActionCount: int  # noqa: N815
    openRiskCount: int  # noqa: N815
    updatedAt: str  # noqa: N815
