"""확인 요청 → 조치 보고 → 확인완료 (SWFR.WEB.004~006).

발주기관이 요청하고 확인한다. 용역사가 보고한다. 역할이 다르면 거절한다.
요청 시점과 보고 시점의 대상 상태를 시스템이 떠 두고, 확인하는 쪽에 두 상태의 차이를
나란히 보여 준다. 원천 도구에는 아무것도 쓰지 않는다(QUR.WEB.003). 여기 기록이 전부다.
"""

from datetime import UTC, datetime
from typing import Any

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.review import repository, snapshot
from app.review.models import (
    TARGET_TYPES,
    ReviewBodyRequest,
    ReviewRequestCreateRequest,
    ReviewRequestDetailResponse,
    ReviewRequestEventResponse,
    ReviewRequestResponse,
    ReviewTargetOption,
)


def _require_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def _require_client(principal: AuthPrincipal) -> None:
    if principal.role not in ("CLIENT", "SUPER_ADMIN"):
        raise errors.ApiError(403, "FORBIDDEN", "발주기관만 요청하고 확인할 수 있습니다.")


def _require_contractor(principal: AuthPrincipal) -> None:
    if principal.role != "CONTRACTOR":
        raise errors.ApiError(403, "FORBIDDEN", "조치 보고는 용역사가 합니다.")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _to_response(row: dict[str, Any]) -> ReviewRequestResponse:
    return ReviewRequestResponse(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        targetType=row["target_type"],
        targetKey=row["target_key"],
        targetLabel=row["target_label"],
        title=row["title"],
        body=row["body"],
        status=row["status"],
        requestedByName=row["requested_by_name"],
        requestedAt=row["requested_at"].isoformat(),
        reportBody=row["report_body"],
        reportedByName=row["reported_by_name"],
        reportedAt=_iso(row["reported_at"]),
        confirmedByName=row["confirmed_by_name"],
        confirmedAt=_iso(row["confirmed_at"]),
        rerequestCount=row["rerequest_count"],
        updatedAt=row["updated_at"].isoformat(),
    )


def _load(cur: Any, principal: AuthPrincipal, request_id: str) -> dict[str, Any]:
    row = repository.find_by_id(cur, request_id)
    if row is None:
        raise errors.not_found("review request", request_id)
    _require_project(cur, principal, str(row["project_id"]))
    return row


def _capture(
    cur: Any, principal: AuthPrincipal, project_id: str, target_type: str, target_key: str
) -> tuple[str, dict[str, Any]]:
    try:
        return snapshot.capture(cur, principal, project_id, target_type, target_key)
    except ValueError as exc:
        raise errors.validation_failed(str(exc)) from exc


def list_targets(
    cur: Any, principal: AuthPrincipal, project_id: str, target_type: str
) -> list[ReviewTargetOption]:
    _require_project(cur, principal, project_id)
    if target_type not in TARGET_TYPES:
        raise errors.validation_failed(f"지원하지 않는 대상 종류입니다: {target_type}")
    return snapshot.targets(cur, project_id, target_type)


def list_requests(
    cur: Any, principal: AuthPrincipal, project_id: str, status: str | None, page: PageQuery
) -> PageResponse[ReviewRequestResponse]:
    _require_project(cur, principal, project_id)
    total = repository.count(cur, project_id, status)
    rows = repository.search(cur, project_id, status, page)
    return PageResponse.of([_to_response(r) for r in rows], page, total)


def create(
    cur: Any, principal: AuthPrincipal, project_id: str, req: ReviewRequestCreateRequest
) -> ReviewRequestResponse:
    _require_client(principal)
    _require_project(cur, principal, project_id)
    if req.targetType not in TARGET_TYPES:
        raise errors.validation_failed(f"지원하지 않는 대상 종류입니다: {req.targetType}")
    label, state = _capture(cur, principal, project_id, req.targetType, req.targetKey)
    now = datetime.now(UTC)
    request_id = repository.insert(
        cur, project_id, req.targetType, req.targetKey, label, req.title.strip(),
        req.body.strip(), principal.user_id, state, now,
    )
    repository.insert_event(
        cur, request_id, "REQUESTED", req.body.strip() or None, principal.user_id, state, now
    )
    return _to_response(repository.find_by_id(cur, request_id))


def get_detail(
    cur: Any, principal: AuthPrincipal, request_id: str
) -> ReviewRequestDetailResponse:
    row = _load(cur, principal, request_id)
    before = row["snapshot_json"] or {}
    # 대상이 그 사이 사라졌을 수도 있다(이슈 삭제 등). 그러면 지금 상태는 비운다.
    try:
        _, current = snapshot.capture(
            cur, principal, str(row["project_id"]), row["target_type"], row["target_key"]
        )
    except (ValueError, errors.ApiError):
        current = {}
    events = [
        ReviewRequestEventResponse(
            id=str(e["id"]),
            kind=e["kind"],
            body=e["body"],
            actorName=e["actor_name"],
            snapshot=e["snapshot_json"] or {},
            createdAt=e["created_at"].isoformat(),
        )
        for e in repository.list_events(cur, request_id)
    ]
    base = _to_response(row)
    return ReviewRequestDetailResponse(
        **base.model_dump(),
        snapshot=before,
        currentState=current,
        changes=snapshot.diff(before, current),
        events=events,
    )


def report(
    cur: Any, principal: AuthPrincipal, request_id: str, req: ReviewBodyRequest
) -> ReviewRequestDetailResponse:
    """용역사의 조치 보고. 보고 시점 상태를 같이 떠 둔다."""
    _require_contractor(principal)
    row = _load(cur, principal, request_id)
    if row["status"] != "REQUESTED":
        raise errors.validation_failed("요청 상태에서만 보고할 수 있습니다.")
    _, state = _capture(
        cur, principal, str(row["project_id"]), row["target_type"], row["target_key"]
    )
    now = datetime.now(UTC)
    repository.mark_reported(cur, request_id, req.body.strip(), principal.user_id, state, now)
    repository.insert_event(
        cur, request_id, "REPORTED", req.body.strip(), principal.user_id, state, now
    )
    return get_detail(cur, principal, request_id)


def confirm(cur: Any, principal: AuthPrincipal, request_id: str) -> ReviewRequestDetailResponse:
    _require_client(principal)
    row = _load(cur, principal, request_id)
    if row["status"] != "REPORTED":
        raise errors.validation_failed("보고된 요청만 확인완료할 수 있습니다.")
    _, state = _capture(
        cur, principal, str(row["project_id"]), row["target_type"], row["target_key"]
    )
    now = datetime.now(UTC)
    repository.mark_confirmed(cur, request_id, principal.user_id, now)
    repository.insert_event(cur, request_id, "CONFIRMED", None, principal.user_id, state, now)
    return get_detail(cur, principal, request_id)


def rerequest(
    cur: Any, principal: AuthPrincipal, request_id: str, req: ReviewBodyRequest
) -> ReviewRequestDetailResponse:
    """보고가 미흡하면 같은 요청을 다시 연다. 지난 보고는 이력에 남는다."""
    _require_client(principal)
    row = _load(cur, principal, request_id)
    if row["status"] != "REPORTED":
        raise errors.validation_failed("보고된 요청만 다시 요청할 수 있습니다.")
    _, state = _capture(
        cur, principal, str(row["project_id"]), row["target_type"], row["target_key"]
    )
    now = datetime.now(UTC)
    repository.mark_rerequested(cur, request_id, req.body.strip(), state, now)
    repository.insert_event(
        cur, request_id, "REREQUESTED", req.body.strip(), principal.user_id, state, now
    )
    return get_detail(cur, principal, request_id)
