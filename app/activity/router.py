"""활동 기록·알림 API."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.activity import service
from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx

router = APIRouter(prefix="/api", tags=["activity"])


class ActivityEventResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815
    projectName: str  # noqa: N815
    occurredAt: str  # noqa: N815
    kind: str
    audience: str
    actorLabel: str  # noqa: N815
    targetType: str | None  # noqa: N815
    targetKey: str | None  # noqa: N815
    summary: str
    detail: dict[str, Any]


class NotificationsResponse(BaseModel):
    items: list[ActivityEventResponse]
    unread: int
    seenAt: str | None  # noqa: N815


class SeenResponse(BaseModel):
    seenAt: str  # noqa: N815


def _to_response(r: dict[str, Any]) -> ActivityEventResponse:
    return ActivityEventResponse(
        id=str(r["id"]),
        projectId=str(r["project_id"]),
        projectName=r["project_name"],
        occurredAt=r["occurred_at"].isoformat(),
        kind=r["kind"],
        audience=r["audience"],
        actorLabel=r["actor_label"],
        targetType=r["target_type"],
        targetKey=r["target_key"],
        summary=r["summary"],
        detail=r["detail_json"] or {},
    )


@router.get("/projects/{project_id}/activity", response_model=PageResponse[ActivityEventResponse])
def list_activity(
    project_id: str,
    principal: Principal,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
    since: Annotated[datetime | None, Query()] = None,
) -> PageResponse[ActivityEventResponse]:
    """사업의 활동. 최근 것이 앞이다. since 를 주면 그 이후만(지난 보고 이후 변경)."""
    with tx() as cur:
        result = service.list_activity(
            cur, principal, project_id, PageQuery(page=page, size=size), since
        )
    return PageResponse.of(
        [_to_response(r) for r in result.content], PageQuery(page=page, size=size),
        result.totalElements,
    )


@router.get("/notifications", response_model=NotificationsResponse)
def notifications(
    principal: Principal, size: Annotated[int, Query(ge=1, le=100)] = 20
) -> NotificationsResponse:
    """내 역할이 알아야 할 최근 활동과 미읽음 수."""
    with tx() as cur:
        data = service.notifications(cur, principal, size)
    return NotificationsResponse(
        items=[_to_response(r) for r in data["items"]],
        unread=data["unread"],
        seenAt=data["seenAt"].isoformat() if data["seenAt"] else None,
    )


@router.post("/notifications/seen", response_model=SeenResponse)
def mark_seen(principal: Principal) -> SeenResponse:
    """알림을 열어 봤다. 이 시각 이전 것은 미읽음에서 빠진다."""
    with tx() as cur:
        now = service.mark_seen(cur, principal)
    return SeenResponse(seenAt=now.isoformat())
