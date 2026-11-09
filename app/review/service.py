"""확인 요청 → 조치 보고 → 확인완료 (SWFR.WEB.004~006).

발주기관이 요청하고 확인한다. 용역사가 보고한다. 역할이 다르면 거절한다.
요청 시점과 보고 시점의 대상 상태를 시스템이 떠 두고, 확인하는 쪽에 두 상태의 차이를
나란히 보여 준다. 원천 도구에는 아무것도 쓰지 않는다(QUR.WEB.003). 여기 기록이 전부다.
"""

from datetime import UTC, datetime
from typing import Any

from app.activity import service as activity
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.dashboard import completion
from app.review import repository, snapshot
from app.review.models import (
    EVIDENCE_KINDS,
    PURPOSES,
    TARGET_TYPES,
    CompletionRecordResponse,
    CompletionWithdrawRequest,
    ReviewBodyRequest,
    ReviewConfirmRequest,
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


def _require_requester(principal: AuthPrincipal) -> None:
    """요청을 여는 쪽. 운영 지원을 위해 최고관리자도 일반 확인 요청은 열 수 있다."""
    if principal.role not in ("CLIENT", "SUPER_ADMIN"):
        raise errors.ApiError(403, "FORBIDDEN", "발주기관만 확인을 요청할 수 있습니다.")


def _require_client(principal: AuthPrincipal) -> None:
    """확인완료·다시 요청은 발주기관만 한다 (SWFR.WEB.006). 최고관리자도 대신하지 않는다.

    요청을 닫는 것은 조치가 충분하다고 발주기관이 판단하는 행위다. 운영자가 닫으면
    "발주기관이 확인했다"는 기록이 거짓이 된다.
    """
    if principal.role != "CLIENT":
        raise errors.ApiError(
            403, "FORBIDDEN", "확인완료와 다시 요청은 그 사업의 발주기관만 할 수 있습니다."
        )


def _require_completion_client(principal: AuthPrincipal) -> None:
    """작업 완료 확인·철회는 그 사업 발주기관만 한다. 최고관리자도 하지 않는다.

    일반 확인 요청은 운영 지원을 위해 최고관리자도 열 수 있다(_require_requester).
    닫는 것은 둘 다 발주기관만이다(_require_client).
    완료 확인은 계약 당사자인 발주기관이 작업 완료를 인정하는 행위라 대신할 수 없다.
    사업 접근은 _load·_require_project 가 따로 본다.
    """
    if principal.role != "CLIENT":
        raise errors.ApiError(
            403, "FORBIDDEN", "작업 완료 확인은 그 사업의 발주기관만 할 수 있습니다."
        )


def _conflict(code: str, message: str) -> errors.ApiError:
    return errors.ApiError(409, code, message)


# 완료 확인 기록에 고정하는 근거 사실. 스냅샷(review/snapshot.py WBS_ITEM)의 키와 같다
_FACT_KEYS = (
    "file_check", "file_rule", "file_ref", "repo_revision",
    "submission", "approval", "product_version",
)


def _evidence_item(cur: Any, project_id: str, e: Any) -> dict[str, Any]:
    """근거 한 줄. 산출물 버전이면 이 사업의 것인지 보고, 보고 시점의 버전·상태를 같이 남긴다."""
    if e.kind != "WORK_PRODUCT":
        ref = e.ref.strip()
        if not ref:
            raise errors.validation_failed("근거 위치(파일 경로·링크·기록 이름)를 적어 주세요.")
        return {"kind": e.kind, "ref": ref, "note": e.note.strip()}
    product = repository.work_product_in_project(cur, project_id, e.workProductId or "")
    if product is None:
        raise errors.validation_failed("이 사업에 등록된 산출물 버전을 골라 주세요.")
    return {
        "kind": "WORK_PRODUCT",
        "ref": f"{product['title'] or product['type']} {product['version'] or ''}".strip(),
        "note": e.note.strip(),
        "workProductId": str(product["id"]),
        "version": product["version"],
        "statusAtReport": product["status"],
    }


def _products_now(cur: Any, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [e["workProductId"] for e in evidence if e.get("workProductId")]
    return [
        {"workProductId": str(p["id"]), "version": p["version"], "status": p["status"],
         "approvedAt": p["approved_at"].isoformat() if p["approved_at"] else None}
        for p in repository.work_products_by_id(cur, ids)
    ]


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
        purpose=row["purpose"],
        completionScope=row["completion_scope"],
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
    if req.purpose not in PURPOSES:
        raise errors.validation_failed(f"지원하지 않는 요청 목적입니다: {req.purpose}")
    completion_mode = req.purpose == "WBS_COMPLETION"
    if completion_mode:
        _require_completion_client(principal)
    else:
        _require_requester(principal)
    _require_project(cur, principal, project_id)
    if req.targetType not in TARGET_TYPES:
        raise errors.validation_failed(f"지원하지 않는 대상 종류입니다: {req.targetType}")
    task_key = scope = None
    if completion_mode:
        task_key, scope = _check_completion_request(cur, project_id, req)
    label, state = _capture(cur, principal, project_id, req.targetType, req.targetKey)
    now = datetime.now(UTC)
    request_id = repository.insert(
        cur, project_id, req.targetType, req.targetKey, label, req.title.strip(),
        req.body.strip(), principal.user_id, state, now,
        purpose=req.purpose, completion_scope=scope, task_key=task_key,
    )
    repository.insert_event(
        cur, request_id, "REQUESTED", req.body.strip() or None, principal.user_id, state, now
    )
    activity.record(
        cur, project_id=project_id, kind=activity.REVIEW_REQUESTED, audience=activity.CONTRACTOR,
        summary=f"확인 요청: {req.title.strip()} ({label})", actor=principal,
        target_type="REVIEW_REQUEST", target_key=request_id, occurred_at=now,
    )
    return _to_response(repository.find_by_id(cur, request_id))


def _check_completion_request(
    cur: Any, project_id: str, req: ReviewRequestCreateRequest
) -> tuple[str, str]:
    """작업 완료 확인 요청의 조건. (작업 식별자, 확인할 완료 내용) 을 돌려준다."""
    if req.targetType != "WBS_ITEM":
        raise errors.validation_failed("작업 완료 확인은 WBS 작업에만 요청할 수 있습니다.")
    scope = (req.completionScope or "").strip()
    if not scope:
        raise errors.validation_failed("확인할 완료 내용을 적어 주세요.")
    item = completion.current_item(cur, project_id, wbs_id=req.targetKey)
    if item is None:
        raise errors.validation_failed("지금 WBS 의 말단 작업이 아닙니다.")
    task_key = str(item["task_key"])
    if repository.open_completion_request(cur, task_key):
        raise _conflict(
            "COMPLETION_REQUEST_OPEN", "이 작업에는 진행 중인 완료 확인 요청이 이미 있습니다."
        )
    last = repository.latest_completion_record(cur, task_key)
    if last and last["kind"] == "CONFIRMED" and last["scope_hash"] == item["scope_hash"]:
        raise _conflict(
            "ALREADY_CONFIRMED",
            "이미 완료 확인된 작업입니다. 다시 확인하려면 먼저 철회하세요.",
        )
    return task_key, scope


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
            evidence=e["evidence_json"],
        )
        for e in repository.list_events(cur, request_id)
    ]
    records = [
        CompletionRecordResponse(
            id=str(c["id"]),
            kind=c["kind"],
            decidedByName=c["decided_by_name"],
            decidedAt=c["decided_at"].isoformat(),
            wbsId=c["wbs_id"],
            weightAt=float(c["weight_at"]),
            planVersion=c["plan_version"],
            reportedActual=None if c["reported_actual"] is None else float(c["reported_actual"]),
            completionScope=c["completion_scope"],
            evidence=c["evidence_json"] or {},
            note=c["note"],
        )
        for c in repository.completion_records(cur, request_id)
    ]
    base = _to_response(row)
    return ReviewRequestDetailResponse(
        **base.model_dump(),
        snapshot=before,
        currentState=current,
        changes=snapshot.diff(before, current),
        events=events,
        completionRecords=records,
    )


