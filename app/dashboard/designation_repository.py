"""지정 산출물 SQL (UC-033, V66). 화면 조립과 권한은 designation.py 가 한다."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from app.db import fetch_all, fetch_one

_COLUMNS = """
    id, project_id, task_key, wbs_id_at, task_name_at, name, description, product_type, guide,
    template_filename, template_content_type, template_size, template_uploaded_at, active,
    created_at, updated_at, origin, wbs_name_at
"""


def list_active(cur: Any, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        f"select {_COLUMNS} from wbs_designated_deliverable "
        "where project_id = %s and active order by created_at, id",
        (project_id,),
    )


def sync_wbs_expected(cur: Any, project_id: str) -> None:
    """WBS 산출물 열을 예상 산출물 행(origin WBS)으로 맞춘다(V73). 몇 번 불러도 같다.

    말단 작업마다 하나다. 없으면 만들고, 있으면 번호·작업명과 (이름을 고치지 않았으면) 이름을
    산출물 열에 맞춘다. 발주기관이 거둔 행은 비활성으로 남아 있어 다시 만들지 않는다.
    산출물 열이 비면 행을 쉬게 한다(비활성 + wbs_name_at 비움). 열이 다시 차면 깨운다. 거둔 행은
    wbs_name_at 이 남아 있어 쉬는 행과 갈린다.
    """
    cur.execute(
        """
        update wbs_designated_deliverable dd
           set active = false, wbs_name_at = null, updated_at = now()
          from wbs_item w
         where dd.project_id = %(p)s and dd.origin = 'WBS' and dd.active
           and w.project_id = dd.project_id and w.task_key = dd.task_key and w.active
           and coalesce(btrim(w.deliverable), '') = ''
        """,
        {"p": project_id},
    )
    cur.execute(
        """
        update wbs_designated_deliverable dd
           set active = true, updated_at = now()
          from wbs_item w
         where dd.project_id = %(p)s and dd.origin = 'WBS' and not dd.active
           and dd.wbs_name_at is null
           and w.project_id = dd.project_id and w.task_key = dd.task_key
           and w.active and w.weight is not null and coalesce(btrim(w.deliverable), '') <> ''
        """,
        {"p": project_id},
    )
    cur.execute(
        """
        update wbs_designated_deliverable dd
           set name = case when dd.wbs_name_at is null or dd.name = dd.wbs_name_at
                           then left(btrim(w.deliverable), 300)
                           else dd.name end,
               wbs_name_at = left(btrim(w.deliverable), 300),
               wbs_id_at = w.wbs_id, task_name_at = w.name, updated_at = now()
          from wbs_item w
         where dd.project_id = %(p)s and dd.origin = 'WBS' and dd.active
           and w.project_id = dd.project_id and w.task_key = dd.task_key
           and w.active and w.weight is not null and coalesce(btrim(w.deliverable), '') <> ''
           and (dd.wbs_name_at is distinct from left(btrim(w.deliverable), 300)
                or dd.wbs_id_at <> w.wbs_id or dd.task_name_at <> w.name)
        """,
        {"p": project_id},
    )
    cur.execute(
        """
        insert into wbs_designated_deliverable
          (project_id, task_key, wbs_id_at, task_name_at, name, origin, wbs_name_at)
        select w.project_id, w.task_key, w.wbs_id, w.name, left(btrim(w.deliverable), 300),
               'WBS', left(btrim(w.deliverable), 300)
          from wbs_item w
         where w.project_id = %(p)s and w.active and w.weight is not null
           and w.task_key is not null and coalesce(btrim(w.deliverable), '') <> ''
           and not exists (
             select 1 from wbs_designated_deliverable dd
              where dd.project_id = w.project_id and dd.task_key = w.task_key
                and dd.origin = 'WBS'
           )
        on conflict do nothing
        """,
        {"p": project_id},
    )


def find(cur: Any, designated_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur, f"select {_COLUMNS} from wbs_designated_deliverable where id = %s", (designated_id,)
    )


def insert(
    cur: Any, project_id: str, task_key: str, wbs_id: str, task_name: str, name: str,
    description: str | None, product_type: str | None, guide: str | None, user_id: str,
) -> dict[str, Any]:
    row = fetch_one(
        cur,
        f"""
        insert into wbs_designated_deliverable
          (project_id, task_key, wbs_id_at, task_name_at, name, description, product_type, guide,
           created_by_user_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning {_COLUMNS}
        """,
        (project_id, task_key, wbs_id, task_name, name, description, product_type, guide, user_id),
    )
    assert row is not None
    return row


def update_fields(cur: Any, designated_id: str, fields: dict[str, Any]) -> None:
    """이름이 정해진 칸만 고친다. 칸 이름은 서비스가 정한 목록에서만 온다."""
    allowed = {"name", "description", "product_type", "guide", "task_key", "wbs_id_at",
               "task_name_at", "active"}
    assert set(fields) <= allowed, fields
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    cur.execute(
        f"update wbs_designated_deliverable set {sets}, updated_at = now() where id = %s",
        (*fields.values(), designated_id),
    )


def save_template(
    cur: Any, designated_id: str, filename: str, content_type: str, content: bytes
) -> None:
    cur.execute(
        """
        update wbs_designated_deliverable
           set template_filename = %s, template_content_type = %s, template_bytes = %s,
               template_size = %s, template_uploaded_at = now(), updated_at = now()
         where id = %s
        """,
        (filename, content_type, content, len(content), designated_id),
    )


def load_template(cur: Any, designated_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select project_id, template_filename, template_content_type, template_bytes
          from wbs_designated_deliverable
         where id = %s and template_bytes is not null
        """,
        (designated_id,),
    )


