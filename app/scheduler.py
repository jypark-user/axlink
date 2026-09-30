"""서버 안 스케줄러 (SWFR.PIP.005 · SWFR.CON.005).

일별 스냅샷과 증분 수집은 스스로 돌아야 한다. cron 에 맡기면 폐쇄망 반입 요소가 하나 늘고
개발·시연·납품 환경이 달라진다. 앱이 뜰 때 백그라운드 작업 하나를 띄우고, 매 분 사업별
설정(project_schedule)을 보고 할 일을 정한다.

- 수집: 활성 연결마다 마지막 수집 뒤 주기(분)가 지났으면 증분 수집. 0 이면 수동만.
- 스냅샷: 사업 시간대(Asia/Seoul) 기준 정해진 시각이 지났는데 오늘 것이 없으면 찍는다.
  기동 직후 오늘 것이 없어도 찍는다. 하루가 비면 추이가 끊긴다.
  같은 날 두 번 찍으면 나중 값이 이기므로, 정해진 시각에 다시 찍어 그날 수집을 반영한다.

판단은 순수 함수로 두어 시계를 주입해 시험한다. 실제 실행은 스레드에서 한다(DB·HTTP 가
동기 코드다). 한 회차의 실패는 로그와 활동 기록에 남고 다음 회차는 계속 돈다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.db import fetch_all, tx

log = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Seoul")
TICK_SECONDS = 60
SYNC_INTERVAL_OPTIONS = (0, 15, 30, 60, 180, 360, 720, 1440)  # 분. 0 은 수동만
DEFAULT_SYNC_INTERVAL = 30
DEFAULT_SYNC_TIME = time(6, 0)  # 하루 한 번을 고른 사업이 도는 시각
DEFAULT_SNAPSHOT_TIME = time(0, 10)
# 스냅샷 갱신 빈도(시간). 24 는 정한 시각에 하루 한 번. 그보다 작으면 그날 줄을 더 자주 덮는다.
# 과업지시서 Ⅱ.2 의 "일별" 은 최소 보장이라 24 보다 긴 선택지는 두지 않는다.
SNAPSHOT_INTERVAL_OPTIONS = (24, 12, 6, 3, 1)
DEFAULT_SNAPSHOT_INTERVAL = 24


@dataclass(frozen=True)
class Schedule:
    project_id: str
    sync_interval_minutes: int
    snapshot_at: time
    snapshot_interval_hours: int = DEFAULT_SNAPSHOT_INTERVAL
    sync_at: time = DEFAULT_SYNC_TIME


def sync_due(
    last_synced_at: datetime | None, interval_minutes: int, now: datetime,
    sync_at: time = DEFAULT_SYNC_TIME,
) -> bool:
    """수집할 때인가. 0 이면 자동 수집 안 함. 한 번도 안 했으면 지금.

    하루 한 번(1440)은 스냅샷처럼 정한 시각 규칙이다. 오늘 아직 안 했고 그 시각이 지났으면
    돈다. 더 잦은 주기는 마지막 수집 뒤 간격이다.
    """
    if interval_minutes <= 0:
        return False
    if last_synced_at is None:
        return True
    if interval_minutes >= 1440:
        local = now.astimezone(LOCAL_TZ)
        done_today = last_synced_at.astimezone(LOCAL_TZ).date() >= local.date()
        return not done_today and local.time() >= sync_at
    return now - last_synced_at >= timedelta(minutes=interval_minutes)


def snapshot_due(
    last_snapshot_date: date | None, snapshot_at: time, now: datetime, *, just_started: bool
) -> bool:
    """오늘 것을 찍어야 하는가.

    기동 직후에는 오늘 것이 없으면 시각과 무관하게 찍는다. 그 뒤로는 정해진 시각을 지난
    첫 회차에 찍는다. 정해진 시각에 찍은 것은 오늘 날짜라 다시 안 찍는다. 단 기동 때 찍은
    것은 정해진 시각이 오면 한 번 더 찍어 그날 수집을 반영한다. 이를 위해 호출부가
    "오늘 정해진 시각 이후에 찍었는가" 를 last_snapshot_date 대신 넘길 수 있게 날짜만 본다.
    """
    local = now.astimezone(LOCAL_TZ)
    today = local.date()
    if last_snapshot_date is None or last_snapshot_date < today:
        return just_started or local.time() >= snapshot_at
    return False


def refresh_due(last_taken_at: datetime | None, interval_hours: int, now: datetime) -> bool:
    """정한 시각과 별개로, 빈도가 하루보다 잦으면 마지막으로 찍은 뒤 그 시간이 지났는가."""
    if interval_hours >= 24 or last_taken_at is None:
        return False
    return now - last_taken_at >= timedelta(hours=interval_hours)


def _load_schedules(cur: Any) -> list[Schedule]:
    rows = fetch_all(
        cur,
        """
        select p.id as project_id,
               coalesce(s.sync_interval_minutes, %s) as interval_minutes,
               coalesce(s.snapshot_hour, %s) as h, coalesce(s.snapshot_minute, %s) as m,
               coalesce(s.snapshot_interval_hours, %s) as every_hours,
               coalesce(s.sync_hour, %s) as sh, coalesce(s.sync_minute, %s) as sm
          from project p
          left join project_schedule s on s.project_id = p.id
         where p.status in ('PLANNING', 'ACTIVE', 'CLOSING')
        """,
        (
            DEFAULT_SYNC_INTERVAL, DEFAULT_SNAPSHOT_TIME.hour, DEFAULT_SNAPSHOT_TIME.minute,
            DEFAULT_SNAPSHOT_INTERVAL, DEFAULT_SYNC_TIME.hour, DEFAULT_SYNC_TIME.minute,
        ),
    )
    return [
        Schedule(
            str(r["project_id"]), int(r["interval_minutes"]), time(r["h"], r["m"]),
            int(r["every_hours"]), time(r["sh"], r["sm"]),
        )
        for r in rows
    ]


def run_once(now: datetime, *, just_started: bool, taken_at_scheduled: set[str]) -> dict[str, int]:
    """한 회차. 수집을 먼저, 스냅샷을 뒤에 한다. 그날 수집이 반영된 값이 그날의 사실이다.

    taken_at_scheduled: 오늘 정해진 시각에 찍은 사업. 기동 때 찍은 것과 구분해 하루 한 번만
    정해진 시각에 다시 찍는다. 날이 바뀌면 호출부가 비운다.
    """
    from app.dashboard import snapshot
    from app.integration import repository as integ_repo
    from app.integration import sync

    counts = {"synced": 0, "snapshots": 0, "errors": 0}
    with tx() as cur:
        schedules = _load_schedules(cur)

    for sched in schedules:
        # 1) 수집
        if sched.sync_interval_minutes > 0:
            with tx() as cur:
                connections = [
                    c for c in integ_repo.find_by_project(cur, sched.project_id)
                    if c["status"] in ("VERIFIED", "ACTIVE")
                    and sync_due(
                        c.get("last_synced_at"), sched.sync_interval_minutes, now, sched.sync_at
                    )
                ]
            for conn in connections:
                try:
                    with tx() as cur:
                        sync.run_sync(cur, conn)
                    counts["synced"] += 1
                except Exception:  # noqa: BLE001 — 한 연결의 실패가 회차를 멈추면 안 된다
                    counts["errors"] += 1
                    log.exception("주기 수집 실패: connection=%s", conn.get("id"))

        # 2) 스냅샷
        local_today = now.astimezone(LOCAL_TZ).date()
        with tx() as cur:
            last = cur.execute(
                """
                select max(snapshot_date) as d, max(created_at) as taken_at
                  from progress_snapshot where project_id = %s
                """,
                (sched.project_id,),
            ).fetchone()
        last_date = last["d"] if last else None
        last_taken_at = last["taken_at"] if last else None
        at_time = now.astimezone(LOCAL_TZ).time() >= sched.snapshot_at
        due = (
            snapshot_due(last_date, sched.snapshot_at, now, just_started=just_started)
            or (at_time and sched.project_id not in taken_at_scheduled and last_date == local_today)
            or refresh_due(last_taken_at, sched.snapshot_interval_hours, now)
        )
        if due:
            try:
                with tx() as cur:
                    snapshot.take_unchecked(cur, sched.project_id, local_today)
                counts["snapshots"] += 1
                if at_time:
                    taken_at_scheduled.add(sched.project_id)
            except Exception:  # noqa: BLE001
                counts["errors"] += 1
                log.exception("일별 스냅샷 실패: project=%s", sched.project_id)
    return counts


async def loop(stop: asyncio.Event) -> None:
    """매 분 한 회차. 첫 회차는 기동 직후다."""
    just_started = True
    taken_at_scheduled: set[str] = set()
    marker_day: date | None = None
    while not stop.is_set():
        now = datetime.now(UTC)
        today = now.astimezone(LOCAL_TZ).date()
        if marker_day != today:
            taken_at_scheduled = set()
            marker_day = today
        try:
            counts = await asyncio.to_thread(
                run_once, now, just_started=just_started, taken_at_scheduled=taken_at_scheduled
            )
            if counts["synced"] or counts["snapshots"] or counts["errors"]:
                log.info("스케줄러 회차 %s", counts)
        except Exception:  # noqa: BLE001
            log.exception("스케줄러 회차 실패")
        just_started = False
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)


def start() -> tuple[asyncio.Task[None], asyncio.Event]:
    stop = asyncio.Event()
    task = asyncio.create_task(loop(stop), name="axlink-scheduler")
    return task, stop
