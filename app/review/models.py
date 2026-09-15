"""확인 요청 DTO. 프런트 types/api.ts 의 ReviewRequest* 와 필드가 1:1 이다."""

from typing import Any

from pydantic import BaseModel, Field

TARGET_TYPES = ("WBS_ITEM", "WORK_PRODUCT", "ISSUE", "RISK", "METRIC")


class ReviewTargetOption(BaseModel):
    key: str
    label: str


class ReviewRequestCreateRequest(BaseModel):
    targetType: str  # noqa: N815 — 프런트 계약 필드명
    targetKey: str = Field(min_length=1)  # noqa: N815
    title: str = Field(min_length=1, max_length=300)
    body: str = ""


class ReviewBodyRequest(BaseModel):
    """조치 보고와 재요청은 본문 하나다."""

    body: str = Field(min_length=1)


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


class ReviewRequestDetailResponse(ReviewRequestResponse):
    """요청 시점 상태와 지금 상태를 나란히 놓는다. 변경 내역은 시스템이 계산한다."""

    snapshot: dict[str, Any]
    currentState: dict[str, Any]  # noqa: N815
    changes: list[ReviewStateChange]
    events: list[ReviewRequestEventResponse]
