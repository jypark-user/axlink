"""요구사항 기준선 1단계 (GH-139, ARC-028).

용역사가 명세서를 등록하고 추출 결과를 정리해 제출한다. 발주기관이 확정한다. 확정 전 목록은
requirement 에 쓰지 않으므로 요구사항 목록·이행률·추적표 어디에도 나오지 않는다.

확정은 한 트랜잭션이다. 기존 요구사항은 코드로 이어 ID·원천·상태 지정·추적 링크·이력을 그대로
두고, 새 코드만 새 행으로 만든다. 같은 코드인데 내용이 다르면 기본으로 기존 정의를 두고, 발주기관이
고른 코드만 명세서 내용으로 바꾼다. 명세서에 없는 기존 코드는 지우지 않고 기준선 밖으로 남긴다.
그리고 사업의 모든 연결에서 이슈로 요구사항을 만드는 설정을 끈다. 이 중 하나라도 실패하면 아무것도
바뀌지 않는다.

1단계는 최초 기준선만 다룬다. 확정한 뒤의 변경(새 버전 대조·확정)은 후속 단위다. 그때까지 새
명세서를 올려도 기준선은 바뀌지 않는다.
"""

from typing import Any

from app.ai.embedding import embedding_port
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.document import structuring
from app.rag import indexing
from app.standard import baseline_repository as repo
from app.standard import repository, trace_service
from app.standard.models import (
    BaselineConnection,
    BaselineExisting,
    BaselineItemRequest,
    BaselineItemResponse,
    BaselineResponse,
    BaselineStateResponse,
    UnresolvedRefResponse,
)

# 명세서를 올리고 정리·제출하는 쪽과 확정하는 쪽. 관리자는 둘 다 할 수 있고 확정한 역할을 남긴다
AUTHOR_ROLES = ("CONTRACTOR", "SUPER_ADMIN")
CONFIRM_ROLES = ("CLIENT", "SUPER_ADMIN")
_PRIORITIES = ("MUST", "SHOULD", "COULD", "WONT")


def _check_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def _require_role(principal: AuthPrincipal, roles: tuple[str, ...], message: str) -> None:
    if principal.role not in roles:
        raise errors.ApiError(403, "FORBIDDEN", message)


def _actor(cur: Any, principal: AuthPrincipal) -> str:
    row = auth_repo.find_user_by_id(cur, principal.user_id) or {}
    return row.get("name") or row.get("username") or "사용자"


def _load(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str, lock: bool = False
) -> dict[str, Any]:
    _check_project(cur, principal, project_id)
    row = repo.find(cur, project_id, baseline_id, lock=lock)
    if row is None:
        raise errors.not_found("요구사항 기준선", baseline_id)
    return row


def _require_status(row: dict[str, Any], *statuses: str) -> None:
    if row["status"] not in statuses:
        raise errors.ApiError(
            409, "BASELINE_STATE",
            f"지금 상태({row['status']})에서는 할 수 없습니다.",
        )


# --- 조회 ------------------------------------------------------------------


def _same(item: dict[str, Any], existing: dict[str, Any]) -> bool:
    """정의가 같은지. 제목과 중요도를 본다. 이슈에서 온 요구사항의 본문은 이슈 본문 전체라
    명세서 칸과 늘 다르므로 판정에 쓰지 않고 화면에서 나란히 보인다."""
    norm = " ".join((item["title"] or "").split())
    return norm == " ".join((existing["title"] or "").split()) and (
        item["priority"] == existing["priority"]
    )


