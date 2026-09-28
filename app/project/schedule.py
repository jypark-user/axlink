"""사업별 수집 주기·스냅샷 시각 설정 API (SWFR.PIP.005 · SWFR.CON.005)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import scheduler
from app.auth import repository as auth_repo
from app.auth.deps import Principal
from app.auth.models import AuthPrincipal
from app.common import errors
from app.db import fetch_one, tx

router = APIRouter(prefix="/api/projects", tags=["schedule"])

INTERVAL_LABELS = {
    0: "자동 수집 안 함 (수동만)",
    15: "15분마다",
    30: "30분마다",
    60: "1시간마다",
    180: "3시간마다",
    360: "6시간마다",
    1440: "하루 한 번",
}


class ScheduleOption(BaseModel):
    minutes: int
    label: str


class ProjectScheduleResponse(BaseModel):
    projectId: str  # noqa: N815
    syncIntervalMinutes: int  # noqa: N815
    snapshotTime: str  # noqa: N815  "HH:MM" 사업 시간대
    timezone: str
    options: list[ScheduleOption]
    minIntervalMinutes: int  # noqa: N815
    lastSnapshotDate: str | None  # noqa: N815
    nextSnapshotAt: str  # noqa: N815
    editable: bool
    updatedAt: str | None  # noqa: N815


class ProjectScheduleUpdateRequest(BaseModel):
    syncIntervalMinutes: int  # noqa: N815
    snapshotTime: str = Field(pattern=r"^\d{2}:\d{2}$")  # noqa: N815


def _require_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def _next_snapshot(at: time, now: datetime) -> datetime:
    local = now.astimezone(scheduler.LOCAL_TZ)
    candidate = local.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def get(cur: Any, principal: AuthPrincipal, project_id: str) -> ProjectScheduleResponse:
    _require_project(cur, principal, project_id)
    row = fetch_one(cur, "select * from project_schedule where project_id = %s", (project_id,))
    interval = row["sync_interval_minutes"] if row else scheduler.DEFAULT_SYNC_INTERVAL
    at = scheduler.DEFAULT_SNAPSHOT_TIME
    if row:
        at = time(row["snapshot_hour"], row["snapshot_minute"])
    last = fetch_one(
        cur, "select max(snapshot_date) as d from progress_snapshot where project_id = %s",
        (project_id,),
    )
    now = datetime.now(UTC)
    return ProjectScheduleResponse(
        projectId=project_id,
        syncIntervalMinutes=interval,
        snapshotTime=at.strftime("%H:%M"),
        timezone=str(scheduler.LOCAL_TZ),
        options=[
            ScheduleOption(minutes=m, label=INTERVAL_LABELS[m])
            for m in scheduler.SYNC_INTERVAL_OPTIONS
        ],
        minIntervalMinutes=min(m for m in scheduler.SYNC_INTERVAL_OPTIONS if m > 0),
        lastSnapshotDate=last["d"].isoformat() if last and last["d"] else None,
        nextSnapshotAt=_next_snapshot(at, now).isoformat(),
        editable=principal.role in ("CLIENT", "SUPER_ADMIN"),
        updatedAt=row["updated_at"].isoformat() if row else None,
    )


def update(
    cur: Any, principal: AuthPrincipal, project_id: str, req: ProjectScheduleUpdateRequest
) -> ProjectScheduleResponse:
    """발주기관과 관리자만 바꾼다. 주기는 선택지 중 하나여야 하고 15분보다 짧을 수 없다."""
    _require_project(cur, principal, project_id)
    if principal.role not in ("CLIENT", "SUPER_ADMIN"):
        raise errors.ApiError(403, "FORBIDDEN", "발주기관 담당자만 수집 주기를 바꿀 수 있습니다.")
    if req.syncIntervalMinutes not in scheduler.SYNC_INTERVAL_OPTIONS:
        choices = ", ".join(str(m) for m in scheduler.SYNC_INTERVAL_OPTIONS)
        raise errors.validation_failed(f"수집 주기는 {choices} 분 중 하나여야 합니다.")
    try:
        hour, minute = (int(x) for x in req.snapshotTime.split(":"))
        at = time(hour, minute)
    except ValueError as exc:
        raise errors.validation_failed("스냅샷 시각은 HH:MM 꼴이어야 합니다.") from exc
    cur.execute(
        """
        insert into project_schedule
            (project_id, sync_interval_minutes, snapshot_hour, snapshot_minute,
             updated_by_user_id, updated_at)
        values (%s, %s, %s, %s, %s, now())
        on conflict (project_id) do update set
          sync_interval_minutes = excluded.sync_interval_minutes,
          snapshot_hour = excluded.snapshot_hour, snapshot_minute = excluded.snapshot_minute,
          updated_by_user_id = excluded.updated_by_user_id, updated_at = now()
        """,
        (project_id, req.syncIntervalMinutes, at.hour, at.minute, principal.user_id),
    )
    return get(cur, principal, project_id)


@router.get("/{project_id}/schedule", response_model=ProjectScheduleResponse)
def get_schedule(project_id: str, principal: Principal) -> ProjectScheduleResponse:
    with tx() as cur:
        return get(cur, principal, project_id)


@router.put("/{project_id}/schedule", response_model=ProjectScheduleResponse)
def put_schedule(
    project_id: str, req: ProjectScheduleUpdateRequest, principal: Principal
) -> ProjectScheduleResponse:
    with tx() as cur:
        return update(cur, principal, project_id, req)
