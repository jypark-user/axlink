"""app_user · organization · refresh_token 조회. SQL 은 여기서만 쓴다."""

from datetime import datetime
from typing import Any

from app.db import fetch_all, fetch_one


def find_user_by_email(cur: Any, email: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select id, organization_id, email, name, password_hash, role, status
          from app_user
         where lower(email) = lower(%s)
        """,
        (email,),
    )


def find_user_by_id(cur: Any, user_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select id, organization_id, email, name, password_hash, role, status
          from app_user
         where id = %s
        """,
        (user_id,),
    )


def find_organization(cur: Any, org_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur, "select id, name, type from organization where id = %s", (org_id,)
    )


def touch_last_login(cur: Any, user_id: str, now: datetime) -> None:
    cur.execute(
        "update app_user set last_login_at = %s, updated_at = %s where id = %s",
        (now, now, user_id),
    )


def insert_refresh_token(
    cur: Any, user_id: str, token_hash: str, expires_at: datetime, user_agent: str | None
) -> None:
    cur.execute(
        """
        insert into refresh_token (app_user_id, token_hash, expires_at, user_agent)
        values (%s, %s, %s, %s)
        """,
        (user_id, token_hash, expires_at, (user_agent or None)),
    )


def find_refresh_token(cur: Any, token_hash: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select id, app_user_id, expires_at, revoked_at
          from refresh_token
         where token_hash = %s
        """,
        (token_hash,),
    )


def revoke_refresh_token(cur: Any, token_id: str, now: datetime) -> None:
    cur.execute(
        "update refresh_token set revoked_at = %s where id = %s and revoked_at is null",
        (now, token_id),
    )


def revoke_all_for_user(cur: Any, user_id: str, now: datetime) -> None:
    cur.execute(
        "update refresh_token set revoked_at = %s where app_user_id = %s and revoked_at is null",
        (now, user_id),
    )


def allowed_project_ids(cur: Any, role: str, org_id: str, user_id: str) -> list[str]:
    """접근 가능한 사업. 파일럿 ProjectAccessResolver 와 같은 규칙이다."""
    if role == "SUPER_ADMIN":
        rows = fetch_all(cur, "select id from project")
    elif role == "CLIENT":
        rows = fetch_all(cur, "select id from project where client_org_id = %s", (org_id,))
    else:
        rows = fetch_all(
            cur,
            "select project_id as id from project_assignment "
            "where user_id = %s and status = 'ACTIVE'",
            (user_id,),
        )
    return sorted(str(r["id"]) for r in rows)
