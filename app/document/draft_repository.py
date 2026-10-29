"""structuring_draft SQL. 문서 하나에 초안 하나다(uq_structuring_draft__upload)."""

from typing import Any

from psycopg.types.json import Jsonb

from app.db import fetch_one


def upsert(
    cur: Any,
    document_id: str,
    model: str,
    draft: dict[str, Any],
    proposed_type: str | None,
    type_rejected: bool,
) -> str:
    """초안을 새로 쓴다. 이미 있으면 내용을 갈고 상태를 제안으로 되돌린다."""
    row = fetch_one(
        cur,
        """
        insert into structuring_draft
          (document_upload_id, model, draft_json, proposed_type, type_rejected, status)
        values (%s, %s, %s, %s, %s, 'PROPOSED')
        on conflict (document_upload_id) do update set
           model = excluded.model, draft_json = excluded.draft_json,
           proposed_type = excluded.proposed_type, type_rejected = excluded.type_rejected,
           status = 'PROPOSED', confirmed_by_user_id = null, confirmed_at = null,
           work_product_id = null, updated_at = now()
        returning id
        """,
        (document_id, model, Jsonb(draft), proposed_type, type_rejected),
    )
    return str(row["id"])


def find_by_document(cur: Any, document_id: str) -> dict[str, Any] | None:
    """초안과 문서를 함께 읽는다. 확정에 문서의 사업·보관 경로가 필요하다."""
    return fetch_one(
        cur,
        """
        select s.id, s.document_upload_id, s.model, s.draft_json, s.proposed_type,
               s.type_rejected, s.status, s.work_product_id, s.created_at,
               d.project_id, d.original_filename, d.stored_path, d.status as document_status
          from structuring_draft s
          join document_upload d on d.id = s.document_upload_id
         where s.document_upload_id = %s
        """,
        (document_id,),
    )


def mark_confirmed(
    cur: Any, draft_id: str, user_id: str, work_product_id: str, status: str
) -> None:
    """status 는 CONFIRMED 또는 MANUAL_OVERRIDE. 제안한 유형과 다르게 확정하면 후자다."""
    cur.execute(
        """
        update structuring_draft
           set status = %s, confirmed_by_user_id = %s, confirmed_at = now(),
               work_product_id = %s, updated_at = now()
         where id = %s
        """,
        (status, user_id, work_product_id, draft_id),
    )


def mark_rejected(cur: Any, draft_id: str, user_id: str) -> None:
    cur.execute(
        """
        update structuring_draft
           set status = 'REJECTED', confirmed_by_user_id = %s, confirmed_at = now(),
               updated_at = now()
         where id = %s
        """,
        (user_id, draft_id),
    )


def set_document_status(cur: Any, document_id: str, status: str) -> None:
    """문서 상태 전이. STRUCTURED → CONFIRMED | REJECTED 는 여기서만 바꾼다."""
    cur.execute(
        "update document_upload set status = %s, updated_at = now() where id = %s",
        (status, document_id),
    )

