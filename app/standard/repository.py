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


def upsert_work_product(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str | None:
    """같은 유형의 현행 산출물 자리를 채운다. 자리가 없으면 새로 만든다.

    uq_work_product__current (project_id, type) where is_current 때문에 무턱대고
    insert 하면 안 된다. 산출물 목록은 미리 정의된 자리이고 수집은 그걸 채우는 일이다.
    """
    row = fetch_one(
        cur,
        "select id from work_product where project_id = %s and type = %s and is_current",
        (project_id, rec["type"]),
    )
    if row is not None:
        fetch_one(
            cur,
            """
            update work_product
               set title = %s, version = %s, file_uri = %s, external_url = %s,
                   tool_connection_id = %s, external_id = %s, source_kind = 'TOOL',
                   status = case when status = 'NONE' then 'SUBMITTED' else status end,
                   submitted_at = coalesce(submitted_at, now()), updated_at = now()
             where id = %s
            returning id
            """,
            (
                rec["title"], rec["version"], rec["file_uri"], rec["external_url"],
                connection_id, external_id, row["id"],
            ),
        )
        return str(row["id"])

    created = fetch_one(
        cur,
        """
        insert into work_product
          (project_id, type, version, title, status, pm_activity, file_uri, external_url,
           tool_connection_id, external_id, source_kind, submitted_at)
        values (%s, %s, %s, %s, 'SUBMITTED', 'PM_1', %s, %s, %s, %s, 'TOOL', now())
        returning id
        """,
        (
            project_id, rec["type"], rec["version"], rec["title"],
            rec["file_uri"], rec["external_url"], connection_id, external_id,
        ),
    )
    return str(created["id"])


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


def list_work_products(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """현행 산출물 22종. 아직 안 낸 것도 자리로 나와야 제출 현황이 성립한다."""
    return fetch_all(
        cur,
        """
        select w.id, w.project_id, w.type, w.version, w.title, w.status,
               w.pm_activity, w.si_activity, w.applicable, w.due_date,
               w.file_uri, w.external_url, w.approved_at, w.updated_at,
               u.name as approved_by
          from work_product w
          left join app_user u on u.id = w.approved_by_user_id
         where w.project_id = %s and w.is_current
         order by w.pm_activity nulls last, w.si_activity nulls last, w.type
        """,
        (project_id,),
    )
