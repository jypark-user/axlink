"""사업 목록 조회와 요약 지표 집계.

지표는 전부 SQL 집계다. LLM 이 수치를 만들지 않는다는 절대 규칙 1 이 여기서부터 지켜진다.
"""

from datetime import datetime
from typing import Any

from app.common import clock
from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one
from app.standard.repository import in_rate_scope

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


def insert_project(
    cur: Any,
    client_org_id: str,
    name: str,
    start_date: Any,
    end_date: Any,
    description: str,
    contractor_name: str | None,
    delete_password_hash: str,
) -> str:
    row = fetch_one(
        cur,
        """
        insert into project
          (client_org_id, name, start_date, end_date, description, contractor_name,
           delete_password_hash, status, current_si_phase)
        values (%s, %s, %s, %s, %s, %s, %s, 'PLANNING', 'SI_1')
        returning id
        """,
        (client_org_id, name, start_date, end_date, description, contractor_name,
         delete_password_hash),
    )
    return str(row["id"])


_UPDATABLE = {
    "name": "name",
    "start_date": "start_date",
    "end_date": "end_date",
    "description": "description",
    "contractor_name": "contractor_name",
    "current_si_phase": "current_si_phase",
    "status": "status",
    "closed_at": "closed_at",
}


def update_project(cur: Any, project_id: str, fields: dict[str, Any]) -> None:
    """준 컬럼만 바꾼다. 컬럼 이름은 화이트리스트로만 받는다."""
    sets, params = ["updated_at = now()"], []
    for key, value in fields.items():
        column = _UPDATABLE[key]
        sets.append(f"{column} = %s")
        params.append(value)
    cur.execute(
        f"update project set {', '.join(sets)} where id = %s", (*params, project_id)
    )


def find_delete_hash(cur: Any, project_id: str) -> str | None:
    row = fetch_one(cur, "select delete_password_hash from project where id = %s", (project_id,))
    return row["delete_password_hash"] if row else None


def delete_project(cur: Any, project_id: str) -> None:
    # 하위 테이블은 전부 on delete cascade 다. 사업이 사라지면 수집분도 같이 사라진다.
    cur.execute("delete from project where id = %s", (project_id,))


def insert_default_dashboard(cur: Any, project_id: str, owner_user_id: str) -> str:
    row = fetch_one(
        cur,
        """
        insert into dashboard (project_id, owner_user_id, name, is_default)
        values (%s, %s, '사업 현황', true)
        returning id
        """,
        (project_id, owner_user_id),
    )
    return str(row["id"])


# --- 할당 -----------------------------------------------------------------

_ASSIGNMENT_SELECT = """
    select a.id, a.project_id, a.contractor_org_id, o.name as contractor_org_name,
           a.user_id, u.name as user_name, u.username, a.status, a.created_at
      from project_assignment a
      join app_user u on u.id = a.user_id
      join organization o on o.id = a.contractor_org_id
"""


def list_assignments(cur: Any, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        _ASSIGNMENT_SELECT
        + " where a.project_id = %s and a.status = 'ACTIVE' order by a.created_at",
        (project_id,),
    )


def find_assignment(cur: Any, project_id: str, user_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        _ASSIGNMENT_SELECT + " where a.project_id = %s and a.user_id = %s"
        " order by a.created_at desc limit 1",
        (project_id, user_id),
    )


def find_assignment_by_id(cur: Any, assignment_id: str) -> dict[str, Any] | None:
    return fetch_one(cur, _ASSIGNMENT_SELECT + " where a.id = %s", (assignment_id,))


def insert_assignment(
    cur: Any, project_id: str, contractor_org_id: str, user_id: str, assigned_by: str
) -> str:
    row = fetch_one(
        cur,
        """
        insert into project_assignment
          (project_id, contractor_org_id, user_id, assigned_by_user_id, status)
        values (%s, %s, %s, %s, 'ACTIVE')
        returning id
        """,
        (project_id, contractor_org_id, user_id, assigned_by),
    )
    return str(row["id"])


def reactivate_assignment(cur: Any, assignment_id: str) -> None:
    cur.execute(
        "update project_assignment set status = 'ACTIVE', revoked_at = null, updated_at = now()"
        " where id = %s",
        (assignment_id,),
    )


