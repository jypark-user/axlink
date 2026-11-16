"""사업 DTO. 프런트 types/api.ts 의 ProjectSummaryResponse 와 필드가 1:1 이다."""

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    startDate: str  # noqa: N815 — 프런트 계약 필드명
    endDate: str  # noqa: N815
    description: str = Field(min_length=1)
    contractorName: str = ""  # noqa: N815
    # 지울 때 맞춰야 하는 비밀번호. 서버는 해시로만 갖고 있는다.
    deletePassword: str = Field(min_length=4)  # noqa: N815


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    startDate: str | None = None  # noqa: N815
    endDate: str | None = None  # noqa: N815
    description: str | None = None
    contractorName: str | None = None  # noqa: N815
    currentSiPhase: str | None = None  # noqa: N815
    # 사업 상태. 종료(CLOSED)로 바꾸면 예약 수집·스냅샷이 멈추고 데이터는 그대로 남는다(AC-002-3)
    status: str | None = None


class ProjectDeleteRequest(BaseModel):
    password: str


class AssignmentCreateRequest(BaseModel):
    contractorOrgId: str  # noqa: N815
    userIds: list[str]  # noqa: N815


class AssignmentResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815
    contractorOrgId: str  # noqa: N815
    contractorOrgName: str  # noqa: N815
    userId: str  # noqa: N815
    userName: str  # noqa: N815
    userEmail: str  # noqa: N815 — 로그인 아이디를 보여 준다(V20 이후 이메일이 아닐 수 있다)
    status: str
    assignedAt: str  # noqa: N815


class ProjectInviteResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815
    expiresAt: str  # noqa: N815
    revokedAt: str | None  # noqa: N815
    createdAt: str  # noqa: N815
    token: str | None  # 생성 응답에만 담긴다. 저장은 해시로만 한다.
    # 이 링크로 가입한 사람이 들어갈 업체(GH-138). 비어 있으면 새 업체 등록만 받는다
    organizationId: str | None = None  # noqa: N815
    organizationName: str | None = None  # noqa: N815


class InviteCreateRequest(BaseModel):
    organizationId: str | None = None  # noqa: N815 — 참여 업체. 지정하면 그 업체로만 가입한다


class ParticipantResponse(BaseModel):
    """사업의 참여 업체. 대표사·참여사는 표시 구분이고 권한이 없다."""

    id: str
    organizationId: str  # noqa: N815
    organizationName: str  # noqa: N815
    role: str  # REPRESENTATIVE | PARTICIPANT
    workNote: str | None  # noqa: N815
    status: str  # ACTIVE | REMOVED
    userCount: int  # noqa: N815
    connectionCount: int  # noqa: N815
    createdAt: str  # noqa: N815
    removedAt: str | None  # noqa: N815


class ParticipantCreateRequest(BaseModel):
    """기존 용역 업체를 고르거나(organizationId) 새 업체 이름을 적는다(organizationName)."""

    organizationId: str | None = None  # noqa: N815
    organizationName: str | None = Field(default=None, max_length=200)  # noqa: N815
    role: str = "PARTICIPANT"
    workNote: str | None = Field(default=None, max_length=300)  # noqa: N815


class ParticipantUpdateRequest(BaseModel):
    role: str | None = None
    workNote: str | None = Field(default=None, max_length=300)  # noqa: N815


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
    openReviewRequestCount: int  # noqa: N815
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
    # 산출물 승인 수(DEC-12): WBS 가 정한 산출물 중 현행 버전이 승인된 수 / WBS 가 정한 산출물 수.
    # 현황 화면 산출물 승인률과 같은 집계다. WBS 가 없으면 0/0(산출 불가)
    requiredWorkProductApproved: int  # noqa: N815
    requiredWorkProductTotal: int  # noqa: N815
    openCorrectionActionCount: int  # noqa: N815
    openRiskCount: int  # noqa: N815
    openReviewRequestCount: int  # noqa: N815 — 미처리 확인 요청 (SWFR.WEB.006)
    # 현황 화면과 같은 산정(dashboard.service.compute). 산출 불가면 None
    representative: float | None = None
    progressLevel: str | None = None  # noqa: N815 — L1~L4
    # 대표값의 산출 근거 한 문장(현황 화면과 같다). L3 이면 이슈 기반 추정 진척률이라고 밝힌다
    progressBasisNote: str | None = None  # noqa: N815
    progressDeviation: float | None = None  # noqa: N815 — WBS 실적 − 계획선. WBS 가 없으면 None
    # 진척 집계 자체가 실패했다. 산출 불가(None)와 다르다. 목록은 그대로 내고 이 칸만 실패로 보인다
    progressError: bool = False  # noqa: N815
    # 일정 준수(DEC-01): 기한이 오늘 이전인 마일스톤 중 기한 안에 닫힌 수 / 평가 대상 수.
    # 평가 대상이 없으면 비율은 None(산출 불가)
    scheduleCompliance: float | None = None  # noqa: N815
    scheduleComplianceAchieved: int = 0  # noqa: N815
    scheduleComplianceTotal: int = 0  # noqa: N815
    updatedAt: str  # noqa: N815
