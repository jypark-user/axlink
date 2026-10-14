"""요구사항 상태 지정 (SWFR.PIP.008, ARC-025).

요구사항 상태는 기본으로 근거대로 움직인다(원천 이슈 열림·닫힘 → 정의·구현). 검증·인수처럼
근거가 아직 자동으로 이어지지 않는 단계는 발주기관이 근거를 보고 사유와 함께 지정한다.
지정은 어느 상태로든 할 수 있고, 근거 상태는 지정과 따로 남아 화면에 나란히 보인다.
수집이 다시 돌아도 지정은 그대로다. 지정을 거두면 근거 상태로 돌아간다.

지정·되돌림은 변경 이력(entity_history)과 활동 기록에 남는다. 용역사에게 알림이 간다.
"""

from typing import Any

from app.activity import service as activity
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.standard import mapping, repository
from app.standard.models import RequirementDecision

DECIDER_ROLES = ("CLIENT", "SUPER_ADMIN")
CLIENT_DECIDED = "CLIENT_DECIDED"
REQUIREMENT_STATUS_DECIDED = "REQUIREMENT_STATUS_DECIDED"
REQUIREMENT_STATUS_REVERTED = "REQUIREMENT_STATUS_REVERTED"

_STATUS_WORD = {
    "DEFINED": "정의", "DESIGNED": "설계", "IMPLEMENTED": "구현",
    "VERIFIED": "검증", "ACCEPTED": "인수", "REJECTED": "반려",
}


def status_basis(row: dict[str, Any]) -> str | None:
    """상태의 출처. 지정이 있으면 지정, 없으면 근거 규칙(mapping)대로다."""
    if row.get("decided_status"):
        return CLIENT_DECIDED
    return mapping.requirement_status_basis(row["status"], row["tool_name"])


def decision_of(row: dict[str, Any]) -> RequirementDecision | None:
    if not row.get("decided_status"):
        return None
    return RequirementDecision(
        status=row["decided_status"],
        reason=row["decided_reason"],
        decidedBy=row.get("decided_by_name"),
        decidedAt=row["decided_at"].isoformat(),
    )


def _target(
    cur: Any, principal: AuthPrincipal, project_id: str, requirement_id: str
) -> dict[str, Any]:
    if principal.role not in DECIDER_ROLES:
        raise errors.ApiError(403, "FORBIDDEN", "요구사항 상태 지정은 발주기관이 합니다.")
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    row = repository.get_requirement(cur, project_id, requirement_id)
    if row is None:
        raise errors.not_found("요구사항", requirement_id)
    return row


def _clean(reason: str) -> str:
    text = (reason or "").strip()
    if not text:
        raise errors.validation_failed("사유를 적어 주세요.")
    return text


def _actor(cur: Any, principal: AuthPrincipal) -> str:
    row = auth_repo.find_user_by_id(cur, principal.user_id) or {}
    return row.get("name") or row.get("username") or "사용자"


def _label(row: dict[str, Any]) -> str:
    return f"{row['code'] or ''} {row['title']}".strip()[:120]


def decide(
    cur: Any, principal: AuthPrincipal, project_id: str, requirement_id: str,
    status: str, reason: str,
) -> dict[str, Any]:
    row = _target(cur, principal, project_id, requirement_id)
    if status not in repository.REQUIREMENT_STATUSES:
        raise errors.validation_failed(f"알 수 없는 요구사항 상태입니다: {status}")
    text = _clean(reason)
    before = row["status"]

    repository.set_requirement_decision(cur, requirement_id, status, text, principal.user_id)
    actor = _actor(cur, principal)
    repository.insert_entity_history(
        cur, entity_type="REQUIREMENT", entity_id=requirement_id, project_id=project_id,
        field="status", from_value=before, to_value=status, actor=actor,
    )
    repository.insert_entity_history(
        cur, entity_type="REQUIREMENT", entity_id=requirement_id, project_id=project_id,
        field="status_decision", from_value=row["evidence_status"], to_value=text, actor=actor,
    )
    activity.record(
        cur, project_id=project_id, kind=REQUIREMENT_STATUS_DECIDED,
        audience=activity.CONTRACTOR, actor=principal, actor_label=actor,
        summary=f"요구사항 상태 지정: {_label(row)} → {_STATUS_WORD.get(status, status)}",
        target_type="REQUIREMENT", target_key=requirement_id,
        detail={"from": before, "to": status, "evidence": row["evidence_status"], "reason": text},
    )
    return repository.get_requirement(cur, project_id, requirement_id)


def revert(
    cur: Any, principal: AuthPrincipal, project_id: str, requirement_id: str, reason: str,
) -> dict[str, Any]:
    row = _target(cur, principal, project_id, requirement_id)
    if not row["decided_status"]:
        raise errors.ApiError(
            409, "NOT_DECIDED", "지정된 상태가 없습니다. 이미 근거대로 움직입니다."
        )
    text = _clean(reason)
    before = row["status"]

    repository.clear_requirement_decision(cur, requirement_id)
    actor = _actor(cur, principal)
    repository.insert_entity_history(
        cur, entity_type="REQUIREMENT", entity_id=requirement_id, project_id=project_id,
        field="status", from_value=before, to_value=row["evidence_status"], actor=actor,
    )
    repository.insert_entity_history(
        cur, entity_type="REQUIREMENT", entity_id=requirement_id, project_id=project_id,
        field="status_decision_revert", from_value=before, to_value=text, actor=actor,
    )
    activity.record(
        cur, project_id=project_id, kind=REQUIREMENT_STATUS_REVERTED,
        audience=activity.CONTRACTOR, actor=principal, actor_label=actor,
        summary=f"요구사항 상태 지정 해제: {_label(row)} → 근거대로 "
                f"{_STATUS_WORD.get(row['evidence_status'], row['evidence_status'])}",
        target_type="REQUIREMENT", target_key=requirement_id,
        detail={"from": before, "to": row["evidence_status"], "reason": text},
    )
    return repository.get_requirement(cur, project_id, requirement_id)
