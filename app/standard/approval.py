"""산출물 승인·반려. 발주기관이 한 버전을 받아들이거나 돌려보낸다.

문서 확정(draft confirm)과 다른 행위다. 확정은 사업 구성원 누구나 올린 문서를 산출물
한 버전으로 등록하는 일이고, 승인은 그 버전을 발주기관이 받아들였다는 기록이다.
그래서 역할(발주기관)과 사업 접근을 둘 다 본다. 승인은 버전 하나에 붙는다. 새 버전이
올라오면 승인은 따라가지 않는다(upsert_work_product 와 같은 규칙).
"""

from typing import Any

from app.activity import service as activity
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.standard import repository

APPROVER_ROLES = ("CLIENT", "SUPER_ADMIN")


def _target(
    cur: Any, principal: AuthPrincipal, project_id: str, work_product_id: str
) -> dict[str, Any]:
    if principal.role not in APPROVER_ROLES:
        raise errors.ApiError(403, "FORBIDDEN", "산출물 승인·반려는 발주기관이 합니다.")
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    row = repository.work_product_for_review(cur, work_product_id)
    # 다른 사업의 산출물 id 를 이 사업 경로로 부르면 없는 것으로 본다
    if row is None or str(row["project_id"]) != project_id:
        raise errors.not_found("산출물", work_product_id)
    if not row["is_current"]:
        raise errors.ApiError(
            409,
            "NOT_CURRENT_VERSION",
            "현행 버전이 아닙니다. 승인·반려는 지금 올라와 있는 버전에만 합니다.",
        )
    return row


def _label(row: dict[str, Any]) -> str:
    return f"{row['title'] or row['type']} {row['version'] or ''}".strip()


def approve(cur: Any, principal: AuthPrincipal, project_id: str, work_product_id: str) -> None:
    row = _target(cur, principal, project_id, work_product_id)
    if row["status"] != "SUBMITTED":
        raise errors.ApiError(
            409,
            "NOT_SUBMITTED",
            "제출된 버전만 승인할 수 있습니다. 지금 상태: " + str(row["status"]),
        )
    repository.approve_work_product(cur, work_product_id, principal.user_id)
    activity.record(
        cur,
        project_id=project_id,
        kind=activity.WORK_PRODUCT_APPROVED,
        audience=activity.CONTRACTOR,
        summary=f"산출물 승인: {_label(row)}",
        actor=principal,
        target_type="WORK_PRODUCT",
        target_key=work_product_id,
        detail={"version": row["version"]},
    )


def reject(
    cur: Any, principal: AuthPrincipal, project_id: str, work_product_id: str, reason: str
) -> None:
    reason = (reason or "").strip()
    if not reason:
        raise errors.validation_failed("반려 사유를 적어 주세요.")
    row = _target(cur, principal, project_id, work_product_id)
    if row["status"] not in ("SUBMITTED", "APPROVED"):
        raise errors.ApiError(
            409,
            "NOT_SUBMITTED",
            "제출되거나 승인된 버전만 반려할 수 있습니다. 지금 상태: " + str(row["status"]),
        )
    repository.reject_work_product(cur, work_product_id, reason)
    activity.record(
        cur,
        project_id=project_id,
        kind=activity.WORK_PRODUCT_REJECTED,
        audience=activity.CONTRACTOR,
        summary=f"산출물 반려: {_label(row)}",
        actor=principal,
        target_type="WORK_PRODUCT",
        target_key=work_product_id,
        detail={"version": row["version"], "reason": reason, "was": row["status"]},
    )