def _existing(row: dict[str, Any]) -> BaselineExisting:
    source = row.get("connection_name") or (
        "문서" if row.get("source_kind") == "DOCUMENT" else "수기"
    )
    return BaselineExisting(
        requirementId=str(row["id"]), code=row["code"], title=row["title"],
        priority=row["priority"], source=source,
    )


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _to_response(cur: Any, row: dict[str, Any], with_items: bool = True) -> BaselineResponse:
    items = repo.items(cur, str(row["id"])) if with_items else []
    problems = structuring.problems_of(items)
    confirmed = row["status"] == "CONFIRMED"
    result = row["confirm_result"] or {}
    existing = {} if confirmed else repo.existing_by_code(cur, str(row["project_id"]))

    out_items: list[BaselineItemResponse] = []
    counts = {"NEW": 0, "SAME": 0, "CHANGED": 0}
    for item, found in zip(items, problems, strict=True):
        if confirmed:
            match = item["match_result"]
            before = (result.get("before") or {}).get(item["code"])
            ex = BaselineExisting(**before) if before else None
        else:
            hit = existing.get(item["code"]) if item["code"] else None
            match = None if not item["code"] else (
                "NEW" if hit is None else ("SAME" if _same(item, hit) else "CHANGED")
            )
            ex = _existing(hit) if hit else None
        if match:
            counts[match] += 1
        extracted = item["extracted_json"]
        edited = bool(extracted) and any(
            (extracted.get(k) or "") != (item[k] or "") for k in ("code", "title", "body")
        ) or bool(extracted) and extracted.get("priority") != item["priority"]
        out_items.append(BaselineItemResponse(
            id=str(item["id"]), seq=item["seq"], code=item["code"], title=item["title"],
            body=item["body"], priority=item["priority"], location=item["source_location"],
            origin=item["origin"], edited=edited, problems=found, match=match, existing=ex,
            requirementId=str(item["requirement_id"]) if item["requirement_id"] else None,
            specApplied=item["spec_applied"],
        ))

    if confirmed:
        missing = [BaselineExisting(**m) for m in result.get("missing", [])]
        connections = [BaselineConnection(**c) for c in result.get("disabledConnections", [])]
    else:
        codes = {i["code"] for i in items if i["code"]}
        missing = [_existing(r) for c, r in existing.items() if c not in codes]
        connections = [
            BaselineConnection(id=str(c["id"]), name=c["name"], tool=c["tool"])
            for c in repo.connections_creating(cur, str(row["project_id"]))
        ]

    return BaselineResponse(
        id=str(row["id"]), version=row["version"], status=row["status"],
        documentId=str(row["document_upload_id"]) if row["document_upload_id"] else None,
        sourceFilename=row["source_filename"], sourceDocVersion=row["source_doc_version"],
        createdBy=row["created_by_name"], createdAt=row["created_at"].isoformat(),
        submittedBy=row["submitted_by_name"], submittedAt=_iso(row["submitted_at"]),
        returnedReason=row["returned_reason"],
        confirmedBy=row["confirmed_by_name"], confirmedByRole=row["confirmed_by_role"],
        confirmedAt=_iso(row["confirmed_at"]),
        items=out_items,
        blockingCount=sum(
            1 for f in problems if any(p in structuring.BLOCKING_PROBLEMS for p in f)
        ),
        extractionEmpty=with_items and not items,
        counts=counts, missing=missing, connections=connections,
    )


def state(cur: Any, principal: AuthPrincipal, project_id: str) -> BaselineStateResponse:
    _check_project(cur, principal, project_id)
    confirmed = repo.find_confirmed(cur, project_id)
    working = repo.find_open(cur, project_id)
    # 발주기관에게는 용역사가 정리 중인 목록을 보이지 않는다. 제출한 것부터 본다
    hide = working is not None and working["status"] == "DRAFT" and principal.role == "CLIENT"
    counts = repo.requirement_counts(cur, project_id)
    if confirmed is not None:
        current = "CONFIRMED"
    elif working is not None:
        current = working["status"]
    else:
        current = "NONE"
    return BaselineStateResponse(
        state=current,
        confirmed=_to_response(cur, confirmed, with_items=False) if confirmed else None,
        working=None if working is None or hide else _to_response(cur, working),
        workingStatus=working["status"] if working else None,
        requirementCount=counts["total"],
        outsideBaselineCount=counts["outside"],
        creatingConnections=[
            BaselineConnection(id=str(c["id"]), name=c["name"], tool=c["tool"])
            for c in repo.connections_creating(cur, project_id)
        ],
        unresolvedCodeCount=repo.unresolved_count(cur, project_id),
    )


def detail(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str
) -> BaselineResponse:
    row = _load(cur, principal, project_id, baseline_id)
    if row["status"] == "DRAFT" and principal.role == "CLIENT":
        raise errors.ApiError(
            403, "BASELINE_NOT_SUBMITTED", "용역사가 제출하면 볼 수 있습니다."
        )
    return _to_response(cur, row)


