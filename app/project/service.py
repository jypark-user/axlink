"""사업 목록 조립. 접근 범위를 먼저 좁히고 그 안에서만 조회한다.

등록·수정·삭제와 용역사 할당·초대는 발주기관(CLIENT) 몫이다(SER.SEC.003). 용역사는
초대 링크로 들어와 자기 사업만 본다.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import bcrypt

from app.auth import repository as auth_repository
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.hashes import random_token, sha256_hex
from app.common.paging import PageQuery, PageResponse
from app.project import participants, repository
from app.project.models import (
    AssignmentCreateRequest,
    AssignmentResponse,
    InviteCreateRequest,
    ParticipantCreateRequest,
    ParticipantResponse,
    ParticipantUpdateRequest,
    ProjectCreateRequest,
    ProjectDeleteRequest,
    ProjectDetailResponse,
    ProjectInviteResponse,
    ProjectMetrics,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
)
from app.review import repository as review_repository
from app.standard import repository as standard_repository

_SI_PHASES = ("SI_1", "SI_2", "SI_3", "SI_4", "SI_5", "SI_6")
_INVITE_TTL = timedelta(days=7)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _require_client(principal: AuthPrincipal) -> None:
    if principal.role not in ("CLIENT", "SUPER_ADMIN"):
        raise errors.ApiError(403, "FORBIDDEN", "발주기관 계정만 할 수 있습니다.")


def _require_allowed(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repository.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise errors.validation_failed(f"{field} 는 YYYY-MM-DD 형식이어야 합니다.") from exc


def create(
    cur: Any, principal: AuthPrincipal, req: ProjectCreateRequest
) -> ProjectDetailResponse:
    """사업 하나 = 기본 대시보드 하나 + 산출물 목록 22개 항목. 셋을 한 트랜잭션에 만든다."""
    _require_client(principal)
    start, end = _parse_date(req.startDate, "startDate"), _parse_date(req.endDate, "endDate")
    if end < start:
        raise errors.validation_failed("마감일은 착수일보다 빠를 수 없습니다.")
    if not req.description.strip():
        raise errors.validation_failed("설명을 입력하세요.")
    delete_hash = bcrypt.hashpw(req.deletePassword.encode("utf-8"), bcrypt.gensalt()).decode()
    project_id = repository.insert_project(
        cur, principal.org_id, req.name.strip(), start, end, req.description.strip(),
        req.contractorName.strip() or None, delete_hash,
    )
    repository.insert_default_dashboard(cur, project_id, principal.user_id)
    standard_repository.create_checklist(cur, project_id)
    return get_detail(cur, principal, project_id)


def update(
    cur: Any, principal: AuthPrincipal, project_id: str, req: ProjectUpdateRequest
) -> ProjectDetailResponse:
    _require_client(principal)
    _require_allowed(cur, principal, project_id)
    row = repository.find_by_id(cur, project_id)
    if row is None:
        raise errors.not_found("project", project_id)

    fields: dict[str, Any] = {}
    if req.name is not None:
        if not req.name.strip():
            raise errors.validation_failed("사업명은 비울 수 없습니다.")
        fields["name"] = req.name.strip()
    if req.description is not None:
        if not req.description.strip():
            raise errors.validation_failed("설명은 비울 수 없습니다.")
        fields["description"] = req.description.strip()
    if req.contractorName is not None:
        fields["contractor_name"] = req.contractorName.strip() or None
    if req.currentSiPhase is not None:
        if req.currentSiPhase not in _SI_PHASES:
            raise errors.validation_failed(f"허용되지 않는 단계입니다: {req.currentSiPhase}")
        fields["current_si_phase"] = req.currentSiPhase

    start = _parse_date(req.startDate, "startDate") if req.startDate else row["start_date"]
    end = _parse_date(req.endDate, "endDate") if req.endDate else row["end_date"]
    if end < start:
        raise errors.validation_failed("마감일은 착수일보다 빠를 수 없습니다.")
    if req.startDate:
        fields["start_date"] = start
    if req.endDate:
        fields["end_date"] = end

    if fields:
        repository.update_project(cur, project_id, fields)
    return get_detail(cur, principal, project_id)


def delete(
    cur: Any, principal: AuthPrincipal, project_id: str, req: ProjectDeleteRequest
) -> None:
    """지우면 수집분까지 전부 사라진다. 등록 때 정한 비밀번호를 맞춰야 한다."""
    _require_client(principal)
    _require_allowed(cur, principal, project_id)
    stored = repository.find_delete_hash(cur, project_id)
    if not stored:
        raise errors.validation_failed("삭제 비밀번호가 설정되지 않은 사업입니다.")
    if not bcrypt.checkpw(req.password.encode("utf-8"), stored.encode("utf-8")):
        raise errors.ApiError(403, "DELETE_PASSWORD_MISMATCH", "삭제 비밀번호가 맞지 않습니다.")
    repository.delete_project(cur, project_id)


# --- 용역사 할당 -------------------------------------------------------------

def _to_assignment(row: dict[str, Any]) -> AssignmentResponse:
    return AssignmentResponse(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        contractorOrgId=str(row["contractor_org_id"]),
        contractorOrgName=row["contractor_org_name"],
        userId=str(row["user_id"]),
        userName=row["user_name"],
        userEmail=row["username"],
        status=row["status"],
        assignedAt=row["created_at"].isoformat(),
    )


def list_assignments(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> list[AssignmentResponse]:
    _require_client(principal)
    _require_allowed(cur, principal, project_id)
    return [_to_assignment(r) for r in repository.list_assignments(cur, project_id)]


def add_assignments(
    cur: Any, principal: AuthPrincipal, project_id: str, req: AssignmentCreateRequest
) -> list[AssignmentResponse]:
    """같은 사람을 두 번 넣어도 한 줄이다. 해제됐던 사람은 되살린다."""
    _require_client(principal)
    _require_allowed(cur, principal, project_id)
    org = repository.find_organization(cur, req.contractorOrgId)
    if org is None or org["type"] != "CONTRACTOR":
        raise errors.validation_failed("용역사 조직이 아닙니다.")
    if not req.userIds:
        raise errors.validation_failed("할당할 계정을 고르세요.")

    participants.ensure(cur, project_id, str(org["id"]), principal.user_id)
    for user_id in req.userIds:
        user = repository.find_user_in_org(cur, user_id, str(org["id"]))
        if user is None or user["role"] != "CONTRACTOR":
            raise errors.validation_failed(f"용역사 소속 계정이 아닙니다: {user_id}")
        existing = repository.find_assignment(cur, project_id, user_id)
        if existing is None:
            repository.insert_assignment(
                cur, project_id, str(org["id"]), user_id, principal.user_id
            )
        elif existing["status"] != "ACTIVE":
            repository.reactivate_assignment(cur, str(existing["id"]))
    return list_assignments(cur, principal, project_id)


def remove_assignment(
    cur: Any, principal: AuthPrincipal, project_id: str, assignment_id: str
) -> None:
    """지우지 않고 해제로 남긴다. 누가 언제까지 붙어 있었는지가 감독 기록이다."""
    _require_client(principal)
    _require_allowed(cur, principal, project_id)
    row = repository.find_assignment_by_id(cur, assignment_id)
    if row is None or str(row["project_id"]) != project_id:
        raise errors.not_found("assignment", assignment_id)
    if row["status"] == "ACTIVE":
        repository.revoke_assignment(cur, assignment_id, datetime.now(UTC))


# --- 초대 링크 --------------------------------------------------------------

def create_invite(
    cur: Any, principal: AuthPrincipal, project_id: str, req: InviteCreateRequest | None = None
) -> ProjectInviteResponse:
    """링크 하나로 여러 명이 가입할 수 있다. 토큰 원문은 이 응답에만 담긴다.

    업체를 지정하면(GH-138) 가입자는 회사명을 무엇으로 적든 그 업체로만 들어간다. 지정할 수
    있는 업체는 이 사업의 참여 업체뿐이다.
    """
    _require_client(principal)
    _require_allowed(cur, principal, project_id)
    participants.require_manager(cur, principal, project_id)
    org_id = org_name = None
    if req is not None and req.organizationId:
        part = participants.active_participant(cur, project_id, req.organizationId)
        if part is None or part["type"] != "CONTRACTOR":
            raise errors.validation_failed("이 사업의 참여 업체만 지정할 수 있습니다.")
        org_id, org_name = str(part["organization_id"]), part["organization_name"]
    token = random_token()
    row = repository.insert_invite(
        cur, project_id, sha256_hex(token), datetime.now(UTC) + _INVITE_TTL, principal.user_id,
        org_id,
    )
    return ProjectInviteResponse(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        expiresAt=row["expires_at"].isoformat(),
        revokedAt=_iso(row["revoked_at"]),
        createdAt=row["created_at"].isoformat(),
        token=token,
        organizationId=org_id,
        organizationName=org_name,
    )


# --- 참여 업체 (GH-138) ------------------------------------------------------

def _to_participant(row: dict[str, Any]) -> ParticipantResponse:
    return ParticipantResponse(
        id=str(row["id"]),
        organizationId=str(row["organization_id"]),
        organizationName=row["organization_name"],
        role=row["role"],
        workNote=row["work_note"],
        status=row["status"],
        userCount=int(row["user_count"]),
        connectionCount=int(row["connection_count"]),
        createdAt=row["created_at"].isoformat(),
        removedAt=_iso(row["removed_at"]),
    )


def list_participants(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> list[ParticipantResponse]:
    """사업에 접근할 수 있으면 누구나 본다. 업무 정보 공유 조회 범위다."""
    participants.require_access(cur, principal, project_id)
    return [_to_participant(r) for r in participants.list_rows(cur, project_id)]


def _actor(cur: Any, principal: AuthPrincipal) -> str:
    row = auth_repository.find_user_by_id(cur, principal.user_id) or {}
    return row.get("name") or row.get("username") or "사용자"


def _check_role(role: str) -> None:
    if role not in participants.ROLES:
        raise errors.validation_failed(
            "구분은 REPRESENTATIVE(대표사)·PARTICIPANT(참여사) 중 하나입니다."
        )


def add_participant(
    cur: Any, principal: AuthPrincipal, project_id: str, req: ParticipantCreateRequest
) -> list[ParticipantResponse]:
    participants.require_manager(cur, principal, project_id)
    _check_role(req.role)
    if req.organizationId:
        org = repository.find_organization(cur, req.organizationId)
        if org is None:
            raise errors.not_found("organization", req.organizationId)
    else:
        name = (req.organizationName or "").strip()
        if not name:
            raise errors.validation_failed("업체를 고르거나 업체 이름을 적으세요.")
        org = repository.find_organization_by_name(cur, name)
        if org is None:
            org = repository.find_organization(
                cur, repository.insert_organization(cur, name, "CONTRACTOR")
            )
    if org["type"] != "CONTRACTOR":
        raise errors.validation_failed("용역 업체만 참여 업체로 둘 수 있습니다.")
    org_id = str(org["id"])
    if participants.active_participant(cur, project_id, org_id) is not None:
        raise errors.ApiError(409, "ALREADY_PARTICIPANT", "이미 참여 업체입니다.")
    note = (req.workNote or "").strip() or None
    pid = participants.insert(cur, project_id, org_id, req.role, note, principal.user_id)
    participants.history(cur, project_id, pid, "participant", None,
                         f"{org['name']} {req.role}", _actor(cur, principal))
    return list_participants(cur, principal, project_id)


def update_participant(
    cur: Any, principal: AuthPrincipal, project_id: str, participant_id: str,
    req: ParticipantUpdateRequest,
) -> list[ParticipantResponse]:
    participants.require_manager(cur, principal, project_id)
    row = participants.find_row(cur, project_id, participant_id)
    if row is None or row["status"] != "ACTIVE":
        raise errors.not_found("participant", participant_id)
    actor = _actor(cur, principal)
    if req.role is not None and req.role != row["role"]:
        _check_role(req.role)
        if req.role == "REPRESENTATIVE":
            participants._demote_representative(cur, project_id)
        cur.execute(
            "update project_participant set role = %s, updated_at = now() where id = %s",
            (req.role, participant_id),
        )
        participants.history(cur, project_id, participant_id, "role", row["role"], req.role, actor)
    if req.workNote is not None:
        note = req.workNote.strip() or None
        cur.execute(
            "update project_participant set work_note = %s, updated_at = now() where id = %s",
            (note, participant_id),
        )
    return list_participants(cur, principal, project_id)


def remove_participant(
    cur: Any, principal: AuthPrincipal, project_id: str, participant_id: str
) -> list[ParticipantResponse]:
    """참여를 끝낸다. 지우지 않는다. 그 업체 사용자의 할당도 해제하고, 그 업체가 만든 연결은
    소유 업체 불명확으로 남는다(발주기관이 다른 참여 업체로 넘기거나 정리한다)."""
    participants.require_manager(cur, principal, project_id)
    row = participants.find_row(cur, project_id, participant_id)
    if row is None or row["status"] != "ACTIVE":
        raise errors.not_found("participant", participant_id)
    now = participants.now()
    cur.execute(
        """
        update project_participant
           set status = 'REMOVED', removed_at = %s, updated_at = %s
         where id = %s
        """,
        (now, now, participant_id),
    )
    cur.execute(
        """
        update project_assignment set status = 'REVOKED', revoked_at = %s, updated_at = %s
         where project_id = %s and contractor_org_id = %s and status = 'ACTIVE'
        """,
        (now, now, project_id, row["organization_id"]),
    )
    participants.history(cur, project_id, participant_id, "status", "ACTIVE", "REMOVED",
                         _actor(cur, principal))
    return list_participants(cur, principal, project_id)


def get_detail(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> ProjectDetailResponse:
    allowed = auth_repository.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    row = repository.find_by_id(cur, project_id)
    if row is None:
        raise errors.not_found("project", project_id)

    m = repository.full_metrics(cur, project_id)
    return ProjectDetailResponse(
        id=str(row["id"]),
        name=row["name"],
        description=row["description"],
        contractorName=row["contractor_name"],
        status=row["status"],
        startDate=row["start_date"].isoformat(),
        endDate=row["end_date"].isoformat(),
        currentSiPhase=row["current_si_phase"],
        clientOrgId=str(row["client_org_id"]),
        clientOrgName=row["client_org_name"],
        assignmentCount=repository.assignment_count(cur, project_id),
        connectionCount=repository.connection_count(cur, project_id),
        defaultDashboardId=repository.default_dashboard_id(cur, project_id),
        openReviewRequestCount=review_repository.open_counts(cur, [project_id]).get(project_id, 0),
        metrics=ProjectMetrics(**{**m, "lastSyncedAt": _iso(m["lastSyncedAt"])}),
        createdAt=row["created_at"].isoformat(),
        updatedAt=row["updated_at"].isoformat(),
    )


def list_projects(
    cur: Any, principal: AuthPrincipal, status: str | None, q: str | None, page: PageQuery
) -> PageResponse[ProjectSummaryResponse]:
    allowed = auth_repository.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if not allowed:
        return PageResponse.of([], page, 0)

    total = repository.count_projects(cur, allowed, status, q)
    rows = repository.search_projects(cur, allowed, status, q, page)
    if not rows:
        return PageResponse.of([], page, total)

    ids = [str(r["id"]) for r in rows]
    approved = repository.approved_work_products(cur, ids)
    risks = repository.open_risks(cur, ids)
    corrections = repository.open_correction_actions(cur, ids)
    reviews = review_repository.open_counts(cur, ids)

    content = [
        ProjectSummaryResponse(
            id=str(r["id"]),
            name=r["name"],
            status=r["status"],
            startDate=r["start_date"].isoformat(),
            endDate=r["end_date"].isoformat(),
            currentSiPhase=r["current_si_phase"],
            clientOrgId=str(r["client_org_id"]),
            clientOrgName=r["client_org_name"],
            contractorName=r["contractor_name"],
            requiredWorkProductApproved=approved.get(str(r["id"]), 0),
            requiredWorkProductTotal=repository.REQUIRED_WORK_PRODUCT_TOTAL,
            openCorrectionActionCount=corrections.get(str(r["id"]), 0),
            openRiskCount=risks.get(str(r["id"]), 0),
            openReviewRequestCount=reviews.get(str(r["id"]), 0),
            updatedAt=r["updated_at"].isoformat(),
        )
        for r in rows
    ]
    return PageResponse.of(content, page, total)