def revoke_assignment(cur: Any, assignment_id: str, now: datetime) -> None:
    cur.execute(
        "update project_assignment set status = 'REVOKED', revoked_at = %s, updated_at = %s"
        " where id = %s",
        (now, now, assignment_id),
    )


def find_user_in_org(cur: Any, user_id: str, org_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        "select id, role, status, name from app_user where id = %s and organization_id = %s",
        (user_id, org_id),
    )


def find_organization(cur: Any, org_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur, "select id, name, type, status from organization where id = %s", (org_id,)
    )


def find_organization_by_name(cur: Any, name: str) -> dict[str, Any] | None:
    return fetch_one(
        cur, "select id, name, type, status from organization where name = %s", (name,)
    )


def insert_organization(cur: Any, name: str, org_type: str) -> str:
    row = fetch_one(
        cur,
        "insert into organization (name, type, status) values (%s, %s, 'ACTIVE') returning id",
        (name, org_type),
    )
    return str(row["id"])


def insert_user(
    cur: Any, org_id: str, username: str, name: str, password_hash: str, role: str
) -> str:
    row = fetch_one(
        cur,
        """
        insert into app_user (organization_id, username, name, password_hash, role, status)
        values (%s, %s, %s, %s, %s, 'ACTIVE')
        returning id
        """,
        (org_id, username, name, password_hash, role),
    )
    return str(row["id"])


# --- 초대 -----------------------------------------------------------------

def insert_invite(
    cur: Any, project_id: str, token_hash: str, expires_at: datetime, created_by: str,
    organization_id: str | None = None,
) -> dict[str, Any]:
    return fetch_one(
        cur,
        """
        insert into project_invite (project_id, token_hash, expires_at, created_by_user_id,
                                    organization_id)
        values (%s, %s, %s, %s, %s)
        returning id, project_id, expires_at, revoked_at, created_at, organization_id
        """,
        (project_id, token_hash, expires_at, created_by, organization_id),
    )


def list_open_invites(cur: Any, project_id: str, now: datetime) -> list[dict[str, Any]]:
    """아직 쓸 수 있는 초대 링크. 취소·만료된 것은 뺀다. 토큰 원문은 없다(해시만 저장)."""
    return fetch_all(
        cur,
        """
        select i.id, i.project_id, i.expires_at, i.revoked_at, i.created_at,
               i.organization_id, co.name as contractor_org_name
          from project_invite i
          left join organization co on co.id = i.organization_id
         where i.project_id = %s and i.revoked_at is null and i.expires_at > %s
         order by i.created_at desc
        """,
        (project_id, now),
    )


def revoke_invite(cur: Any, project_id: str, invite_id: str, now: datetime) -> bool:
    cur.execute(
        """
        update project_invite set revoked_at = %s
         where id::text = %s and project_id = %s and revoked_at is null
        """,
        (now, invite_id, project_id),
    )
    return cur.rowcount == 1


def find_invite_by_hash(cur: Any, token_hash: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select i.id, i.project_id, i.expires_at, i.revoked_at, i.created_by_user_id,
               p.name as project_name, o.name as client_org_name,
               i.organization_id, co.name as contractor_org_name
          from project_invite i
          join project p on p.id = i.project_id
          join organization o on o.id = p.client_org_id
          left join organization co on co.id = i.organization_id
         where i.token_hash = %s
        """,
        (token_hash,),
    )


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
    # 이행률 재료. 요구사항 목록을 확정했으면 확정 목록만 센다(DEC-11)
    req = fetch_one(
        cur,
        f"""
        select count(*) as total,
               count(*) filter (where r.status in ('VERIFIED','ACCEPTED')) as accepted
          from requirement r where r.project_id = %s and {in_rate_scope("r")}
        """,
        (project_id,),
    )
    issue = fetch_one(
        cur,
        "select count(*) filter (where status in ('OPEN','IN_PROGRESS')) as open_count "
        "from issue where project_id = %s and issue_kind = 'GENERAL'",
        (project_id,),
    )
    # 산출물 승인 수: WBS 가 정한 산출물 기준(DEC-12). 목록·현황과 같은 산정
    from app.dashboard import service as dashboard_service  # 순환 import 회피

    wp_approved, wp_total = dashboard_service.deliverable_approval_now(
        cur, project_id, clock.today()
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
        "workProductApproved": wp_approved,
        "workProductTotal": wp_total,
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
