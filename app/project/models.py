"""사업 DTO. 프런트 types/api.ts 의 ProjectSummaryResponse 와 필드가 1:1 이다."""

from pydantic import BaseModel


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