def add_event(
    cur: Any, designated_id: str, kind: str, user_id: str, detail: dict[str, Any]
) -> None:
    cur.execute(
        """
        insert into wbs_designated_deliverable_event
          (designated_id, kind, actor_user_id, detail_json)
        values (%s, %s, %s, %s)
        """,
        (designated_id, kind, user_id, Jsonb(detail)),
    )


def events(cur: Any, designated_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select e.kind, e.at, e.detail_json, u.name as actor_name, u.role as actor_role
          from wbs_designated_deliverable_event e
          join app_user u on u.id = e.actor_user_id
         where e.designated_id = %s
         order by e.at, e.id
        """,
        (designated_id,),
    )


def submissions(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """지정 항목에 이어 올린 문서와 그 산출물 버전. 최근 것이 앞에 온다.

    실패·반려(처리 반려)된 문서는 뺀다. 확정 전 문서도 낸다(「등록, 제출 전」으로 보인다).
    """
    return fetch_all(
        cur,
        """
        select d.id, d.designated_deliverable_id, d.original_filename, d.created_at,
               d.processing_state, s.status as draft_status, s.work_product_id,
               d.review_status, d.review_reason, d.reviewed_at,
               wp.version as wp_version, wp.status as wp_status, wp.reject_reason,
               wp.approved_at, wp.submitted_at, wp.is_current
          from document_upload d
          left join structuring_draft s on s.document_upload_id = d.id
          left join work_product wp on wp.id = s.work_product_id
         where d.project_id = %s and d.designated_deliverable_id is not null
           and d.status not in ('FAILED', 'REJECTED')
         order by d.created_at desc, d.id
        """,
        (project_id,),
    )


def active_leaf_by_task(cur: Any, project_id: str, task_key: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select id, wbs_id, name, task_key, weight
          from wbs_item
         where project_id = %s and task_key = %s and active and weight is not null
        """,
        (project_id, task_key),
    )


def link_document(cur: Any, document_id: str, designated_id: str, wbs_item_id: str) -> None:
    cur.execute(
        """
        update document_upload
           set designated_deliverable_id = %s, wbs_item_id = %s,
               review_status = coalesce(review_status, 'SUBMITTED'), updated_at = now()
         where id = %s
        """,
        (designated_id, wbs_item_id, document_id),
    )
