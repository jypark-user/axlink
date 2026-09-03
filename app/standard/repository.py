"""표준 모델 upsert. 원천 키는 (tool_connection_id, external_id) 다.

부분 유니크 인덱스라 on conflict 에 where 절을 그대로 붙여야 인덱스가 추론된다 —
ORM 을 쓰지 않는 이유 중 하나다(CLAUDE.md 1절).
"""

from typing import Any

from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one

_SOURCE_CONFLICT = """
    on conflict (tool_connection_id, external_id)
      where tool_connection_id is not null and external_id is not null
"""


def upsert_requirement(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into requirement
          (project_id, code, title, body, priority, status, assignee,
           source_created_at, source_updated_at,
           tool_connection_id, external_id, external_url, source_kind)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
        {_SOURCE_CONFLICT}
        do update set
           code = excluded.code, title = excluded.title, body = excluded.body,
           priority = excluded.priority, status = excluded.status,
           assignee = excluded.assignee,
           source_created_at = excluded.source_created_at,
           source_updated_at = excluded.source_updated_at,
           external_url = excluded.external_url, updated_at = now()
        returning id
        """,
        (
            project_id, rec["code"], rec["title"], rec["body"], rec["priority"], rec["status"],
            rec["assignee"], rec["source_created_at"], rec["source_updated_at"],
            connection_id, external_id, rec["external_url"],
        ),
    )
    return str(row["id"])


def upsert_issue(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into issue
          (project_id, issue_key, title, body, status, severity, assignee,
           source_created_at, source_updated_at, resolved_at,
           tool_connection_id, external_id, external_url, source_kind)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
        {_SOURCE_CONFLICT}
        do update set
           issue_key = excluded.issue_key, title = excluded.title, body = excluded.body,
           status = excluded.status, assignee = excluded.assignee,
           source_created_at = excluded.source_created_at,
           source_updated_at = excluded.source_updated_at,
           resolved_at = excluded.resolved_at,
           external_url = excluded.external_url, updated_at = now()
        returning id
        """,
        (
            project_id, rec["issue_key"], rec["title"], rec["body"], rec["status"],
            rec["severity"], rec["assignee"], rec["source_created_at"],
            rec["source_updated_at"], rec["resolved_at"],
            connection_id, external_id, rec["external_url"],
        ),
    )
    return str(row["id"])


def upsert_code_change(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into code_change
          (project_id, kind, title, ref_name, state, author, occurred_at,
           tool_connection_id, external_id, external_url, source_kind)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
        {_SOURCE_CONFLICT}
        do update set
           title = excluded.title, ref_name = excluded.ref_name, state = excluded.state,
           author = excluded.author, occurred_at = excluded.occurred_at,
           external_url = excluded.external_url, updated_at = now()
        returning id
        """,
        (
            project_id, rec["kind"], rec["title"], rec["ref_name"], rec["state"],
            rec["author"], rec["occurred_at"],
            connection_id, external_id, rec["external_url"],
        ),
    )
    return str(row["id"])


# --- 조회 ---------------------------------------------------------------

_REQUIREMENT_COLUMNS = """
    r.id, r.project_id, r.code, r.title, r.priority, r.status, r.assignee,
    r.tool_connection_id, r.external_id, r.external_url, r.source_kind, r.updated_at,
    c.tool as tool_name,
    exists (
      select 1 from trace_link tl
       where tl.to_type = 'REQUIREMENT' and tl.to_id = r.id
         and tl.link_kind = 'TESTS' and tl.status = 'ACTIVE'
    ) as trace_complete
"""
_REQUIREMENT_FROM = """
    from requirement r
    left join tool_connection c on c.id = r.tool_connection_id
"""


def _search(q: str | None) -> tuple[str, list[Any]]:
    """코드·제목 어느 쪽으로 찾아도 걸리게 한다.

    조건을 SQL 안에서 "%s is null" 로 처리하면 파라미터 타입을 못 정해 실패한다.
    없을 때는 조건 자체를 빼는 편이 낫다.
    """
    if not q or not q.strip():
        return "", []
    like = f"%{q.strip()}%"
    return " and (r.code ilike %s or r.title ilike %s)", [like, like]


def count_requirements(cur: Any, project_id: str, q: str | None) -> int:
    where, params = _search(q)
    row = fetch_one(
        cur,
        f"select count(*) as n from requirement r where r.project_id = %s {where}",
        (project_id, *params),
    )
    return int(row["n"]) if row else 0



def search_requirements(
    cur: Any, project_id: str, q: str | None, page: PageQuery
) -> list[dict[str, Any]]:
    where, params = _search(q)
    return fetch_all(
        cur,
        f"""
        select {_REQUIREMENT_COLUMNS} {_REQUIREMENT_FROM}
         where r.project_id = %s {where}
         order by r.code nulls last, r.created_at
         limit %s offset %s
        """,
        (project_id, *params, page.size, page.offset),
    )