def report(
    cur: Any, principal: AuthPrincipal, request_id: str, req: ReviewBodyRequest
) -> ReviewRequestDetailResponse:
    """용역사의 조치 보고. 보고 시점 상태를 같이 떠 둔다."""
    _require_contractor(principal)
    row = _load(cur, principal, request_id)
    if row["status"] != "REQUESTED":
        raise errors.validation_failed("요청 상태에서만 보고할 수 있습니다.")
    if not (req.body or "").strip():
        # 공백만 든 보고는 보고가 아니다(IM-007 AC-051-3, GH-220). 상태를 바꾸지 않는다
        raise errors.validation_failed("보고문을 적어 주세요.")
    evidence = None
    if row["purpose"] == "WBS_COMPLETION":
        # 완료 근거가 없는 보고는 받지 않는다. 파일이 없으면 시험·시연·회의 기록을 적는다
        if not req.evidence:
            raise errors.validation_failed("완료 근거를 하나 이상 적어 주세요.")
        bad = [e.kind for e in req.evidence if e.kind not in EVIDENCE_KINDS]
        if bad:
            raise errors.validation_failed(f"근거 종류가 아닙니다: {', '.join(bad)}")
        evidence = [
            _evidence_item(cur, str(row["project_id"]), e) for e in req.evidence
        ]
    _, state = _capture(
        cur, principal, str(row["project_id"]), row["target_type"], row["target_key"]
    )
    now = datetime.now(UTC)
    repository.mark_reported(cur, request_id, req.body.strip(), principal.user_id, state, now)
    repository.insert_event(
        cur, request_id, "REPORTED", req.body.strip(), principal.user_id, state, now,
        evidence=evidence,
    )
    activity.record(
        cur, project_id=str(row["project_id"]), kind=activity.REVIEW_REPORTED,
        audience=activity.CLIENT, summary=f"조치 보고: {row['title']}", actor=principal,
        target_type="REVIEW_REQUEST", target_key=request_id, occurred_at=now,
    )
    return get_detail(cur, principal, request_id)


