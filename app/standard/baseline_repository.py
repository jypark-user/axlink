"""요구사항 기준선 SQL (GH-139, ARC-028). 판단은 baseline.py 가 한다."""

from typing import Any

from psycopg.types.json import Jsonb

from app.db import fetch_all, fetch_one

_BASELINE_COLUMNS = """
    b.id, b.project_id, b.version, b.status, b.document_upload_id, b.source_filename,
    b.source_file_hash, b.source_doc_version, b.submitted_at, b.returned_reason,
    b.confirmed_at, b.confirmed_by_role, b.confirm_result, b.parents_json, b.created_at,
    b.updated_at,
    cu.name as created_by_name, su.name as submitted_by_name, fu.name as confirmed_by_name
"""
_BASELINE_FROM = """
    from requirement_baseline b
    left join app_user cu on cu.id = b.created_by_user_id
    left join app_user su on su.id = b.submitted_by_user_id
    left join app_user fu on fu.id = b.confirmed_by_user_id
"""


def find_document(cur: Any, document_id: str) -> dict[str, Any] | None:
    """명세서로 쓸 문서. 추출한 글과 파일 해시까지 읽는다."""
    return fetch_one(
        cur,
        """
        select id, project_id, original_filename, file_hash, extracted_text
          from document_upload where id = %s
        """,
        (document_id,),
    )


def find_open(cur: Any, project_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        f"select {_BASELINE_COLUMNS} {_BASELINE_FROM} "
        "where b.project_id = %s and b.status in ('DRAFT', 'SUBMITTED')",
        (project_id,),
    )


def find_confirmed(cur: Any, project_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        f"select {_BASELINE_COLUMNS} {_BASELINE_FROM} "
        "where b.project_id = %s and b.status = 'CONFIRMED'",
        (project_id,),
    )


def find(cur: Any, project_id: str, baseline_id: str, lock: bool = False) -> dict[str, Any] | None:
    if lock:
        # 확정·제출처럼 상태를 바꾸는 요청은 행을 잠그고 다시 읽는다. 같은 요청이 겹쳐도
        # 둘째는 바뀐 상태를 보고 거절된다
        cur.execute(
            "select id from requirement_baseline where id = %s and project_id = %s for update",
            (baseline_id, project_id),
        )
        if cur.fetchone() is None:
            return None
    return fetch_one(
        cur,
        f"select {_BASELINE_COLUMNS} {_BASELINE_FROM} where b.id = %s and b.project_id = %s",
        (baseline_id, project_id),
    )


def next_version(cur: Any, project_id: str) -> int:
    row = fetch_one(
        cur,
        "select coalesce(max(version), 0) + 1 as v from requirement_baseline where project_id = %s",
        (project_id,),
    )
    return int(row["v"])


def insert(
    cur: Any,
    project_id: str,
    version: int,
    document: dict[str, Any],
    doc_version: str | None,
    user_id: str,
) -> str:
    row = fetch_one(
        cur,
        """
        insert into requirement_baseline
          (project_id, version, document_upload_id, source_filename, source_file_hash,
           source_doc_version, created_by_user_id)
        values (%s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            project_id,
            version,
            document["id"],
            document["original_filename"],
            document["file_hash"],
            doc_version,
            user_id,
        ),
    )
    return str(row["id"])


def set_parents(cur: Any, baseline_id: str, parents: list[dict[str, Any]]) -> None:
    cur.execute(
        "update requirement_baseline set parents_json = %s where id = %s",
        (Jsonb(parents), baseline_id),
    )


def baselines_for_parents(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """상위 요구사항을 읽을 기준선(확정본과 작업 중인 것). parents_json 이 없던 때 등록한
    것은 명세서 문서의 글을 같이 읽는다."""
    return fetch_all(
        cur,
        """
        select b.id, b.parents_json, d.extracted_text
          from requirement_baseline b
          left join document_upload d on d.id = b.document_upload_id and b.parents_json is null
         where b.project_id = %s
         order by (b.status = 'CONFIRMED') desc, b.version desc
        """,
        (project_id,),
    )


def insert_item(cur: Any, baseline_id: str, seq: int, item: dict[str, Any], origin: str) -> str:
    row = fetch_one(
        cur,
        """
        insert into requirement_baseline_item
          (baseline_id, seq, code, title, body, priority, source_location, extracted_json, origin)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            baseline_id,
            seq,
            item.get("code"),
            item["title"],
            item.get("body") or "",
            item.get("priority") or "SHOULD",
            item.get("location"),
            Jsonb(item) if origin == "EXTRACTED" else None,
            origin,
        ),
    )
    return str(row["id"])


