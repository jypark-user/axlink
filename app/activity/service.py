"""활동 기록과 알림 (2026-09-23 결정).

기록은 사업 단위 한 표다. 알림은 그 위에 "내 역할이 알아야 할 것" 과 사용자별 마지막 확인
시각을 얹은 것이다. 기록은 쓰기 지점(확인 요청·산출물·동기화)이 부르고, 실패해도 본 작업을
막지 않는다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common.paging import PageQuery, PageResponse
from app.db import fetch_all, fetch_one

log = logging.getLogger(__name__)

CLIENT = "CLIENT"
CONTRACTOR = "CONTRACTOR"
ALL = "ALL"

# 종류. 화면 라벨은 프런트가 붙인다
REVIEW_REQUESTED = "REVIEW_REQUESTED"
REVIEW_REPORTED = "REVIEW_REPORTED"
REVIEW_CONFIRMED = "REVIEW_CONFIRMED"
REVIEW_REREQUESTED = "REVIEW_REREQUESTED"
DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
DELIVERABLE_SUBMITTED = "DELIVERABLE_SUBMITTED"
DELIVERABLE_OVERDUE = "DELIVERABLE_OVERDUE"
SYNC_FAILED = "SYNC_FAILED"
SYNC_CHANGED = "SYNC_CHANGED"


def other_side(role: str) -> str:
    """행동한 쪽의 반대편이 알아야 한다. 관리자가 한 일은 둘 다 본다."""
    if role == CONTRACTOR:
        return CLIENT
    if role == CLIENT:
        return CONTRACTOR
    return ALL


def record(
    cur: Any,
    *,
    project_id: str,
    kind: str,
    audience: str,
    summary: str,
    actor: AuthPrincipal | None = None,
    actor_label: str | None = None,
    target_type: str | None = None,
    target_key: str | None = None,
    detail: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """활동 한 줄. actor 가 없으면 시스템이 일으킨 일이다."""
    label = actor_label
    actor_id = None
    if actor is not None:
        actor_id = actor.user_id
        if label is None:
            row = auth_repo.find_user_by_id(cur, actor.user_id)
            label = (row or {}).get("name") or "사용자"
    try:
        cur.execute(
            """
            insert into activity_event
                (project_id, occurred_at, kind, audience, actor_user_id, actor_label,
                 target_type, target_key, summary, detail_json)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                project_id, occurred_at or datetime.now(UTC), kind, audience, actor_id,
                (label or "시스템")[:120], target_type, target_key, summary[:500],
                Jsonb(detail or {}),
            ),
        )
    except Exception:  # noqa: BLE001 — 기록이 본 작업을 막으면 안 된다
        log.exception("활동 기록을 남기지 못했습니다: %s", kind)


def _audiences(principal: AuthPrincipal) -> list[str] | None:
    if principal.role == "SUPER_ADMIN":
        return None
    return [principal.role, ALL]


def list_activity(
    cur: Any, principal: AuthPrincipal, project_id: str, page: PageQuery,
    since: datetime | None = None,
) -> PageResponse[dict[str, Any]]:
    """사업의 활동 전부(활동 탭). 역할과 무관하게 본다. 기간을 주면 그 이후만."""
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        from app.common import errors

        raise errors.project_access_denied()
    where = ["e.project_id = %s"]
    params: list[Any] = [project_id]
    if since is not None:
        where.append("e.occurred_at >= %s")
        params.append(since)
    total = fetch_one(
        cur, f"select count(*) as n from activity_event e where {' and '.join(where)}", params
    )
    rows = fetch_all(
        cur,
        f"""
        select e.*, p.name as project_name
          from activity_event e join project p on p.id = e.project_id
         where {' and '.join(where)}
         order by e.occurred_at desc
         limit %s offset %s
        """,
        [*params, page.size, page.offset],
    )
    return PageResponse.of(rows, page, int(total["n"]) if total else 0)


def notifications(cur: Any, principal: AuthPrincipal, size: int) -> dict[str, Any]:
    """내 역할이 알아야 할 최근 활동과 미읽음 수. 배정된 사업만."""
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if not allowed:
        return {"items": [], "unread": 0, "seenAt": None}
    seen = fetch_one(
        cur, "select seen_at from notification_seen where user_id = %s", (principal.user_id,)
    )
    seen_at = seen["seen_at"] if seen else None
    where = ["e.project_id = any(%s::uuid[])"]
    params: list[Any] = [allowed]
    audiences = _audiences(principal)
    if audiences is not None:
        where.append("e.audience = any(%s)")
        params.append(audiences)
    # 자기가 한 일은 자기에게 알리지 않는다
    where.append("(e.actor_user_id is null or e.actor_user_id <> %s)")
    params.append(principal.user_id)
    clause = " and ".join(where)
    rows = fetch_all(
        cur,
        f"""
        select e.*, p.name as project_name
          from activity_event e join project p on p.id = e.project_id
         where {clause}
         order by e.occurred_at desc
         limit %s
        """,
        [*params, size],
    )
    unread_sql = f"select count(*) as n from activity_event e where {clause}"
    unread_params = list(params)
    if seen_at is not None:
        unread_sql += " and e.occurred_at > %s"
        unread_params.append(seen_at)
    unread = fetch_one(cur, unread_sql, unread_params)
    return {"items": rows, "unread": int(unread["n"]) if unread else 0, "seenAt": seen_at}


def mark_seen(cur: Any, principal: AuthPrincipal) -> datetime:
    now = datetime.now(UTC)
    cur.execute(
        """
        insert into notification_seen (user_id, seen_at) values (%s, %s)
        on conflict (user_id) do update set seen_at = excluded.seen_at
        """,
        (principal.user_id, now),
    )
    return now