def confirm(
    cur: Any, principal: AuthPrincipal, request_id: str, req: ReviewConfirmRequest
) -> ReviewRequestDetailResponse:
    """확인완료. 작업 완료 확인 요청이면 완료 확인 기록을 같은 트랜잭션에서 남긴다.

    요청 상태 변경과 기록 저장은 함께 성공하거나 함께 실패한다(어느 쪽이든 예외면 롤백).
    중복 클릭·재시도는 상태 조건부 갱신과 (요청, 종류) 유일 제약이 막는다.
    """
    row = _load(cur, principal, request_id)
    completion_mode = row["purpose"] == "WBS_COMPLETION"
    if completion_mode:
        _require_completion_client(principal)
        if not req.acknowledgeCompletion:
            raise errors.validation_failed(
                "작업 완료를 인정한다는 확인이 필요합니다. 내용을 보고 확인란에 표시하세요."
            )
    else:
        _require_client(principal)
    if row["status"] != "REPORTED":
        if row["status"] == "CONFIRMED":
            raise _conflict("ALREADY_DECIDED", "이미 확인완료된 요청입니다.")
        raise errors.validation_failed("보고된 요청만 확인완료할 수 있습니다.")
    project_id = str(row["project_id"])
    item = None
    if completion_mode:
        item = completion.current_item(cur, project_id, task_key=str(row["task_key"]))
        if item is None:
            raise _conflict(
                "TASK_CHANGED",
                "요청한 작업을 지금 WBS 에서 같은 작업으로 확인할 수 없습니다"
                "(번호·작업명 변경, 분할·병합, 삭제). 새 작업으로 다시 요청하세요.",
            )
        if item["scope_hash"] != (row["snapshot_json"] or {}).get("scope_hash"):
            raise _conflict(
                "SCOPE_CHANGED",
                "요청 뒤 작업명이나 산출물 열이 바뀌었습니다. 바뀐 내용으로 다시 요청하세요.",
            )
    _, state = _capture(cur, principal, project_id, row["target_type"], row["target_key"])
    now = datetime.now(UTC)
    if not repository.mark_confirmed(cur, request_id, principal.user_id, now):
        raise _conflict("ALREADY_DECIDED", "이미 처리된 요청입니다.")
    repository.insert_event(
        cur, request_id, "CONFIRMED", req.note.strip() or None, principal.user_id, state, now
    )
    if completion_mode:
        assert item is not None
        saved = repository.insert_completion_record(cur, {
            "project_id": project_id,
            "task_key": str(item["task_key"]),
            "wbs_id": item["wbs_id"],
            "review_request_id": request_id,
            "kind": "CONFIRMED",
            "decided_by": principal.user_id,
            "decided_at": now,
            "scope_hash": item["scope_hash"],
            "weight_at": item["weight"],
            "plan_work_product_id": item["work_product_id"],
            "plan_version": item["plan_version"],
            "reported_actual": item["actual"],
            "completion_scope": row["completion_scope"],
            "item_json": {
                "name": item["name"], "deliverable": item["deliverable"],
                "start": _iso(item["start_on"]), "end": _iso(item["end_on"]),
            },
            "evidence_json": {
                "facts": {k: state.get(k) for k in _FACT_KEYS},
                "reported": repository.last_reported_evidence(cur, request_id),
                # 근거로 든 산출물 버전의 확인 시점 상태. 뒤에 승인돼도 이 값은 그대로다
                "work_products_at_confirm": _products_now(
                    cur, repository.last_reported_evidence(cur, request_id)
                ),
            },
            "note": req.note.strip() or None,
        })
        if not saved:
            raise _conflict("ALREADY_DECIDED", "이 요청의 완료 확인은 이미 기록됐습니다.")
    activity.record(
        cur, project_id=str(row["project_id"]), kind=activity.REVIEW_CONFIRMED,
        audience=activity.CONTRACTOR, summary=f"확인완료: {row['title']}", actor=principal,
        target_type="REVIEW_REQUEST", target_key=request_id, occurred_at=now,
    )
    return get_detail(cur, principal, request_id)


