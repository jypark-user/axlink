"""WBS 작업별 지정 산출물·양식 (UC-033, 10-14 협의 1-1절 「WBS 산출물」, GH-141).

발주기관이 작업마다 「무엇을 내야 하나」(항목)와 「어떻게 쓰나」(양식·작성 안내)를 정한다.
용역사는 항목을 골라 제출하고, 제출본의 승인·반려는 지금처럼 산출물 버전에 붙는다(UC-031).

지키는 것
- 양식은 제출본이 아니다. 문서 표에 넣지 않아 판정·승인률에 들지 않는다.
- 업로드만으로 제출이 아니다. 초안을 확정해야 제출이다(DEC-14).
- 22종은 분류일 뿐이다. 지정 항목을 22종으로 강제하지 않고, 다른 유형으로 내도 막지 않는다.
- 지정은 작업 정체(task_key)에 묶인다. 계획서를 다시 올려 정체가 끊기면 「재지정 필요」로
  보이고 지정·제출 이력은 남는다. WBS 산출물 열은 편집하지 않는다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.auth import duties
from app.auth.deps import AuthPrincipal
from app.common import errors
from app.dashboard import designation_repository as repo
from app.dashboard.models import (
    DesignatedDeliverable,
    DesignatedVersion,
    DesignateRequest,
    DesignationEvent,
    DesignationUpdateRequest,
)
from app.document import extractor
from app.standard.work_product_type import DISPLAY_NAMES

MISSING = "MISSING"
REGISTERED = "REGISTERED"  # 올렸지만 확정 전. 제출이 아니다
SUBMITTED = "SUBMITTED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"

# 초안 확정의 두 갈래. 제안한 유형대로면 CONFIRMED, 사람이 유형을 바꿔 확정하면 MANUAL_OVERRIDE
_CONFIRMED_DRAFT = ("CONFIRMED", "MANUAL_OVERRIDE")

RULE_DESIGNATED = "DESIGNATED"

TEMPLATE_MAX_BYTES = 20 * 1024 * 1024
NAME_MAX = 300


# ---------------------------------------------------------------- 순수 함수


def version_state(row: dict[str, Any]) -> str:
    """양식 자리에 올라온 산출물 하나의 상태(V70). 올라오면 제출, 발주기관이 승인·반려한다.

    예전에는 초안을 확정해 22종 산출물 버전이 생겨야 제출이었다. 2026-11-18 사용자 결정으로
    올라온 산출물 자체가 승인 단위가 됐다.
    """
    status = row.get("review_status")
    return status if status in (SUBMITTED, APPROVED, REJECTED) else SUBMITTED


def submit_readiness(row: dict[str, Any]) -> str | None:
    """예전 「산출물로 제출」 단계의 다음 할 일. 올리면 제출이라 이제 늘 없다(V70)."""
    return None


def item_status(states: list[str]) -> str:
    """항목 상태는 가장 최근 올라온 산출물이 정한다. states 는 최근 것이 앞이다."""
    return states[0] if states else MISSING


def is_submitted(status: str) -> bool:
    """판정에서 「제출」로 세는가. 반려도 제출은 된 것이다(승인 여부는 따로 본다)."""
    return status in (SUBMITTED, APPROVED, REJECTED)


@dataclass(frozen=True)
class Coverage:
    """한 작업의 지정 항목 제출 현황. 판정(deliverable.judge)의 재료."""

    total: int
    submitted: int
    # 승인률(DEC-12)이 볼 산출물. 양식이 모두 승인이면 승인된 것, 아니면 아직 승인 안 된 것.
    # 이걸 판정에 실어 두면 승인률 계산이 양식 없는 작업과 같은 길(현행 버전 승인 여부)로 간다
    product_id: str | None = None


# ---------------------------------------------------------------- 조회 조립


def _versions(rows: list[dict[str, Any]]) -> list[DesignatedVersion]:
    return [
        DesignatedVersion(
            documentId=str(r["id"]),
            fileName=r["original_filename"],
            uploadedAt=r["created_at"].isoformat(),
            state=version_state(r),
            workProductId=str(r["work_product_id"]) if r.get("work_product_id") else None,
            version=r.get("wp_version"),
            rejectReason=r.get("review_reason") if r.get("review_status") == REJECTED else None,
            decidedAt=r["reviewed_at"].isoformat()
            if r.get("reviewed_at") and r.get("review_status") == APPROVED
            else None,
            isCurrent=True,
            submit=submit_readiness(r),
        )
        for r in rows
    ]


def build(
    cur: Any, project_id: str, live_task_keys: set[str]
) -> tuple[dict[str, list[DesignatedDeliverable]], list[DesignatedDeliverable]]:
    """지정 항목을 작업 정체별로 묶는다. 지금 계획서에 없는 정체의 항목은 따로 낸다."""
    by_item: dict[str, list[dict[str, Any]]] = {}
    for s in repo.submissions(cur, project_id):
        by_item.setdefault(str(s["designated_deliverable_id"]), []).append(s)

    by_task: dict[str, list[DesignatedDeliverable]] = {}
    orphans: list[DesignatedDeliverable] = []
    for row in repo.list_active(cur, project_id):
        versions = _versions(by_item.get(str(row["id"]), []))
        task_key = str(row["task_key"])
        view = DesignatedDeliverable(
            id=str(row["id"]),
            taskKey=task_key,
            wbsIdAt=row["wbs_id_at"],
            taskNameAt=row["task_name_at"],
            name=row["name"],
            description=row.get("description"),
            productType=row.get("product_type"),
            guide=row.get("guide"),
            templateFileName=row.get("template_filename"),
            templateSize=row.get("template_size"),
            status=item_status([v.state for v in versions]),
            needsRedesignation=task_key not in live_task_keys,
            versions=versions,
            origin=row.get("origin") or "REQUEST",
        )
        if view.needsRedesignation and view.origin == "WBS":
            continue  # WBS 에서 온 것은 그 작업이 없어지면 함께 없어진다. 재지정 대상이 아니다
        if view.needsRedesignation:
            orphans.append(view)
        else:
            by_task.setdefault(task_key, []).append(view)
    return by_task, orphans


def coverage(cur: Any, project_id: str, live_task_keys: set[str]) -> dict[str, Coverage]:
    """작업 정체별 지정 항목 수와 그중 제출된 수. 지정이 없는 작업은 들어 있지 않다."""
    by_task, _ = build(cur, project_id, live_task_keys)
    return {
        key: Coverage(
            len(items), sum(1 for i in items if is_submitted(i.status)), _review_product(items)
        )
        for key, items in by_task.items()
    }


def _latest_product(item: DesignatedDeliverable) -> str | None:
    return next((v.workProductId for v in item.versions if v.workProductId), None)


def _review_product(items: list[DesignatedDeliverable]) -> str | None:
    """작업의 승인 여부를 대표하는 산출물. 모두 승인이면 그중 하나, 아니면 승인 안 된 것 하나."""
    if items and all(i.status == APPROVED for i in items):
        return _latest_product(items[0])
    for i in items:
        if i.status != APPROVED:
            return _latest_product(i)
    return None


# ---------------------------------------------------------------- 변경


def _require_access(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    from app.dashboard import service as dashboard_service

    dashboard_service.require_project(cur, principal, project_id)


def _clean_name(value: str | None) -> str:
    name = (value or "").strip()
    if not name:
        raise errors.validation_failed("산출물 이름을 적으세요.")
    if len(name) > NAME_MAX:
        raise errors.validation_failed(f"산출물 이름은 {NAME_MAX}자까지입니다.")
    return name


def _clean_type(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    code = value.strip()
    if code not in DISPLAY_NAMES:
        raise errors.validation_failed(f"알 수 없는 산출물 분류입니다: {code}")
    return code


def _blank_to_none(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _task_key(value: str) -> str:
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError):
        raise errors.validation_failed("작업을 고르세요.") from None


def _leaf(cur: Any, project_id: str, task_key: str) -> dict[str, Any]:
    """지정할 작업. WBS 가 없으면 먼저 등록하라고 한다(UC-033 E3)."""
    from app.dashboard import service as dashboard_service
    from app.standard import wbs_repository

    dashboard_service.ensure_wbs_loaded(cur, project_id)
    if not wbs_repository.list_items(cur, project_id):
        raise errors.validation_failed("먼저 WBS 를 등록하세요.")
    leaf = repo.active_leaf_by_task(cur, project_id, task_key)
    if leaf is None:
        raise errors.validation_failed("지금 WBS 에 그 작업이 없습니다. 작업을 다시 고르세요.")
    return leaf


def _uuid_or_404(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise errors.not_found("지정 산출물", value) from None


def _owned(cur: Any, project_id: str, designated_id: str) -> dict[str, Any]:
    row = repo.find(cur, _uuid_or_404(designated_id))
    if row is None or str(row["project_id"]) != project_id or not row["active"]:
        raise errors.not_found("지정 산출물", designated_id)
    return row


def designate(
    cur: Any, principal: AuthPrincipal, project_id: str, req: DesignateRequest
) -> str:
    """작업에 내야 할 산출물 항목을 정한다. 발주기관만 한다(AC-033-1)."""
    duties.require(principal, "DELIVERABLE_DESIGNATE")
    _require_access(cur, principal, project_id)
    name = _clean_name(req.name)
    product_type = _clean_type(req.productType)
    leaf = _leaf(cur, project_id, _task_key(req.taskKey))
    row = repo.insert(
        cur, project_id, str(leaf["task_key"]), leaf["wbs_id"], leaf["name"], name,
        _blank_to_none(req.description), product_type, _blank_to_none(req.guide),
        principal.user_id,
    )
    repo.add_event(cur, str(row["id"]), "CREATED", principal.user_id, {
        "wbsId": leaf["wbs_id"], "taskName": leaf["name"], "name": name,
        "productType": product_type,
    })
    return str(row["id"])


def update(
    cur: Any, principal: AuthPrincipal, project_id: str, designated_id: str,
    req: DesignationUpdateRequest,
) -> None:
    """항목 내용을 고치거나 다른 작업으로 옮긴다(재지정). 바뀐 칸만 이력에 남긴다."""
    duties.require(principal, "DELIVERABLE_DESIGNATE")
    _require_access(cur, principal, project_id)
    row = _owned(cur, project_id, designated_id)

    fields: dict[str, Any] = {}
    sent = req.model_fields_set
    if "name" in sent:
        fields["name"] = _clean_name(req.name)
    if "description" in sent:
        fields["description"] = _blank_to_none(req.description)
    if "productType" in sent:
        fields["product_type"] = _clean_type(req.productType)
    if "guide" in sent:
        fields["guide"] = _blank_to_none(req.guide)
    changed = {k: v for k, v in fields.items() if row.get(k) != v}
    if changed:
        repo.update_fields(cur, designated_id, changed)
        repo.add_event(cur, designated_id, "UPDATED", principal.user_id, {
            "before": {k: row.get(k) for k in changed}, "after": changed,
        })

    if "taskKey" in sent and req.taskKey:
        leaf = _leaf(cur, project_id, _task_key(req.taskKey))
        if str(leaf["task_key"]) != str(row["task_key"]) and row.get("origin") == "WBS":
            raise errors.ApiError(
                409, "WBS_EXPECTED_FIXED",
                "WBS 에서 온 예상 산출물은 다른 작업으로 옮길 수 없습니다.",
            )
        if str(leaf["task_key"]) != str(row["task_key"]):
            repo.update_fields(cur, designated_id, {
                "task_key": str(leaf["task_key"]), "wbs_id_at": leaf["wbs_id"],
                "task_name_at": leaf["name"],
            })
            repo.add_event(cur, designated_id, "REASSIGNED", principal.user_id, {
                "from": {"wbsId": row["wbs_id_at"], "taskName": row["task_name_at"]},
                "to": {"wbsId": leaf["wbs_id"], "taskName": leaf["name"]},
            })


def remove(cur: Any, principal: AuthPrincipal, project_id: str, designated_id: str) -> None:
    """지정을 거둔다. 행과 제출 이력은 지우지 않는다."""
    duties.require(principal, "DELIVERABLE_DESIGNATE")
    _require_access(cur, principal, project_id)
    row = _owned(cur, project_id, designated_id)
    repo.update_fields(cur, designated_id, {"active": False})
    repo.add_event(cur, designated_id, "REMOVED", principal.user_id, {
        "wbsId": row["wbs_id_at"], "name": row["name"],
    })


def put_template(
    cur: Any, principal: AuthPrincipal, project_id: str, designated_id: str,
    filename: str, content: bytes,
) -> None:
    """양식 파일을 올린다. 문서 표에 넣지 않으므로 제출본으로 세지 않는다(AC-033-3)."""
    duties.require(principal, "DELIVERABLE_DESIGNATE")
    _require_access(cur, principal, project_id)
    row = _owned(cur, project_id, designated_id)
    name = (filename or "").strip()
    if not name:
        raise errors.validation_failed("파일명이 없습니다.")
    ext = extractor.ext_of(name)
    if ext not in extractor.SUPPORTED_EXTS:
        raise errors.validation_failed(
            f"{' · '.join(extractor.SUPPORTED_EXTS)} 만 양식으로 올릴 수 있습니다."
        )
    if not content:
        raise errors.validation_failed("빈 파일입니다.")
    if len(content) > TEMPLATE_MAX_BYTES:
        raise errors.validation_failed("양식은 20MB 이하 파일만 올릴 수 있습니다.")
    repo.save_template(
        cur, designated_id, name, extractor.MIME_BY_EXT.get(ext, "application/octet-stream"),
        content,
    )
    repo.add_event(cur, designated_id, "TEMPLATE", principal.user_id, {
        "fileName": name, "size": len(content), "before": row.get("template_filename"),
    })


def get_template(
    cur: Any, principal: AuthPrincipal, project_id: str, designated_id: str
) -> dict[str, Any]:
    """양식 내려받기. 그 사업을 볼 수 있으면 누구나 받는다."""
    _require_access(cur, principal, project_id)
    _owned(cur, project_id, designated_id)
    row = repo.load_template(cur, designated_id)
    if row is None:
        raise errors.not_found("양식", designated_id)
    return row


def history(
    cur: Any, principal: AuthPrincipal, project_id: str, designated_id: str
) -> list[DesignationEvent]:
    """지정 변경 이력. 거둔 항목도 본다."""
    _require_access(cur, principal, project_id)
    row = repo.find(cur, _uuid_or_404(designated_id))
    if row is None or str(row["project_id"]) != project_id:
        raise errors.not_found("지정 산출물", designated_id)
    return [
        DesignationEvent(
            kind=e["kind"], at=e["at"].isoformat(), actorName=e["actor_name"],
            actorRole=e["actor_role"], detail=e["detail_json"] or {},
        )
        for e in repo.events(cur, designated_id)
    ]


def resolve_for_upload(cur: Any, project_id: str, designated_id: str) -> str:
    """지정 항목을 골라 올릴 때 붙일 WBS 항목 id. 작업이 끊긴 항목에는 받지 않는다."""
    row = _owned(cur, project_id, designated_id)
    leaf = repo.active_leaf_by_task(cur, project_id, str(row["task_key"]))
    if leaf is None:
        raise errors.validation_failed(
            "계획서가 바뀌어 이 항목은 재지정이 필요합니다. "
            "발주기관이 작업을 다시 정한 뒤 올리세요."
        )
    return str(leaf["id"])
