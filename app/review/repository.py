from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one

_SELECT = """
    select r.id, r.project_id, r.target_type, r.target_key, r.target_label, r.title, r.body,
           r.status, r.requested_at, r.snapshot_json, r.report_body, r.reported_at,
           r.report_snapshot_json, r.confirmed_at, r.rerequest_count, r.updated_at,
           rq.name as requested_by_name, rp.name as reported_by_name, cf.name as confirmed_by_name
      from review_request r
      join app_user rq on rq.id = r.requested_by_user_id
      left join app_user rp on rp.id = r.reported_by_user_id
      left join app_user cf on cf.id = r.confirmed_by_user_id
"""


def insert(
    cur: Any,
    project_id: str,
    target_type: str,
    target_key: str,
    target_label: str,
    title: str,
    body: str,
    requested_by: str,
    snapshot: dict[str, Any],
    now: datetime,
) -> str:
    row = fetch_one(
        cur,
        """
        insert into review_request
          (project_id, target_type, target_key, target_label, title, body,
           requested_by_user_id, requested_at, snapshot_json)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (project_id, target_type, target_key, target_label, title, body,
         requested_by, now, Jsonb(snapshot)),
    )
    return str(row["id"])


def find_by_id(cur: Any, request_id: str) -> dict[str, Any] | None:
    return fetch_one(cur, _SELECT + " where r.id = %s", (request_id,))


def _filter(status: str | None) -> tuple[str, list[Any]]:
    if status:
        return " and r.status = %s", [status]
    return "", []


def count(cur: Any, project_id: str, status: str | None) -> int:
    where, params = _filter(status)
    row = fetch_one(
        cur,
        f"select count(*) as n from review_request r where r.project_id = %s {where}",
        (project_id, *params),
    )
    return int(row["n"]) if row else 0


def search(
    cur: Any, project_id: str, status: str | None, page: PageQuery
) -> list[dict[str, Any]]:
    """안 끝난 것이 위로, 그 안에서는 최근에 움직인 순서."""
    where, params = _filter(status)
    return fetch_all(
        cur,
        _SELECT
        + f" where r.project_id = %s {where}"
        + " order by (r.status = 'CONFIRMED'), r.updated_at desc limit %s offset %s",
        (project_id, *params, page.size, page.offset),
    )


def mark_reported(
    cur: Any, request_id: str, body: str, actor: str, snapshot: dict[str, Any], now: datetime
) -> None:
    cur.execute(
        """
        update review_request
           set status = 'REPORTED', report_body = %s, reported_by_user_id = %s,
               reported_at = %s, report_snapshot_json = %s, updated_at = %s
         where id = %s
        """,
        (body, actor, now, Jsonb(snapshot), now, request_id),
    )


def mark_confirmed(cur: Any, request_id: str, actor: str, now: datetime) -> None:
    cur.execute(
        """
        update review_request
           set status = 'CONFIRMED', confirmed_by_user_id = %s, confirmed_at = %s, updated_at = %s
         where id = %s
        """,
        (actor, now, now, request_id),
    )


def mark_rerequested(
    cur: Any, request_id: str, body: str, snapshot: dict[str, Any], now: datetime
) -> None:
    """다시 요청이다. 보고·확인 칸을 비우고 요청 시점 상태를 새로 뜬다.

    지난 보고는 이력(review_request_event)에 남는다.
    """
    cur.execute(
        """
        update review_request
           set status = 'REQUESTED', body = %s, requested_at = %s, snapshot_json = %s,
               report_body = null, reported_by_user_id = null, reported_at = null,
               report_snapshot_json = null, confirmed_by_user_id = null, confirmed_at = null,
               rerequest_count = rerequest_count + 1, updated_at = %s
         where id = %s
        """,
        (body, now, Jsonb(snapshot), now, request_id),
    )


def insert_event(
    cur: Any,
    request_id: str,
    kind: str,
    body: str | None,
    actor: str,
    snapshot: dict[str, Any],
    now: datetime,
) -> None:
    cur.execute(
        """
        insert into review_request_event
          (review_request_id, kind, body, actor_user_id, snapshot_json, created_at)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (request_id, kind, body, actor, Jsonb(snapshot), now),
    )


def list_events(cur: Any, request_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select e.id, e.kind, e.body, e.snapshot_json, e.created_at, u.name as actor_name
          from review_request_event e
          join app_user u on u.id = e.actor_user_id
         where e.review_request_id = %s
         order by e.created_at, e.id
        """,
        (request_id,),
    )


def open_counts(cur: Any, project_ids: list[str]) -> dict[str, int]:
    """미처리 = 확인완료가 아닌 것. 요청받은 쪽이 움직여야 하는 건수다."""
    rows = fetch_all(
        cur,
        """
        select project_id, count(*) as cnt from review_request
         where project_id = any(%s) and status <> 'CONFIRMED'
         group by project_id
        """,
        (project_ids,),
    )
    return {str(r["project_id"]): int(r["cnt"]) for r in rows}
