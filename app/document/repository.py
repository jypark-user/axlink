"""document_upload SQL."""

from typing import Any

from psycopg.types.json import Jsonb

from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one

_COLUMNS = """
    d.id, d.project_id, d.original_filename, d.stored_path, d.content_type, d.file_ext,
    d.size_bytes, d.file_hash, d.page_count, d.status, d.error, d.created_at,
    length(d.extracted_text) as extracted_chars,
    u.name as uploaded_by,
    s.status as draft_status, s.work_product_id as draft_work_product_id,
    s.proposed_type, d.product_type, d.wbs_item_id,
    w.wbs_id, w.name as wbs_name,
    dd.name as designated_name, dd.active as designated_active,
    d.processing_state, d.processing_error, d.processing_attempts, d.processed_at,
    d.processing_steps
"""
_FROM = """
    from document_upload d
    join app_user u on u.id = d.uploaded_by_user_id
    left join structuring_draft s on s.document_upload_id = d.id
    left join wbs_item w on w.id = d.wbs_item_id
    left join wbs_designated_deliverable dd on dd.id = d.designated_deliverable_id
"""


def find_by_hash(cur: Any, project_id: str, file_hash: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        f"select {_COLUMNS} {_FROM} where d.project_id = %s and d.file_hash = %s",
        (project_id, file_hash),
    )


def find_by_id(cur: Any, document_id: str) -> dict[str, Any] | None:
    return fetch_one(cur, f"select {_COLUMNS} {_FROM} where d.id = %s", (document_id,))