def unresolved_refs(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> list[UnresolvedRefResponse]:
    _check_project(cur, principal, project_id)
    rows = repository.list_unresolved_refs(cur, project_id)
    labels = repository.entity_labels(
        cur, {(r["source_type"], str(r["source_id"])) for r in rows}
    )
    return [
        UnresolvedRefResponse(
            code=r["code"], sourceType=r["source_type"], sourceId=str(r["source_id"]),
            sourceLabel=labels.get((r["source_type"], str(r["source_id"])), ("?", None))[0],
            evidenceText=r["evidence_text"], evidenceUrl=r["evidence_url"],
        )
        for r in rows
    ]


# --- 용역사: 등록·정리·제출 ----------------------------------------------------


def create(
    cur: Any, principal: AuthPrincipal, project_id: str, document_id: str
) -> BaselineResponse:
    _check_project(cur, principal, project_id)
    _require_role(principal, AUTHOR_ROLES, "요구사항 명세서 등록은 용역사가 합니다.")
    if repo.find_confirmed(cur, project_id) is not None:
        # 1단계는 최초 기준선만이다. 확정 뒤 새 명세서는 기준선을 바꾸지 않는다
        raise errors.ApiError(
            409, "BASELINE_CONFIRMED",
            "요구사항 기준선이 이미 확정됐습니다. 변경은 변경 관리 절차로 합니다.",
        )
    if repo.find_open(cur, project_id) is not None:
        raise errors.ApiError(
            409, "BASELINE_IN_PROGRESS", "작성 중이거나 확정을 기다리는 기준선이 있습니다."
        )
    document = repo.find_document(cur, document_id)
    if document is None or str(document["project_id"]) != project_id:
        raise errors.not_found("문서", document_id)
    text = document.get("extracted_text")
    if not text:
        raise errors.ApiError(
            409, "DOCUMENT_NOT_EXTRACTED",
            "문서에서 글을 아직 읽지 못했습니다. 처리 뒤 다시 등록하세요.",
        )

    baseline_id = repo.insert(
        cur, project_id, repo.next_version(cur, project_id), document,
        structuring.guess_version(text), principal.user_id,
    )
    # 추출 결과는 버리는 행 없이 모두 넣는다. 중복·꼴 문제는 표시하고 사람이 고친다
    for seq, item in enumerate(structuring.spec_items(text), start=1):
        repo.insert_item(cur, baseline_id, seq, item.as_dict(), "EXTRACTED")
    return _to_response(cur, repo.find(cur, project_id, baseline_id))


def _editable(cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str) -> None:
    _require_role(principal, AUTHOR_ROLES, "명세서 항목 정리는 용역사가 합니다.")
    row = _load(cur, principal, project_id, baseline_id, lock=True)
    _require_status(row, "DRAFT")


def _clean_item(req: BaselineItemRequest) -> dict[str, Any]:
    if req.priority not in _PRIORITIES:
        raise errors.validation_failed(f"중요도는 {', '.join(_PRIORITIES)} 중 하나입니다.")
    return {
        "code": req.code.strip() or None, "title": " ".join(req.title.split()),
        "body": req.body.strip(), "priority": req.priority,
    }


def update_item(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str, item_id: str,
    req: BaselineItemRequest,
) -> BaselineResponse:
    _editable(cur, principal, project_id, baseline_id)
    if repo.find_item(cur, baseline_id, item_id) is None:
        raise errors.not_found("명세서 항목", item_id)
    repo.update_item(cur, item_id, _clean_item(req))
    return _to_response(cur, repo.find(cur, project_id, baseline_id))


def add_item(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str,
    req: BaselineItemRequest,
) -> BaselineResponse:
    _editable(cur, principal, project_id, baseline_id)
    repo.insert_item(cur, baseline_id, repo.next_seq(cur, baseline_id), _clean_item(req), "MANUAL")
    return _to_response(cur, repo.find(cur, project_id, baseline_id))


def delete_item(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str, item_id: str
) -> BaselineResponse:
    _editable(cur, principal, project_id, baseline_id)
    if repo.find_item(cur, baseline_id, item_id) is None:
        raise errors.not_found("명세서 항목", item_id)
    repo.delete_item(cur, item_id)
    return _to_response(cur, repo.find(cur, project_id, baseline_id))


def discard(cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str) -> None:
    """잘못 올린 명세서를 버린다. 작성 중일 때만. 요구사항에는 아무것도 쓰지 않았다."""
    _editable(cur, principal, project_id, baseline_id)
    repo.delete(cur, baseline_id)


def submit(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str
) -> BaselineResponse:
    _editable(cur, principal, project_id, baseline_id)
    items = repo.items(cur, baseline_id)
    if not items:
        raise errors.validation_failed(
            "명세서에서 요구사항을 찾지 못했습니다. 항목을 더하거나 다른 파일을 올리세요."
        )
    blocking = []
    for i, found in zip(items, structuring.problems_of(items), strict=True):
        hard = [p for p in found if p in structuring.BLOCKING_PROBLEMS]
        if hard:
            blocking.append(f"{i['code'] or '(코드 없음)'}: {', '.join(hard)}")
    if blocking:
        raise errors.validation_failed(
            f"고쳐야 할 항목이 {len(blocking)}건 있습니다. " + "; ".join(blocking[:5])
        )
    repo.set_submitted(cur, baseline_id, principal.user_id)
    return _to_response(cur, repo.find(cur, project_id, baseline_id))


# --- 발주기관: 돌려보내기·확정 -------------------------------------------------


def return_to_author(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str, reason: str
) -> BaselineResponse:
    _require_role(principal, CONFIRM_ROLES, "기준선 반려는 발주기관이 합니다.")
    row = _load(cur, principal, project_id, baseline_id, lock=True)
    _require_status(row, "SUBMITTED")
    text = reason.strip()
    if not text:
        raise errors.validation_failed("사유를 적어 주세요.")
    repo.set_returned(cur, baseline_id, text)
    return _to_response(cur, repo.find(cur, project_id, baseline_id))


def confirm(
    cur: Any, principal: AuthPrincipal, project_id: str, baseline_id: str,
    apply_spec_codes: list[str],
) -> BaselineResponse:
    """최초 기준선 확정. 호출한 쪽의 트랜잭션 하나로 끝난다. 중간에 실패하면 전부 되돌아간다."""
    _require_role(principal, CONFIRM_ROLES, "요구사항 기준선 확정은 발주기관이 합니다.")
    row = _load(cur, principal, project_id, baseline_id, lock=True)
    _require_status(row, "SUBMITTED")
    if repo.find_confirmed(cur, project_id) is not None:
        raise errors.ApiError(409, "BASELINE_CONFIRMED", "요구사항 기준선이 이미 확정됐습니다.")

    items = repo.items(cur, baseline_id)
    if any(
        any(p in structuring.BLOCKING_PROBLEMS for p in found)
        for found in structuring.problems_of(items)
    ):
        raise errors.validation_failed("고쳐야 할 항목이 있어 확정할 수 없습니다.")

    existing = repo.existing_by_code(cur, project_id, lock=True)
    changed = {
        i["code"] for i in items
        if i["code"] in existing and not _same(i, existing[i["code"]])
    }
    unknown = set(apply_spec_codes) - changed
    if unknown:
        raise errors.validation_failed(
            "내용이 다른 기존 요구사항만 명세서 내용으로 바꿀 수 있습니다: "
            + ", ".join(sorted(unknown))
        )

    actor = _actor(cur, principal)
    label = f"v{row['version']}"
    document_id = str(row["document_upload_id"]) if row["document_upload_id"] else None
    before: dict[str, dict[str, Any]] = {}
    sources: list[indexing.IndexSource] = []
    for item in items:
        hit = existing.get(item["code"])
        if hit is None:
            rid = repo.insert_requirement(cur, project_id, item, document_id, baseline_id)
            match, applied = "NEW", False
            sources.append(indexing.IndexSource(
                source_type="REQUIREMENT", source_id=rid, project_id=project_id,
                title=f"{item['code']} {item['title']}", body=item["body"],
            ))
        else:
            rid = str(hit["id"])
            match = "CHANGED" if item["code"] in changed else "SAME"
            applied = item["code"] in apply_spec_codes
            before[item["code"]] = _existing(hit).model_dump()
            repo.attach_requirement(cur, rid, baseline_id, item, applied)
            if applied:
                for field in ("title", "priority"):
                    if hit[field] != item[field]:
                        repository.insert_entity_history(
                            cur, entity_type="REQUIREMENT", entity_id=rid,
                            project_id=project_id, field=field, from_value=hit[field],
                            to_value=item[field], actor=actor,
                        )
        repository.insert_entity_history(
            cur, entity_type="REQUIREMENT", entity_id=rid, project_id=project_id,
            field="baseline", from_value=None, to_value=f"{label} {match}", actor=actor,
        )
        repo.record_item_match(cur, str(item["id"]), rid, match, applied)

    codes = {i["code"] for i in items}
    missing = [_existing(r).model_dump() for c, r in existing.items() if c not in codes]
    stopped = repo.stop_creating(cur, project_id)
    for conn in stopped:
        repository.insert_entity_history(
            cur, entity_type="TOOL_CONNECTION", entity_id=str(conn["id"]),
            project_id=project_id, field="requirement_from_issues",
            from_value="true", to_value="false", actor=actor,
        )
    repo.set_confirmed(cur, baseline_id, principal.user_id, principal.role, {
        "before": before,
        "missing": missing,
        "disabledConnections": [
            {"id": str(c["id"]), "name": c["name"], "tool": c["tool"]} for c in stopped
        ],
    })
    repository.insert_entity_history(
        cur, entity_type="REQUIREMENT_BASELINE", entity_id=baseline_id, project_id=project_id,
        field="status", from_value="SUBMITTED", to_value="CONFIRMED", actor=actor,
    )
    # 새 코드가 생겼으니 미해결이던 참조가 풀린다. 같은 트랜잭션에서 다시 잇는다
    trace_service.build_project_links(cur, project_id)
    if sources:
        try:
            indexing.reindex(cur, embedding_port(), sources)
        except errors.ApiError as exc:
            if not exc.code.startswith("AI_"):
                raise
            # 색인은 검색용이다. 실패해도 확정은 남긴다. 다음 수집·재색인이 채운다
    return _to_response(cur, repo.find(cur, project_id, baseline_id))