def withdraw_completion(
    cur: Any, principal: AuthPrincipal, request_id: str, req: CompletionWithdrawRequest
) -> ReviewRequestDetailResponse:
    """완료 확인 철회. 확인 기록은 지우지 않고 철회 한 줄을 더한다. 요청 상태는 그대로다."""
    _require_completion_client(principal)
    row = _load(cur, principal, request_id)
    if row["purpose"] != "WBS_COMPLETION" or row["status"] != "CONFIRMED":
        raise errors.validation_failed("확인완료된 작업 완료 확인 요청만 철회할 수 있습니다.")
    last = repository.latest_completion_record(cur, str(row["task_key"]))
    if last is None or str(last["review_request_id"]) != request_id or last["kind"] != "CONFIRMED":
        raise _conflict(
            "NOT_CURRENT_CONFIRMATION",
            "이 요청의 확인은 이미 철회됐거나 지금 유효한 확인이 아닙니다.",
        )
    now = datetime.now(UTC)
    reason = req.reason.strip()
    saved = repository.insert_completion_record(cur, {
        "project_id": str(row["project_id"]),
        "task_key": str(last["task_key"]),
        "wbs_id": last["wbs_id"],
        "review_request_id": request_id,
        "kind": "WITHDRAWN",
        "decided_by": principal.user_id,
        "decided_at": now,
        "scope_hash": last["scope_hash"],
        "weight_at": last["weight_at"],
        "plan_work_product_id": last["plan_work_product_id"],
        "plan_version": last["plan_version"],
        "reported_actual": last["reported_actual"],
        "completion_scope": last["completion_scope"],
        "item_json": last["item_json"],
        "evidence_json": last["evidence_json"],
        "note": reason,
    })
    if not saved:
        raise _conflict("ALREADY_DECIDED", "이 요청의 확인은 이미 철회됐습니다.")
    repository.insert_event(
        cur, request_id, "COMPLETION_WITHDRAWN", reason, principal.user_id,
        row["snapshot_json"] or {}, now,
    )
    activity.record(
        cur, project_id=str(row["project_id"]), kind=activity.COMPLETION_WITHDRAWN,
        audience=activity.ALL, summary=f"완료 확인 철회: {row['target_label']}", actor=principal,
        target_type="REVIEW_REQUEST", target_key=request_id, occurred_at=now,
    )
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
    activity.record(
        cur, project_id=str(row["project_id"]), kind=activity.REVIEW_REREQUESTED,
        audience=activity.CONTRACTOR, summary=f"다시 요청: {row['title']}", actor=principal,
        target_type="REVIEW_REQUEST", target_key=request_id, occurred_at=now,
    )
    return get_detail(cur, principal, request_id)
