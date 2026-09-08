"""document_upload SQL."""

from typing import Any

from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one

_COLUMNS = """
    d.id, d.project_id, d.original_filename, d.stored_path, d.content_type, d.file_ext,
    d.size_bytes, d.file_hash, d.page_count, d.status, d.error, d.created_at,
    length(d.extracted_text) as extracted_chars,
    u.name as uploaded_by
"""
_FROM = "from document_upload d join app_user u on u.id = d.uploaded_by_user_id"


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
           content_type, file_ext, size_bytes, file_hash, status)
        values (%s, %s, %s, %s, %s, %s, %s, %s, 'UPLOADED')
        returning id
        """,
        (
            project_id, user_id, filename, stored_path,
            content_type, file_ext, size_bytes, file_hash,
        ),
    )
    return str(row["id"])


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
