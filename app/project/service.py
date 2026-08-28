"""사업 목록 조립. 접근 범위를 먼저 좁히고 그 안에서만 조회한다."""

from typing import Any

from app.auth import repository as auth_repository
from app.auth.models import AuthPrincipal
from app.common.paging import PageQuery, PageResponse
from app.project import repository
from app.project.models import ProjectSummaryResponse


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
