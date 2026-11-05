"""공동 수급 참여 업체 (GH-138, ARC-029, SER.SEC.003).

권한은 셋으로 나뉜다.

- 사업 관리(참여 업체·사용자 할당·초대·연결 소유 업체 변경): 그 사업의 발주기관(CLIENT)과
  시스템 관리자(SUPER_ADMIN). 용역 업체는 대표사여도 하지 못한다.
- 업무 정보 조회: 사업에 접근할 수 있는 사람 모두(참여 업체 사용자·발주기관·관리자). 지금과 같다.
- 도구 연결의 설정 변경·삭제·연결 테스트: 그 연결의 소유 업체 사용자, 발주기관, 관리자.
  인증정보 힌트도 이 셋에게만 보인다.

대표사·참여사는 표시 구분이다. 권한을 바꾸지 않는다.
"""

from datetime import UTC, datetime
from typing import Any

from app.auth import repository as auth_repository
from app.auth.models import AuthPrincipal
from app.common import errors
from app.db import fetch_all, fetch_one

ROLES = ("REPRESENTATIVE", "PARTICIPANT")


# --- 조회 SQL ----------------------------------------------------------------


def find_project(cur: Any, project_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur, "select id, client_org_id, contractor_name from project where id = %s", (project_id,)
    )


def active_participant(cur: Any, project_id: str, org_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select pp.id, pp.role, pp.organization_id, o.name as organization_name, o.type
          from project_participant pp
          join organization o on o.id = pp.organization_id
         where pp.project_id = %s and pp.organization_id = %s and pp.status = 'ACTIVE'
        """,
        (project_id, org_id),
    )


def list_rows(cur: Any, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select pp.id, pp.organization_id, o.name as organization_name, pp.role, pp.work_note,
               pp.status, pp.created_at, pp.removed_at,
               (select count(*) from project_assignment a
                 where a.project_id = pp.project_id and a.contractor_org_id = pp.organization_id
                   and a.status = 'ACTIVE') as user_count,
               (select count(*) from tool_connection c
                 where c.project_id = pp.project_id and c.contractor_org_id = pp.organization_id)
                 as connection_count
          from project_participant pp
          join organization o on o.id = pp.organization_id
         where pp.project_id = %s
         order by pp.status, (pp.role = 'REPRESENTATIVE') desc, o.name
        """,
        (project_id,),
    )


def find_row(cur: Any, project_id: str, participant_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        "select * from project_participant where id = %s and project_id = %s",
        (participant_id, project_id),
    )


# --- 쓰기 SQL ----------------------------------------------------------------


def insert(
    cur: Any, project_id: str, org_id: str, role: str, note: str | None, user_id: str | None
) -> str:
    if role == "REPRESENTATIVE":
        _demote_representative(cur, project_id)
    row = fetch_one(
        cur,
        """
        insert into project_participant (project_id, organization_id, role, work_note,
                                         created_by_user_id)
        values (%s, %s, %s, %s, %s) returning id
        """,
        (project_id, org_id, role, note, user_id),
    )
    return str(row["id"])


def _demote_representative(cur: Any, project_id: str) -> None:
    cur.execute(
        """
        update project_participant set role = 'PARTICIPANT', updated_at = now()
         where project_id = %s and status = 'ACTIVE' and role = 'REPRESENTATIVE'
        """,
        (project_id,),
    )


def ensure(cur: Any, project_id: str, org_id: str, user_id: str | None) -> None:
    """할당·초대 수락으로 들어온 업체가 참여 업체가 아니면 참여사로 올린다. 이미 있으면 그대로다.

    사업 정보의 용역사 이름과 조직 이름이 같고 대표사가 아직 없으면 대표사로 둔다.
    """
    if active_participant(cur, project_id, org_id) is not None:
        return
    project = find_project(cur, project_id)
    org = fetch_one(cur, "select name from organization where id = %s", (org_id,))
    has_rep = fetch_one(
        cur,
        "select 1 as x from project_participant where project_id = %s and status = 'ACTIVE' "
        "and role = 'REPRESENTATIVE'",
        (project_id,),
    )
    role = (
        "REPRESENTATIVE"
        if has_rep is None and project and org and project["contractor_name"] == org["name"]
        else "PARTICIPANT"
    )
    insert(cur, project_id, org_id, role, None, user_id)


# --- 권한 -------------------------------------------------------------------


def require_access(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repository.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def is_manager(cur: Any, principal: AuthPrincipal, project_id: str) -> bool:
    """사업 관리 권한. 관리자, 또는 그 사업의 발주기관 사용자."""
    if principal.role == "SUPER_ADMIN":
        return True
    if principal.role != "CLIENT":
        return False
    project = find_project(cur, project_id)
    return project is not None and str(project["client_org_id"]) == principal.org_id


def require_manager(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    require_access(cur, principal, project_id)
    if not is_manager(cur, principal, project_id):
        raise errors.ApiError(
            403, "FORBIDDEN", "참여 업체·사용자·연결 소유는 발주기관이 관리합니다."
        )


def owner_state(cur: Any, conn: dict[str, Any]) -> tuple[str, str | None]:
    """연결 소유 업체의 상태와 이름. 참여 업체면 PARTICIPANT, 발주기관이 만들었으면 CLIENT,
    둘 다 아니면 UNCLEAR(관리자가 만들었거나 참여가 끝난 업체). 임의로 배정하지 않는다."""
    project_id, org_id = str(conn["project_id"]), str(conn["contractor_org_id"])
    org = fetch_one(cur, "select name from organization where id = %s", (org_id,))
    name = org["name"] if org else None
    if active_participant(cur, project_id, org_id) is not None:
        return "PARTICIPANT", name
    project = find_project(cur, project_id)
    if project is not None and str(project["client_org_id"]) == org_id:
        return "CLIENT", name
    return "UNCLEAR", name


def can_manage_connection(cur: Any, principal: AuthPrincipal, conn: dict[str, Any]) -> bool:
    project_id = str(conn["project_id"])
    if is_manager(cur, principal, project_id):
        return True
    if principal.role != "CONTRACTOR" or str(conn["contractor_org_id"]) != principal.org_id:
        return False
    # 참여가 끝난 업체는 예전에 만든 연결이라도 바꾸지 못한다
    return active_participant(cur, project_id, principal.org_id) is not None


def require_connection_manager(cur: Any, principal: AuthPrincipal, conn: dict[str, Any]) -> None:
    require_access(cur, principal, str(conn["project_id"]))
    if not can_manage_connection(cur, principal, conn):
        raise errors.ApiError(
            403,
            "CONNECTION_OWNER_ONLY",
            "이 연결은 소유 업체와 발주기관만 바꾸거나 지울 수 있습니다.",
        )


def history(
    cur: Any,
    project_id: str,
    participant_id: str,
    field: str,
    before: str | None,
    after: str | None,
    actor: str,
) -> None:
    cur.execute(
        """
        insert into entity_history (entity_type, entity_id, project_id, field, from_value,
                                    to_value, actor)
        values ('PROJECT_PARTICIPANT', %s, %s, %s, %s, %s, %s)
        """,
        (participant_id, project_id, field, before, after, actor[:120]),
    )


def now() -> datetime:
    return datetime.now(UTC)
