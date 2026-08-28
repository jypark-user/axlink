"""사업 목록 조립. 접근 범위를 먼저 좁히고 그 안에서만 조회한다."""

from typing import Any

from app.auth import repository as auth_repository
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.project import repository
from app.project.models import (
    ProjectDetailResponse,
    ProjectMetrics,
    ProjectSummaryResponse,
)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


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
            updatedAt=r["updated_at"].isoformat(),
        )
        for r in rows
    ]
    return PageResponse.of(content, page, total)
