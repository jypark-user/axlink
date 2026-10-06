"""확인 요청 DTO. 프런트 types/api.ts 의 ReviewRequest* 와 필드가 1:1 이다."""

from typing import Any

from pydantic import BaseModel, Field

TARGET_TYPES = ("WBS_ITEM", "WORK_PRODUCT", "ISSUE", "RISK", "METRIC")
PURPOSES = ("GENERAL", "WBS_COMPLETION")
# 완료 근거 종류. 파일이 없는 작업은 시험·시연·회의 기록으로 근거를 댄다
# WORK_PRODUCT 는 이 사업에 등록된 산출물 버전 하나를 가리킨다(workProductId 필수).
# 나머지는 글로 적는 근거다
EVIDENCE_KINDS = (
    "WORK_PRODUCT", "DOCUMENT", "FILE", "COMMIT", "TEST", "DEMO", "MEETING", "OTHER",
)


class EvidenceItem(BaseModel):
    kind: str
    # 파일 경로·링크·커밋·회의록 이름 등. 산출물 버전이면 서버가 제목·버전으로 채운다
    ref: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=1000)
    workProductId: str | None = None  # noqa: N815


class ReviewTargetOption(BaseModel):
    key: str
    label: str


class ReviewRequestCreateRequest(BaseModel):
    targetType: str  # noqa: N815 — 프런트 계약 필드명
    targetKey: str = Field(min_length=1)  # noqa: N815
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    # WBS_COMPLETION 이면 WBS 작업 하나의 완료를 확인해 달라는 요청이다.
    # 확인할 완료 내용이 있어야 한다
    purpose: str = "GENERAL"
    completionScope: str | None = None  # noqa: N815


class ReviewBodyRequest(BaseModel):
    """조치 보고와 재요청은 본문 하나다. 완료 확인 요청의 보고에는 근거가 붙는다."""

    body: str = Field(min_length=1)
    evidence: list[EvidenceItem] = []


class ReviewConfirmRequest(BaseModel):
    """확인완료. 작업 완료 확인이면 완료를 인정한다는 뜻을 명시해야 한다."""

    acknowledgeCompletion: bool = False  # noqa: N815
    note: str = ""


class CompletionWithdrawRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CompletionRecordResponse(BaseModel):
    id: str
    kind: str  # CONFIRMED | WITHDRAWN
    decidedByName: str  # noqa: N815
    decidedAt: str  # noqa: N815
    wbsId: str  # noqa: N815
    weightAt: float  # noqa: N815
    planVersion: str | None  # noqa: N815
    reportedActual: float | None  # noqa: N815
    completionScope: str  # noqa: N815
    evidence: dict[str, Any]
    note: str | None


class ReviewStateChange(BaseModel):
    field: str
    label: str
    before: Any
    after: Any


class ReviewRequestEventResponse(BaseModel):
    id: str
    kind: str
    body: str | None
    actorName: str  # noqa: N815
    snapshot: dict[str, Any]
    createdAt: str  # noqa: N815
    evidence: list[dict[str, Any]] | None = None


class ReviewRequestResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815
    targetType: str  # noqa: N815
    targetKey: str  # noqa: N815
    targetLabel: str  # noqa: N815
    title: str
    body: str
    status: str
    requestedByName: str  # noqa: N815
    requestedAt: str  # noqa: N815
    reportBody: str | None  # noqa: N815
    reportedByName: str | None  # noqa: N815
    reportedAt: str | None  # noqa: N815
    confirmedByName: str | None  # noqa: N815
    confirmedAt: str | None  # noqa: N815
    rerequestCount: int  # noqa: N815
    updatedAt: str  # noqa: N815
    purpose: str = "GENERAL"
    completionScope: str | None = None  # noqa: N815


class ReviewRequestDetailResponse(ReviewRequestResponse):
    """요청 시점 상태와 지금 상태를 나란히 놓는다. 변경 내역은 시스템이 계산한다."""

    snapshot: dict[str, Any]
    currentState: dict[str, Any]  # noqa: N815
    changes: list[ReviewStateChange]
    events: list[ReviewRequestEventResponse]
    completionRecords: list[CompletionRecordResponse] = []  # noqa: N815
