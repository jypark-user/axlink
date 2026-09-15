"""대시보드·위젯 SQL. 레이아웃과 위젯 명세의 단일 원천은 이 두 표다(설계 제약 4·5).

삭제는 status = 'DELETED' 로만 한다. 위젯 id 가 레이아웃 JSON 에 박혀 있어
행을 지우면 무엇이 있었는지 알 수 없게 된다.
"""

from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from app.db import fetch_all, fetch_one


def find_dashboard(cur: Any, dashboard_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select d.id, d.project_id, d.owner_user_id, d.name, d.layout_json, d.is_default,
               d.updated_at, p.name as project_name
          from dashboard d
          left join project p on p.id = d.project_id
         where d.id = %s and d.status = 'ACTIVE'
        """,
        (dashboard_id,),
    )


def list_dashboards(
    cur: Any, user_id: str, project_id: str | None, allowed_project_ids: list[str]
) -> list[dict[str, Any]]:
    """내가 만든 것 + 접근 가능한 사업의 기본 대시보드. 기본이 먼저, 그다음 이름순."""
    return fetch_all(
        cur,
        """
        select d.id, d.project_id, d.owner_user_id, d.name, d.is_default, d.updated_at,
               p.name as project_name,
               (select count(*) from widget w
                 where w.dashboard_id = d.id and w.status = 'ACTIVE') as widget_count
          from dashboard d
          left join project p on p.id = d.project_id
         where d.status = 'ACTIVE'
           and (%(project_id)s::uuid is null or d.project_id = %(project_id)s::uuid)
           and (d.owner_user_id = %(user_id)s
                or (d.is_default and d.project_id = any(%(allowed)s::uuid[])))
         order by d.is_default desc, d.name
        """,
        {"project_id": project_id, "user_id": user_id, "allowed": allowed_project_ids},
    )


def create_dashboard(
    cur: Any, project_id: str | None, owner_user_id: str, name: str, is_default: bool
) -> str:
    row = fetch_one(
        cur,
        """
        insert into dashboard (project_id, owner_user_id, name, is_default)
        values (%s, %s, %s, %s)
        returning id
        """,
        (project_id, owner_user_id, name, is_default),
    )
    return str(row["id"])


def update_layout(cur: Any, dashboard_id: str, layout: dict[str, Any]) -> None:
    cur.execute(
        "update dashboard set layout_json = %s, updated_at = %s where id = %s",
        (Jsonb(layout), datetime.now(UTC), dashboard_id),
    )


def list_widgets(cur: Any, dashboard_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select id, dashboard_id, template, title, spec_json, created_at, updated_at
          from widget
         where dashboard_id = %s and status = 'ACTIVE'
         order by created_at
        """,
        (dashboard_id,),
    )


def find_widget(cur: Any, widget_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select id, dashboard_id, template, title, spec_json, created_at, updated_at
          from widget
         where id = %s and status = 'ACTIVE'
        """,
        (widget_id,),
    )


def create_widget(
    cur: Any, dashboard_id: str, template: str, title: str, spec: dict[str, Any], user_id: str
) -> str:
    row = fetch_one(
        cur,
        """
        insert into widget (dashboard_id, template, title, spec_json, created_by_user_id)
        values (%s, %s, %s, %s, %s)
        returning id
        """,
        (dashboard_id, template, title, Jsonb(spec), user_id),
    )
    return str(row["id"])


def update_widget(
    cur: Any, widget_id: str, template: str, title: str, spec: dict[str, Any]
) -> None:
    cur.execute(
        """
        update widget
           set template = %s, title = %s, spec_json = %s, updated_at = %s
         where id = %s
        """,
        (template, title, Jsonb(spec), datetime.now(UTC), widget_id),
    )


def soft_delete_widget(cur: Any, widget_id: str) -> None:
    cur.execute(
        "update widget set status = 'DELETED', updated_at = %s where id = %s",
        (datetime.now(UTC), widget_id),
    )