def items(cur: Any, baseline_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select id, seq, code, title, body, priority, source_location, extracted_json, origin,
               requirement_id, match_result, spec_applied
          from requirement_baseline_item
         where baseline_id = %s
         order by seq
        """,
        (baseline_id,),
    )


def find_item(cur: Any, baseline_id: str, item_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        "select id from requirement_baseline_item where baseline_id = %s and id = %s",
        (baseline_id, item_id),
    )


def update_item(cur: Any, item_id: str, item: dict[str, Any]) -> None:
    cur.execute(
        """
        update requirement_baseline_item
           set code = %s, title = %s, body = %s, priority = %s, updated_at = now()
         where id = %s
        """,
        (item["code"], item["title"], item["body"], item["priority"], item_id),
    )


def delete_item(cur: Any, item_id: str) -> None:
    cur.execute("delete from requirement_baseline_item where id = %s", (item_id,))


def next_seq(cur: Any, baseline_id: str) -> int:
    row = fetch_one(
        cur,
        "select coalesce(max(seq), 0) + 1 as s from requirement_baseline_item "
        "where baseline_id = %s",
        (baseline_id,),
    )
    return int(row["s"])


def set_submitted(cur: Any, baseline_id: str, user_id: str) -> None:
    cur.execute(
        """
        update requirement_baseline
           set status = 'SUBMITTED', submitted_by_user_id = %s, submitted_at = now(),
               returned_reason = null, updated_at = now()
         where id = %s
        """,
        (user_id, baseline_id),
    )


def set_returned(cur: Any, baseline_id: str, reason: str) -> None:
    cur.execute(
        """
        update requirement_baseline
           set status = 'DRAFT', returned_reason = %s, updated_at = now()
         where id = %s
        """,
        (reason, baseline_id),
    )


def delete(cur: Any, baseline_id: str) -> None:
    cur.execute("delete from requirement_baseline where id = %s", (baseline_id,))


def set_confirmed(
    cur: Any, baseline_id: str, user_id: str, role: str, result: dict[str, Any]
) -> None:
    cur.execute(
        """
        update requirement_baseline
           set status = 'CONFIRMED', confirmed_by_user_id = %s, confirmed_by_role = %s,
               confirmed_at = now(), confirm_result = %s, updated_at = now()
         where id = %s
        """,
        (user_id, role, Jsonb(result), baseline_id),
    )


def existing_by_code(cur: Any, project_id: str, lock: bool = False) -> dict[str, dict[str, Any]]:
    """사업에 이미 있는 요구사항(코드 있는 것). 확정 때는 잠근다."""
    rows = fetch_all(
        cur,
        f"""
        select r.id, r.code, r.title, r.body, r.priority, r.baseline_id, r.source_kind,
               c.name as connection_name
          from requirement r
          left join tool_connection c on c.id = r.tool_connection_id
         where r.project_id = %s and r.code is not null
         order by r.code
         {"for update of r" if lock else ""}
        """,
        (project_id,),
    )
    return {r["code"]: r for r in rows}


def insert_requirement(
    cur: Any, project_id: str, item: dict[str, Any], document_id: str | None, baseline_id: str
) -> str:
    row = fetch_one(
        cur,
        """
        insert into requirement
          (project_id, code, title, body, priority, status, evidence_status,
           document_upload_id, source_kind, baseline_id, baseline_item_id)
        values (%s, %s, %s, %s, %s, 'DEFINED', 'DEFINED', %s, 'DOCUMENT', %s, %s)
        returning id
        """,
        (
            project_id,
            item["code"],
            item["title"],
            item["body"],
            item["priority"],
            document_id,
            baseline_id,
            item["id"],
        ),
    )
    return str(row["id"])


def attach_requirement(
    cur: Any, requirement_id: str, baseline_id: str, item: dict[str, Any], apply_spec: bool
) -> None:
    """기존 요구사항을 기준선에 붙인다. ID·원천·상태·링크는 그대로다. 명세서 내용 적용은
    발주기관이 고른 것만이다."""
    if apply_spec:
        cur.execute(
            """
            update requirement
               set baseline_id = %s, baseline_item_id = %s, title = %s, body = %s,
                   priority = %s, updated_at = now()
             where id = %s
            """,
            (
                baseline_id,
                item["id"],
                item["title"],
                item["body"],
                item["priority"],
                requirement_id,
            ),
        )
    else:
        cur.execute(
            """
            update requirement
               set baseline_id = %s, baseline_item_id = %s, updated_at = now()
             where id = %s
            """,
            (baseline_id, item["id"], requirement_id),
        )


def record_item_match(
    cur: Any, item_id: str, requirement_id: str, match: str, applied: bool
) -> None:
    cur.execute(
        """
        update requirement_baseline_item
           set requirement_id = %s, match_result = %s, spec_applied = %s, updated_at = now()
         where id = %s
        """,
        (requirement_id, match, applied, item_id),
    )


def requirement_counts(cur: Any, project_id: str) -> dict[str, int]:
    row = fetch_one(
        cur,
        """
        select count(*) as total,
               count(*) filter (where baseline_id is null) as outside
          from requirement where project_id = %s
        """,
        (project_id,),
    )
    return {"total": int(row["total"]), "outside": int(row["outside"])}


def unresolved_count(cur: Any, project_id: str, except_codes: set[str]) -> int:
    """없는 코드를 가리킨 근거의 코드 수. 기준선의 상위 요구사항 코드는 빼고 센다."""
    row = fetch_one(
        cur,
        """
        select count(distinct code) as n from requirement_unresolved_ref
         where project_id = %s and not (code = any(%s))
        """,
        (project_id, list(except_codes)),
    )
    return int(row["n"])
