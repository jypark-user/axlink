"""서버 오류 기록. 500 으로 끝난 요청을 표에 남겨 최고관리자 화면에서 본다.

폐쇄망에서는 서버 로그 파일을 열어 볼 사람이 없다. 기록은 최선을 다하되 실패해도 응답을
막지 않는다. 기록하다 죽으면 로그에만 남긴다.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from app.db import fetch_all, fetch_one, tx

log = logging.getLogger(__name__)

_TRACE_LIMIT = 20_000


def record(
    *,
    method: str,
    path: str,
    status_code: int,
    code: str,
    message: str,
    exc: BaseException | None = None,
    user_id: str | None = None,
) -> None:
    trace = None
    exc_name = None
    if exc is not None:
        exc_name = type(exc).__name__[:200]
        lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        trace = "".join(lines)[-_TRACE_LIMIT:]
    try:
        with tx() as cur:
            cur.execute(
                """
                insert into app_error_log
                    (method, path, status_code, code, message, exception, traceback, user_id)
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (method[:10], path, status_code, code[:40], message, exc_name, trace, user_id),
            )
    except Exception:  # noqa: BLE001 — 기록 실패가 응답을 막으면 안 된다
        log.exception("오류 기록을 남기지 못했습니다")


def list_recent(cur: Any, page: int, size: int) -> tuple[list[dict[str, Any]], int]:
    total = fetch_one(cur, "select count(*) as n from app_error_log")
    rows = fetch_all(
        cur,
        """
        select e.id, e.occurred_at, e.method, e.path, e.status_code, e.code, e.message,
               e.exception, e.traceback, u.username, u.name as user_name
          from app_error_log e
          left join app_user u on u.id = e.user_id
         order by e.occurred_at desc
         limit %s offset %s
        """,
        (size, page * size),
    )
    return rows, int(total["n"]) if total else 0


def clear(cur: Any) -> int:
    cur.execute("delete from app_error_log")
    return cur.rowcount
