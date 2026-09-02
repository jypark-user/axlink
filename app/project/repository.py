"""사업 목록 조회와 요약 지표 집계.

지표는 전부 SQL 집계다. LLM 이 수치를 만들지 않는다는 절대 규칙 1 이 여기서부터 지켜진다.
"""

from typing import Any

from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one

# 파일럿 ProjectMetricsReader.REQUIRED_WORK_PRODUCT_TOTAL 과 같은 값이다 (29110 산출물 22종).
REQUIRED_WORK_PRODUCT_TOTAL = 22

_SORT_WHITELIST = {
    "name": "p.name",
    "startDate": "p.start_date",
    "endDate": "p.end_date",
    "status": "p.status",
    "createdAt": "p.created_at",
    "updatedAt": "p.updated_at",
}


def sort_clause(sort: str | None) -> str:
    """정렬은 화이트리스트로만 받는다. 사용자 입력을 SQL 에 잇지 않는다."""
    if not sort:
        return "p.created_at desc"
    field, _, direction = sort.partition(",")
    column = _SORT_WHITELIST.get(field.strip())
    if column is None:
        return "p.created_at desc"
    return f"{column} {'asc' if direction.strip().lower() == 'asc' else 'desc'}"


def _scope_filter(
    allowed_ids: list[str], status: str | None, q: str | None
) -> tuple[str, list[Any]]:
    where = ["p.id = any(%s)"]
    params: list[Any] = [allowed_ids]
    if status:
        where.append("p.status = %s")
        params.append(status)
    if q:
        where.append("p.name ilike %s")
        params.append(f"%{q}%")
    return " and ".join(where), params


def count_projects(cur: Any, allowed_ids: list[str], status: str | None, q: str | None) -> int:
    clause, params = _scope_filter(allowed_ids, status, q)
    row = fetch_one(cur, f"select count(*) as cnt from project p where {clause}", params)
    return int(row["cnt"]) if row else 0


def search_projects(
    cur: Any, allowed_ids: list[str], status: str | None, q: str | None, page: PageQuery
) -> list[dict[str, Any]]:
    clause, params = _scope_filter(allowed_ids, status, q)
    sql = f"""
        select p.id, p.name, p.status, p.start_date, p.end_date, p.current_si_phase,
               p.client_org_id, p.contractor_name, p.updated_at, o.name as client_org_name
          from project p
          join organization o on o.id = p.client_org_id
         where {clause}
         order by {sort_clause(page.sort)}
         limit %s offset %s
    """
    return fetch_all(cur, sql, [*params, page.size, page.offset])


def find_by_id(cur: Any, project_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select p.id, p.client_org_id, p.name, p.description, p.contractor_name,
               p.status, p.start_date, p.end_date, p.current_si_phase,
               p.created_at, p.updated_at, o.name as client_org_name
          from project p
          join organization o on o.id = p.client_org_id
         where p.id = %s
        """,
        (project_id,),
    )


def full_metrics(cur: Any, project_id: str) -> dict[str, Any]:
    """단일 사업의 전체 지표. 전부 SQL 집계다 — 절대 규칙 1."""
    req = fetch_one(
        cur,
        """
        select count(*) as total,
               count(*) filter (where status in ('VERIFIED','ACCEPTED')) as accepted
          from requirement where project_id = %s
        """,
        (project_id,),
    )
    issue = fetch_one(
        cur,
        "select count(*) filter (where status in ('OPEN','IN_PROGRESS')) as open_count "
        "from issue where project_id = %s",
        (project_id,),
    )
    wp = fetch_one(
        cur,
        """
        select count(*) filter (where status = 'APPROVED') as approved, count(*) as total
          from work_product where project_id = %s
        """,
        (project_id,),
    )
    risk = fetch_one(
        cur,
        "select count(*) as cnt from risk where project_id = %s and status <> 'CLOSED'",
        (project_id,),
    )
    coverage = fetch_one(
        cur,
        """
        with total as (
          select count(distinct id) as n from requirement where project_id = %s
        ),
        traced as (
          select count(distinct r.id) as n
            from requirement r
            join trace_link tl on tl.to_type = 'REQUIREMENT' and tl.to_id = r.id
             and tl.link_kind = 'TESTS' and tl.status = 'ACTIVE'
           where r.project_id = %s
        )
        select case when (select n from total) = 0 then 0
                    else round(100.0 * (select n from traced) / (select n from total))::int
               end as coverage
        """,
        (project_id, project_id),
    )
    synced = fetch_one(
        cur,
        "select max(last_synced_at) as last_synced from tool_connection where project_id = %s",
        (project_id,),
    )
    return {
        "requirementTotal": int(req["total"]),
        "requirementAccepted": int(req["accepted"]),
        "issueOpen": int(issue["open_count"]),
        "riskOpen": int(risk["cnt"]),
        "workProductApproved": int(wp["approved"]),
        "workProductTotal": int(wp["total"]),
        "traceabilityCoverage": int(coverage["coverage"]),
        "lastSyncedAt": synced["last_synced"],
    }


def assignment_count(cur: Any, project_id: str) -> int:
    row = fetch_one(
        cur,
        "select count(*) as cnt from project_assignment "
        "where project_id = %s and status = 'ACTIVE'",
        (project_id,),
    )
    return int(row["cnt"]) if row else 0


def connection_count(cur: Any, project_id: str) -> int:
    row = fetch_one(
        cur, "select count(*) as cnt from tool_connection where project_id = %s", (project_id,)
    )
    return int(row["cnt"]) if row else 0


def default_dashboard_id(cur: Any, project_id: str) -> str | None:
    row = fetch_one(
        cur,
        "select id from dashboard where project_id = %s and is_default and status = 'ACTIVE' "
        "order by created_at limit 1",
        (project_id,),
    )
    return str(row["id"]) if row else None


def approved_work_products(cur: Any, project_ids: list[str]) -> dict[str, int]:
    rows = fetch_all(
        cur,
        """
        select project_id, count(*) filter (where status = 'APPROVED') as approved
          from work_product
         where project_id = any(%s)
         group by project_id
        """,
        (project_ids,),
    )
    return {str(r["project_id"]): int(r["approved"]) for r in rows}


def open_risks(cur: Any, project_ids: list[str]) -> dict[str, int]:
    rows = fetch_all(
        cur,
        """
        select project_id, count(*) as cnt
          from risk
         where project_id = any(%s) and status <> 'CLOSED'
         group by project_id
        """,
        (project_ids,),
    )
    return {str(r["project_id"]): int(r["cnt"]) for r in rows}


def open_correction_actions(cur: Any, project_ids: list[str]) -> dict[str, int]:
    """status = 'OPEN' 만 센다. 파일럿과 같은 필터다.

    상태값에는 OVERDUE 도 있어서 기한이 지난 시정조치는 이 수에서 빠진다.
    의도인지 결함인지 확인이 필요하나, 수치가 파일럿과 달라지면 안 되므로 지금은 그대로 옮긴다.
    """
    rows = fetch_all(
        cur,
        """
        select project_id, count(*) as cnt
          from correction_action
         where project_id = any(%s) and status = 'OPEN'
         group by project_id
        """,
        (project_ids,),
    )
    return {str(r["project_id"]): int(r["cnt"]) for r in rows}
