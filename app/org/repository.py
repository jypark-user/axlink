from typing import Any

from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one

_FROM = """
    from app_user u
    join organization o on o.id = u.organization_id
"""


def _filter(
    role: str | None, status: str | None, org_id: str | None, q: str | None
) -> tuple[str, list[Any]]:
    where, params = [], []
    if role:
        where.append("u.role = %s")
        params.append(role)
    if status:
        where.append("u.status = %s")
        params.append(status)
    if org_id:
        where.append("u.organization_id = %s")
        params.append(org_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        where.append("(u.username ilike %s or u.name ilike %s or o.name ilike %s)")
        params += [like, like, like]
    return (" where " + " and ".join(where)) if where else "", params


def count_users(
    cur: Any, role: str | None, status: str | None, org_id: str | None, q: str | None
) -> int:
    where, params = _filter(role, status, org_id, q)
    row = fetch_one(cur, f"select count(*) as n {_FROM} {where}", params)
    return int(row["n"]) if row else 0


def search_users(
    cur: Any,
    role: str | None,
    status: str | None,
    org_id: str | None,
    q: str | None,
    page: PageQuery,
) -> list[dict[str, Any]]:
    where, params = _filter(role, status, org_id, q)
    return fetch_all(
        cur,
        f"""
        select u.id, u.organization_id, o.name as organization_name, u.username, u.name,
               u.role, u.status, u.last_login_at, u.created_at
        {_FROM} {where}
         order by o.name, u.name
         limit %s offset %s
        """,
        (*params, page.size, page.offset),
    )
