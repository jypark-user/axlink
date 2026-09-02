"""doc_chunk SQL. 색인은 소스 단위 전량 교체다 — 부분 갱신하지 않는다."""

from typing import Any

from psycopg.types.json import Jsonb

from app.db import fetch_all, fetch_one


def column_dimension(cur: Any) -> int:
    """embedding 컬럼의 실제 차원. pgvector 는 atttypmod 에 차원을 그대로 넣는다.

    information_schema 로는 vector 의 차원이 안 보여서 카탈로그를 직접 본다.
    """
    row = fetch_one(
        cur,
        """
        select atttypmod as dim
          from pg_attribute
         where attrelid = 'doc_chunk'::regclass and attname = 'embedding'
        """,
    )
    return int(row["dim"]) if row else 0


def delete_by_source(cur: Any, source_type: str, source_id: str) -> int:
    cur.execute(
        "delete from doc_chunk where source_type = %s and source_id = %s",
        (source_type, source_id),
    )
    return cur.rowcount


def insert_chunks(cur: Any, rows: list[dict[str, Any]]) -> int:
    """청크를 한 번에 넣는다. 호출 전에 같은 소스의 기존 청크가 지워져 있어야 한다."""
    if not rows:
        return 0
    cur.executemany(
        """
        insert into doc_chunk
          (project_id, source_type, source_id, chunk_index, content, embedding,
           embedding_model, token_count, source_title, source_uri, content_hash, meta_json)
        values (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                r["project_id"], r["source_type"], r["source_id"], r["chunk_index"],
                r["content"], r["embedding"], r["embedding_model"], r["token_count"],
                r["source_title"], r["source_uri"], r["content_hash"], Jsonb(r["meta"]),
            )
            for r in rows
        ],
    )
    return len(rows)


def count_by_project(cur: Any, project_id: str) -> int:
    row = fetch_one(
        cur, "select count(*) as n from doc_chunk where project_id = %s", (project_id,)
    )
    return int(row["n"]) if row else 0


def count_by_source_type(cur: Any, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select source_type, count(*) as chunks, count(distinct source_id) as sources
          from doc_chunk
         where project_id = %s
         group by source_type
         order by source_type
        """,
        (project_id,),
    )


def hashes_by_source(
    cur: Any, source_type: str, source_ids: list[str]
) -> dict[str, list[str]]:
    """소스별 청크 해시를 chunk_index 순으로 돌려준다. 재색인 생략 판단에 쓴다."""
    if not source_ids:
        return {}
    rows = fetch_all(
        cur,
        """
        select source_id::text as source_id, content_hash
          from doc_chunk
         where source_type = %s and source_id = any(%s::uuid[])
         order by source_id, chunk_index
        """,
        (source_type, source_ids),
    )
    found: dict[str, list[str]] = {}
    for row in rows:
        found.setdefault(row["source_id"], []).append(row["content_hash"])
    return found
