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
from app.project import repository
from app.project.models import (
    AssignmentCreateRequest,
    AssignmentResponse,
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
    cur: Any, principal: AuthPrincipal, project_id: str
) -> ProjectInviteResponse:
    """링크 하나로 여러 명이 가입할 수 있다. 토큰 원문은 이 응답에만 담긴다."""
    _require_client(principal)
    _require_allowed(cur, principal, project_id)
    token = random_token()
    row = repository.insert_invite(
        cur, project_id, sha256_hex(token), datetime.now(UTC) + _INVITE_TTL, principal.user_id
    )
    return ProjectInviteResponse(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        expiresAt=row["expires_at"].isoformat(),
        revokedAt=_iso(row["revoked_at"]),
        createdAt=row["created_at"].isoformat(),
        token=token,
    )


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