def find_text(cur: Any, document_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select id, project_id, original_filename, status, page_count,
               coalesce(extracted_text, '') as extracted_text
          from document_upload where id = %s
        """,
        (document_id,),
    )


def insert(
    cur: Any,
    project_id: str,
    user_id: str,
    filename: str,
    stored_path: str,
    content_type: str,
    file_ext: str,
    size_bytes: int,
    file_hash: str,
) -> str:
    row = fetch_one(
        cur,
        """
        insert into document_upload
          (project_id, uploaded_by_user_id, original_filename, stored_path,
           content_type, file_ext, size_bytes, file_hash, status, processing_state)
        values (%s, %s, %s, %s, %s, %s, %s, %s, 'UPLOADED', 'QUEUED')
        returning id
        """,
        (
            project_id, user_id, filename, stored_path,
            content_type, file_ext, size_bytes, file_hash,
        ),
    )
    return str(row["id"])


def link_wbs_item(cur: Any, document_id: str, wbs_item_id: str | None) -> None:
    cur.execute(
        "update document_upload set wbs_item_id = %s, updated_at = now() where id = %s",
        (wbs_item_id, document_id),
    )


def set_product_type(cur: Any, document_id: str, product_type: str | None) -> None:
    cur.execute(
        "update document_upload set product_type = %s, updated_at = now() where id = %s",
        (product_type, document_id),
    )


def mark_extracted(
    cur: Any, document_id: str, text: str, page_count: int | None, warning: str
) -> None:
    cur.execute(
        """
        update document_upload
           set extracted_text = %s, page_count = %s, status = 'EXTRACTED',
               error = nullif(%s, ''), updated_at = now()
         where id = %s
        """,
        (text, page_count, warning, document_id),
    )


def mark_failed(cur: Any, document_id: str, message: str) -> None:
    cur.execute(
        """
        update document_upload
           set status = 'FAILED', error = %s, updated_at = now()
         where id = %s
        """,
        (message[:1000], document_id),
    )


def count_by_project(cur: Any, project_id: str) -> int:
    row = fetch_one(
        cur, "select count(*) as n from document_upload where project_id = %s", (project_id,)
    )
    return int(row["n"]) if row else 0


def list_by_project(cur: Any, project_id: str, page: PageQuery) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        f"""
        select {_COLUMNS} {_FROM}
         where d.project_id = %s
         order by d.created_at desc
         limit %s offset %s
        """,
        (project_id, page.size, page.offset),
    )


def note_error(cur: Any, document_id: str, message: str) -> None:
    """상태는 그대로 두고 사유만 적는다. 추출은 됐는데 색인만 못 한 경우다."""
    cur.execute(
        "update document_upload set error = %s, updated_at = now() where id = %s",
        (message[:1000], document_id),
    )


def find_file(cur: Any, document_id: str) -> dict[str, Any] | None:
    """원본 내려받기·삭제에 필요한 최소 정보."""
    return fetch_one(
        cur,
        """
        select id, project_id, original_filename, stored_path, content_type, file_hash
          from document_upload where id = %s
        """,
        (document_id,),
    )


def delete(cur: Any, document_id: str) -> None:
    cur.execute("delete from document_upload where id = %s", (document_id,))


def count_by_stored_path(cur: Any, stored_path: str) -> int:
    """같은 파일을 가리키는 행 수. 마지막 하나를 지울 때만 원본을 지운다."""
    row = fetch_one(
        cur,
        "select count(*) as n from document_upload where stored_path = %s",
        (stored_path,),
    )
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------- 처리 대기열 (GH-121)
# 접수된 문서의 추출·색인·초안 작업. processing_state 가 QUEUED → RUNNING → DONE | FAILED 다.

_JOB_COLUMNS = (
    "id::text as id, project_id::text as project_id, original_filename, stored_path, "
    "file_ext, processing_attempts"
)


def claim_next(cur: Any) -> dict[str, Any] | None:
    """가장 오래 기다린 접수 문서 하나를 처리 중으로 바꿔 가져간다. 여럿이 동시에 불러도
    같은 문서를 두 번 가져가지 않는다(skip locked)."""
    return fetch_one(
        cur,
        f"""
        update document_upload
           set processing_state = 'RUNNING', processing_attempts = processing_attempts + 1,
               processing_started_at = now(), processing_heartbeat_at = now(),
               processing_error = null, updated_at = now()
         where id = (
               select id from document_upload
                where processing_state = 'QUEUED'
                order by created_at
                for update skip locked
                limit 1)
        returning {_JOB_COLUMNS}
        """,
    )


def start(cur: Any, document_id: str) -> dict[str, Any] | None:
    """그 문서를 바로 처리 중으로 바꾼다. 요청 안에서 처리하는 시험 실행에서 쓴다."""
    return fetch_one(
        cur,
        f"""
        update document_upload
           set processing_state = 'RUNNING', processing_attempts = processing_attempts + 1,
               processing_started_at = now(), processing_heartbeat_at = now(),
               processing_error = null, updated_at = now()
         where id = %s
        returning {_JOB_COLUMNS}
        """,
        (document_id,),
    )


def lock_for_write(cur: Any, document_id: str) -> bool:
    """쓰기 전에 문서 행을 잠근다. 처리 중에 지워졌으면 False 다. 지운 문서의 색인을
    남기지 않는다."""
    row = fetch_one(
        cur, "select 1 as ok from document_upload where id = %s for update", (document_id,)
    )
    return row is not None


def heartbeat(cur: Any, document_id: str, steps: dict[str, Any] | None = None) -> None:
    cur.execute(
        """
        update document_upload
           set processing_heartbeat_at = now(),
               processing_steps = coalesce(%s, processing_steps)
         where id = %s and processing_state = 'RUNNING'
        """,
        (Jsonb(steps) if steps is not None else None, document_id),
    )


def finish(cur: Any, document_id: str, steps: dict[str, Any]) -> None:
    cur.execute(
        """
        update document_upload
           set processing_state = 'DONE', processing_error = null, processed_at = now(),
               processing_steps = %s, updated_at = now()
         where id = %s
        """,
        (Jsonb(steps), document_id),
    )


def fail(cur: Any, document_id: str, message: str, steps: dict[str, Any]) -> None:
    cur.execute(
        """
        update document_upload
           set processing_state = 'FAILED', processing_error = %s, processed_at = now(),
               processing_steps = %s, updated_at = now()
         where id = %s
        """,
        (message[:1000], Jsonb(steps), document_id),
    )


def requeue(cur: Any, document_id: str) -> None:
    """실패한 문서를 다시 대기열에 넣는다. 같은 파일을 다시 올렸을 때다."""
    cur.execute(
        """
        update document_upload
           set processing_state = 'QUEUED', processing_error = null, processing_attempts = 0,
               updated_at = now()
         where id = %s and processing_state = 'FAILED'
        """,
        (document_id,),
    )


def recover_abandoned(
    cur: Any, stale_seconds: int, max_attempts: int, all_running: bool
) -> tuple[int, int]:
    """처리 중인 채 멈춘 작업을 되살린다. 재시작으로 끊겼거나 heartbeat 가 오래 없는 것이다.
    시도가 한도에 닿았으면 실패로 남긴다. (다시 넣은 수, 실패로 둔 수)."""
    stale = "true" if all_running else "processing_heartbeat_at < now() - make_interval(secs => %s)"
    params: tuple[Any, ...] = () if all_running else (stale_seconds,)
    failed = fetch_all(
        cur,
        f"""
        update document_upload
           set processing_state = 'FAILED', processed_at = now(), updated_at = now(),
               processing_error = '처리가 ' || processing_attempts || '번 중단되어 멈췄습니다'
                                  || '(재시작 또는 시간 초과). '
                                  || '같은 파일을 다시 올리면 다시 처리합니다.'
         where processing_state = 'RUNNING' and ({stale}) and processing_attempts >= %s
        returning id
        """,
        (*params, max_attempts),
    )
    requeued = fetch_all(
        cur,
        f"""
        update document_upload
           set processing_state = 'QUEUED', updated_at = now()
         where processing_state = 'RUNNING' and ({stale})
        returning id
        """,
        params,
    )
    return len(requeued), len(failed)
