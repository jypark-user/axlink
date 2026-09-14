"""conversation · message · message_source SQL. 대화는 사용자의 것이라 user_id 로 잠근다."""

from typing import Any

from psycopg.types.json import Jsonb

from app.db import fetch_all, fetch_one

_CONVERSATION = """
select c.id::text as id, c.title, c.project_scope::text[] as project_scope, c.pinned,
       c.last_message_at, c.created_at,
       (select count(*) from message m where m.conversation_id = c.id) as message_count,
       coalesce((select array_agg(p.name order by p.name)
                   from project p where p.id = any(c.project_scope)), '{}') as project_names
  from conversation c
"""


def list_conversations(cur: Any, user_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        _CONVERSATION
        + """
 where c.user_id = %s and c.status = 'ACTIVE'
 order by c.pinned desc, coalesce(c.last_message_at, c.created_at) desc, c.id
 limit %s offset %s
""",
        (user_id, limit, offset),
    )


def count_conversations(cur: Any, user_id: str) -> int:
    row = fetch_one(
        cur,
        "select count(*) as n from conversation where user_id = %s and status = 'ACTIVE'",
        (user_id,),
    )
    return int(row["n"]) if row else 0


def get_conversation(cur: Any, conversation_id: str, user_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        _CONVERSATION + " where c.id = %s and c.user_id = %s and c.status = 'ACTIVE'",
        (conversation_id, user_id),
    )


def insert_conversation(
    cur: Any, user_id: str, title: str, project_scope: list[str]
) -> dict[str, Any]:
    row = fetch_one(
        cur,
        """
        insert into conversation (user_id, title, project_scope)
        values (%s, %s, %s::uuid[])
        returning id::text as id
        """,
        (user_id, title, project_scope),
    )
    assert row is not None
    found = get_conversation(cur, row["id"], user_id)
    assert found is not None
    return found


def update_conversation(
    cur: Any,
    conversation_id: str,
    title: str | None,
    pinned: bool | None,
    project_scope: list[str] | None,
) -> None:
    sets: list[str] = ["updated_at = now()"]
    params: list[Any] = []
    if title is not None:
        sets.append("title = %s")
        params.append(title)
    if pinned is not None:
        sets.append("pinned = %s")
        params.append(pinned)
    if project_scope is not None:
        sets.append("project_scope = %s::uuid[]")
        params.append(project_scope)
    params.append(conversation_id)
    cur.execute(f"update conversation set {', '.join(sets)} where id = %s", params)


def delete_conversation(cur: Any, conversation_id: str) -> None:
    """소프트 삭제. 메시지·출처는 남는다. 답변 이력이 곧 시연 데이터라 지우지 않는다."""
    cur.execute(
        "update conversation set status = 'DELETED', updated_at = now() where id = %s",
        (conversation_id,),
    )


def touch_conversation(cur: Any, conversation_id: str) -> None:
    cur.execute(
        "update conversation set last_message_at = now(), updated_at = now() where id = %s",
        (conversation_id,),
    )


# ---------------------------------------------------------------- message


def next_seq(cur: Any, conversation_id: str) -> int:
    row = fetch_one(
        cur,
        "select coalesce(max(seq), 0) + 1 as seq from message where conversation_id = %s",
        (conversation_id,),
    )
    return int(row["seq"]) if row else 1


def insert_message(
    cur: Any,
    conversation_id: str,
    seq: int,
    role: str,
    content: str,
    status: str = "COMPLETE",
    route_type: str | None = None,
    rewritten_query: str | None = None,
    measure_key: str | None = None,
    infographic: dict[str, Any] | None = None,
) -> str:
    row = fetch_one(
        cur,
        """
        insert into message
          (conversation_id, seq, role, content, status, route_type, rewritten_query,
           measure_key, infographic_json)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id::text as id
        """,
        (
            conversation_id, seq, role, content, status, route_type, rewritten_query,
            measure_key, Jsonb(infographic) if infographic is not None else None,
        ),
    )
    assert row is not None
    return row["id"]


def finish_message(
    cur: Any, message_id: str, content: str, status: str, latency_ms: int
) -> None:
    cur.execute(
        """
        update message
           set content = %s, status = %s, latency_ms = %s, updated_at = now()
         where id = %s
        """,
        (content, status, latency_ms, message_id),
    )


def list_messages(cur: Any, conversation_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select id::text as id, conversation_id::text as conversation_id, seq, role, content,
               status, route_type, rewritten_query, measure_key, feedback, infographic_json,
               created_at
          from message
         where conversation_id = %s
         order by seq
        """,
        (conversation_id,),
    )


def message_owner(cur: Any, message_id: str) -> dict[str, Any] | None:
    """피드백 권한 확인용. 메시지가 속한 대화의 주인을 돌려준다."""
    return fetch_one(
        cur,
        """
        select m.id::text as id, m.role, c.user_id::text as user_id
          from message m join conversation c on c.id = m.conversation_id
         where m.id = %s and c.status = 'ACTIVE'
        """,
        (message_id,),
    )


def set_feedback(cur: Any, message_id: str, feedback: str) -> None:
    cur.execute(
        "update message set feedback = %s, updated_at = now() where id = %s",
        (feedback, message_id),
    )


# ---------------------------------------------------------------- message_source


def insert_sources(cur: Any, message_id: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cur.executemany(
        """
        insert into message_source
          (message_id, footnote_no, doc_chunk_id, source_type, source_title, snippet,
           external_url, page_no)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                message_id, r["footnote_no"], r["doc_chunk_id"], r["source_type"],
                r["source_title"], r["snippet"], r["external_url"], r["page_no"],
            )
            for r in rows
        ],
    )


def sources_for_messages(cur: Any, message_ids: list[str]) -> list[dict[str, Any]]:
    """출처와 그 청크가 아직 가리키는 표준 객체·사업. 청크가 재색인으로 사라졌으면
    저장해 둔 제목·조각·링크만 남는다."""
    if not message_ids:
        return []
    return fetch_all(
        cur,
        """
        select s.message_id::text as message_id, s.footnote_no,
               s.doc_chunk_id::text as doc_chunk_id,
               s.source_type, s.source_title, s.snippet, s.external_url, s.page_no,
               c.source_id::text as source_id, c.project_id::text as project_id,
               p.name as project_name
          from message_source s
          left join doc_chunk c on c.id = s.doc_chunk_id
          left join project p on p.id = c.project_id
         where s.message_id = any(%s::uuid[])
         order by s.message_id, s.footnote_no
        """,
        (message_ids,),
    )
