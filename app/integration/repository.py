"""tool_connection CRUD. SQL 은 여기서만 쓴다."""

import json
from datetime import datetime
from typing import Any

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
) -> dict[str, Any]:
    row = fetch_one(
        cur,
        """
        insert into tool_connection
          (project_id, contractor_org_id, tool, name, base_url, target_resource,
           auth_encrypted, auth_hint, status)
        values (%s, %s, %s, %s, %s, %s, %s, %s, 'DRAFT')
        returning id
        """,
        (
            project_id, contractor_org_id, tool, name, base_url, target_resource,
            auth_encrypted, auth_hint,
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


def update_status(cur: Any, connection_id: str, status: str, now: datetime) -> None:
    cur.execute(
        "update tool_connection set status = %s, updated_at = %s where id = %s",
        (status, now, connection_id),
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


def mapping_rule_count(mapping_rules_json: Any) -> int:
    if not mapping_rules_json:
        return 0
    data = (
        mapping_rules_json
        if isinstance(mapping_rules_json, dict)
        else json.loads(mapping_rules_json)
    )
    return len(data.get("rules", []))
