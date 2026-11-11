"""tool_connection CRUD. SQL 은 여기서만 쓴다."""

import hashlib
import json
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from app.db import fetch_all, fetch_one

_COLUMNS = """
    id, project_id, contractor_org_id, tool, name, base_url, target_resource,
    auth_encrypted, auth_hint, mapping_rules_json, status,
    last_verified_at, last_synced_at, last_error, created_at
"""


def insert(
    cur: Any,
    project_id: str,
    contractor_org_id: str,
    tool: str,
    name: str,
    base_url: str,
    target_resource: str,
    auth_encrypted: str,
    auth_hint: str,
    mapping_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = fetch_one(
        cur,
        """
        insert into tool_connection
          (project_id, contractor_org_id, tool, name, base_url, target_resource,
           auth_encrypted, auth_hint, mapping_rules_json, status)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'DRAFT')
        returning id
        """,
        (
            project_id, contractor_org_id, tool, name, base_url, target_resource,
            auth_encrypted, auth_hint, Jsonb(mapping_rules or {}),
        ),
    )
    return find_by_id(cur, str(row["id"]))


def find_by_id(cur: Any, connection_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur, f"select {_COLUMNS} from tool_connection where id = %s", (connection_id,)
    )


def find_by_project(cur: Any, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        f"select {_COLUMNS} from tool_connection where project_id = %s order by created_at",
        (project_id,),
    )


def update_mapping_rules(
    cur: Any, connection_id: str, mapping_rules: dict[str, Any], now: datetime
) -> None:
    cur.execute(
        "update tool_connection set mapping_rules_json = %s, updated_at = %s where id = %s",
        (Jsonb(mapping_rules), now, connection_id),
    )


def update_status(cur: Any, connection_id: str, status: str, now: datetime) -> None:
    cur.execute(
        "update tool_connection set status = %s, updated_at = %s where id = %s",
        (status, now, connection_id),
    )


def update_connection(
    cur: Any,
    connection_id: str,
    now: datetime,
    *,
    name: str | None = None,
    base_url: str | None = None,
    target_resource: str | None = None,
    auth_encrypted: str | None = None,
    auth_hint: str | None = None,
    reset_status: bool = False,
) -> None:
    """준 값만 바꾼다. reset_status 면 검증이 무효가 됐다는 뜻이라 DRAFT 로 되돌린다."""
    sets = ["updated_at = %s"]
    params: list[Any] = [now]
    for column, value in (
        ("name", name),
        ("base_url", base_url),
        ("target_resource", target_resource),
        ("auth_encrypted", auth_encrypted),
        ("auth_hint", auth_hint),
    ):
        if value is not None:
            sets.append(f"{column} = %s")
            params.append(value)
    if reset_status:
        sets.append("status = 'DRAFT'")
        sets.append("last_error = null")
    cur.execute(
        f"update tool_connection set {', '.join(sets)} where id = %s",
        (*params, connection_id),
    )


def mark_verified(cur: Any, connection_id: str, now: datetime) -> None:
    cur.execute(
        """
        update tool_connection
           set status = 'VERIFIED', last_verified_at = %s, last_error = null, updated_at = %s
         where id = %s
        """,
        (now, now, connection_id),
    )


def delete(cur: Any, connection_id: str) -> None:
    cur.execute("delete from tool_connection where id = %s", (connection_id,))


def ingested_count(cur: Any, connection_id: str) -> int:
    row = fetch_one(
        cur,
        "select count(*) as cnt from raw_artifact where tool_connection_id = %s",
        (connection_id,),
    )
    return int(row["cnt"]) if row else 0


def last_sync_status(cur: Any, connection_id: str) -> str | None:
    row = fetch_one(
        cur,
        """
        select status from sync_job where tool_connection_id = %s
         order by started_at desc nulls last limit 1
        """,
        (connection_id,),
    )
    return row["status"] if row else None


# --- 수집(BACKFILL) ---------------------------------------------------------

def try_lock_sync(cur: Any, connection_id: str) -> bool:
    """이 연결의 수집 잠금을 잡는다. 다른 회차가 잡고 있으면 False (AC-011-8).

    회차는 트랜잭션 하나 안에서 돌아 진행 중인 잡 행이 다른 요청에 보이지 않는다. 그래서 행이
    아니라 트랜잭션 잠금으로 막는다. 회차가 끝나거나(커밋·롤백) 프로세스가 죽으면 풀린다."""
    row = fetch_one(
        cur,
        "select pg_try_advisory_xact_lock(hashtextextended('sync:' || %s, 0)) as ok",
        (connection_id,),
    )
    return bool(row and row["ok"])


def insert_sync_job(
    cur: Any,
    connection_id: str,
    kind: str,
    cursor_from: Any,
    now: datetime,
    retry_of: str | None = None,
) -> str:
    row = fetch_one(
        cur,
        """
        insert into sync_job
          (tool_connection_id, kind, status, cursor_from, started_at, retry_of_job_id)
        values (%s, %s, 'RUNNING', %s, %s, %s)
        returning id
        """,
        (connection_id, kind, cursor_from, now, retry_of),
    )
    return str(row["id"])


def finish_sync_job(
    cur: Any,
    job_id: str,
    status: str,
    stats: dict[str, int],
    cursor_to: datetime,
    now: datetime,
    error: str | None = None,
    error_code: str | None = None,
) -> None:
    cur.execute(
        """
        update sync_job
           set status = %s, stats_json = %s, cursor_to = %s, finished_at = %s,
               error = %s, error_code = %s, updated_at = %s
         where id = %s
        """,
        (status, Jsonb(stats), cursor_to, now, error, error_code, now, job_id),
    )


def find_sync_job(cur: Any, job_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select j.id, j.tool_connection_id, j.kind, j.status, j.started_at, j.finished_at,
               j.stats_json, j.error, j.error_code, j.retry_of_job_id,
               c.name as connection_name, c.tool, c.project_id
          from sync_job j
          join tool_connection c on c.id = j.tool_connection_id
         where j.id = %s
        """,
        (job_id,),
    )


def list_sync_jobs(cur: Any, project_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select j.id, j.tool_connection_id, j.kind, j.status, j.started_at, j.finished_at,
               j.stats_json, j.error, j.error_code, c.name as connection_name,
               c.tool, c.project_id
          from sync_job j
          join tool_connection c on c.id = j.tool_connection_id
         where c.project_id = %s
         order by j.started_at desc nulls last, j.created_at desc
         limit %s offset %s
        """,
        (project_id, limit, offset),
    )


def count_sync_jobs(cur: Any, project_id: str) -> int:
    row = fetch_one(
        cur,
        """
        select count(*) as cnt from sync_job j
          join tool_connection c on c.id = j.tool_connection_id
         where c.project_id = %s
        """,
        (project_id,),
    )
    return int(row["cnt"]) if row else 0


def last_success_cursor(cur: Any, connection_id: str):
    """마지막 성공 수집의 커서. 없으면 None — 그때는 전체수집이다."""
    row = fetch_one(
        cur,
        """
        select max(cursor_to) as cursor_to
          from sync_job
         where tool_connection_id = %s and status = 'SUCCEEDED'
        """,
        (connection_id,),
    )
    return row["cursor_to"] if row else None


def last_success_resume(cur: Any, connection_id: str) -> dict[str, Any]:
    """마지막 성공 수집이 남긴 이어 읽을 자리(stats_json.resume). 없으면 빈 dict.

    항목종류 → {"since": ISO} 또는 {"since": ISO, "until": ISO}. 상한에 걸린 종류만 있다.
    """
    row = fetch_one(
        cur,
        """
        select stats_json -> 'resume' as resume
          from sync_job
         where tool_connection_id = %s and status = 'SUCCEEDED'
         order by cursor_to desc nulls last, finished_at desc nulls last
         limit 1
        """,
        (connection_id,),
    )
    return (row or {}).get("resume") or {}


def upsert_raw_artifact(
    cur: Any, connection_id: str, external_id: str, object_kind: str, payload: dict, job_id: str
) -> bool:
    """원본을 적재한다. 내용이 바뀌었으면 True(적재/갱신), 같으면 False(건너뜀).

    출처 보존이 원칙이라 원본 payload 를 그대로 둔다(SWFR.PIP.002).
    """
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    existing = fetch_one(
        cur,
        "select content_hash from raw_artifact "
        "where tool_connection_id = %s and external_id = %s",
        (connection_id, external_id),
    )
    if existing is None:
        cur.execute(
            """
            insert into raw_artifact
              (tool_connection_id, external_id, object_kind, payload_jsonb,
               content_hash, sync_job_id)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (connection_id, external_id, object_kind, Jsonb(payload), content_hash, job_id),
        )
        return True
    if existing["content_hash"] != content_hash:
        cur.execute(
            """
            update raw_artifact
               set object_kind = %s, payload_jsonb = %s, content_hash = %s,
                   fetched_at = now(), sync_job_id = %s
             where tool_connection_id = %s and external_id = %s
            """,
            (object_kind, Jsonb(payload), content_hash, job_id, connection_id, external_id),
        )
        return True
    return False


def mark_synced(cur: Any, connection_id: str, now: datetime, error: str | None) -> None:
    cur.execute(
        "update tool_connection set last_synced_at = %s, last_error = %s, updated_at = %s "
        "where id = %s",
        (now, error, now, connection_id),
    )


def mapping_rule_count(mapping_rules_json: Any) -> int:
    if not mapping_rules_json:
        return 0
    data = (
        mapping_rules_json
        if isinstance(mapping_rules_json, dict)
        else json.loads(mapping_rules_json)
    )
    # 파일럿 형식({"rules": [...]})과 현행 평면 dict(SWFR.CON.002) 둘 다 센다.
    return len(data.get("rules", data))


def github_repo_tree(cur: Any, project_id: str) -> dict[str, Any] | None:
    """사업에 연결된 GitHub 저장소의 파일 목록(가장 최근 수집분). 산출물 판정의 재료다."""
    row = fetch_one(
        cur,
        """
        select ra.payload_jsonb as payload
          from raw_artifact ra
          join tool_connection tc on tc.id = ra.tool_connection_id
         where tc.project_id = %s and tc.tool = 'GITHUB' and ra.object_kind = 'tree'
         order by ra.fetched_at desc
         limit 1
        """,
        (project_id,),
    )
    return None if row is None else (row["payload"] or None)


def redmine_issue_payloads(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """사업에 연결된 Redmine 의 이슈 원시본. 일정 화면이 WBS 파일 없을 때 대체 원천으로 쓴다.
    표준 모델의 issue 에는 시작일·종료일이 없고 원시본에는 그대로 있다."""
    rows = fetch_all(
        cur,
        """
        select ra.payload_jsonb as payload, tc.base_url
          from raw_artifact ra
          join tool_connection tc on tc.id = ra.tool_connection_id
         where tc.project_id = %s and tc.tool = 'REDMINE' and ra.object_kind = 'issue'
         order by ra.external_id
        """,
        (project_id,),
    )
    return [{**(r["payload"] or {}), "_base_url": r["base_url"]} for r in rows]


def raw_payload(cur: Any, connection_id: str, external_id: str) -> dict[str, Any] | None:
    row = fetch_one(
        cur,
        "select payload_jsonb from raw_artifact where tool_connection_id = %s and external_id = %s",
        (connection_id, external_id),
    )
    return None if row is None else row["payload_jsonb"]


def raw_payloads_by_kind(cur: Any, connection_id: str, kind: str) -> dict[str, dict[str, Any]]:
    rows = fetch_all(
        cur,
        "select external_id, payload_jsonb from raw_artifact "
        "where tool_connection_id = %s and object_kind = %s",
        (connection_id, kind),
    )
    return {r["external_id"]: r["payload_jsonb"] for r in rows}


def raw_changes_without_files(cur: Any, connection_id: str) -> list[dict[str, Any]]:
    """변경 파일을 아직 받지 않은 커밋·PR. 최근 것부터(새 분류가 먼저 쓰인다)."""
    return fetch_all(
        cur,
        """
        select external_id, object_kind, payload_jsonb from raw_artifact
         where tool_connection_id = %s and object_kind in ('commit', 'pull_request')
           and not (payload_jsonb ? 'files')
         order by fetched_at desc, external_id
        """,
        (connection_id,),
    )


def count_changes_with_files(cur: Any, connection_id: str) -> int:
    row = fetch_one(
        cur,
        "select count(*) as n from raw_artifact where tool_connection_id = %s "
        "and object_kind in ('commit', 'pull_request') and payload_jsonb ? 'files'",
        (connection_id,),
    )
    return int(row["n"]) if row else 0
