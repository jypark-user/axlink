"""WBS 작업 완료 확인 (ARC-019). 보고 진척률 옆의 '완료 확인율'과 작업별 근거 사실.

네 가지 사실을 섞지 않는다.
- 파일 대조: WBS 산출물 열과 같은 파일·문서가 있는가(deliverable.judge). 제출이 아니다
- 정식 제출: 맞춘 근거가 산출물 항목이고 그 항목이 제출 상태인가. 산출물 항목이 없으면 모른다
- 산출물 승인: 그 산출물 버전을 발주기관이 승인했는가
- 작업 완료 확인: 발주기관이 '작업 완료 확인' 요청으로 이 작업의 완료를 인정했는가

완료 확인율은 마지막 것만 센다. 집계는 v_wbs_completion 뷰 하나에서 하고, 시맨틱 지표
wbs_completion_rate 도 같은 뷰를 읽는다(메뉴와 질의가 같은 수치).
"""

from datetime import date
from typing import Any

from app.dashboard import deliverable
from app.dashboard import service as dashboard_service
from app.db import fetch_all, fetch_one

# 파일 대조 결과. 판정 코드 SUBMITTED 는 '파일·문서가 있다'는 뜻이라 MATCHED 로 바꿔 부른다
FILE_CHECK = {
    deliverable.SUBMITTED: "MATCHED",
    deliverable.MISSING: "MISSING",
    deliverable.OVERDUE: "OVERDUE",
    deliverable.NONE: "NONE",
}


def _product(cur: Any, product_id: str | None) -> dict[str, Any] | None:
    if not product_id:
        return None
    return fetch_one(
        cur,
        "select id, type, version, status, approved_at, is_current from work_product where id = %s",
        (product_id,),
    )


def facts_from(
    cur: Any, judged: deliverable.Judgement | None, tree_sha: str | None
) -> dict[str, Any]:
    """판정 하나에서 근거 사실 넷 중 셋(파일 대조·정식 제출·승인)을 뽑는다.

    산출물 항목에 닿지 못했으면(저장소 파일만 있음 등) 제출·승인은 UNKNOWN 이다.
    파일이 있다는 사실로 제출을 대신하지 않는다.
    """
    if judged is None:
        return {
            "file_check": None, "file_rule": None, "file_ref": None, "repo_revision": tree_sha,
            "submission": "UNKNOWN", "approval": "UNKNOWN",
            "product_id": None, "product_version": None, "approved_at": None,
        }
    product = _product(cur, judged.product_id)
    if product is None:
        submission = approval = "UNKNOWN"
    else:
        status = product["status"]
        submission = {
            "SUBMITTED": "SUBMITTED", "APPROVED": "SUBMITTED", "REJECTED": "SUBMITTED",
            "DRAFT": "DRAFT",
        }.get(status, "UNKNOWN")
        approval = {"APPROVED": "APPROVED", "REJECTED": "REJECTED"}.get(status, "NOT_APPROVED")
    return {
        "file_check": FILE_CHECK.get(judged.status, judged.status),
        "file_rule": judged.rule,
        "file_ref": judged.ref,
        "repo_revision": tree_sha,
        "submission": submission,
        "approval": approval,
        "product_id": str(product["id"]) if product else None,
        "product_version": product["version"] if product else None,
        "approved_at": product["approved_at"].isoformat()
        if product and product["approved_at"] else None,
    }


def item_facts(cur: Any, project_id: str, at: date) -> dict[str, dict[str, Any]]:
    """말단 작업마다 근거 사실. 대조는 읽기만 한다(저장·활동 기록 없음)."""
    check = dashboard_service.judge_deliverables(cur, project_id, at)
    by_id = {j.wbs_id: j for j in check.judgements}
    return {
        i["wbs_id"]: facts_from(cur, by_id.get(i["wbs_id"]), check.tree_sha)
        for i in check.items
        if i.get("weight") is not None
    }


def current_item(cur: Any, project_id: str, *, wbs_id: str | None = None,
                 task_key: str | None = None) -> dict[str, Any] | None:
    """지금 계획의 활성 말단 작업 하나. 번호 또는 작업 식별자로 찾는다."""
    where, arg = ("w.wbs_id = %s", wbs_id) if wbs_id else ("w.task_key = %s", task_key)
    return fetch_one(
        cur,
        f"""
        select w.id, w.wbs_id, w.task_key, w.name, w.deliverable, w.weight, w.actual,
               w.start_on, w.end_on, w.scope_hash, w.key_reason, w.work_product_id,
               p.version as plan_version
          from wbs_item w
          left join work_product p on p.id = w.work_product_id
         where w.project_id = %s and w.active and w.weight is not null and {where}
        """,
        (project_id, arg),
    )


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


def summary(cur: Any, project_id: str, at: date) -> dict[str, Any]:
    """완료 확인 화면의 숫자와 작업 행. 분모가 없으면 비율은 None(산출 불가)."""
    rows = fetch_all(
        cur,
        """
        select v.*, w.line_no, p.version as plan_version_now,
               rr.id as open_request_id, rr.status as open_request_status,
               cr.evidence_json as confirmed_evidence, cr.decided_at as confirmed_at,
               u.name as confirmed_by
          from v_wbs_completion v
          join wbs_item w on w.id = v.wbs_item_id
          left join work_product p on p.id = w.work_product_id
          left join review_request rr
            on rr.task_key = v.task_key and rr.purpose = 'WBS_COMPLETION'
           and rr.status in ('REQUESTED', 'REPORTED')
          left join wbs_completion_record cr on cr.id = v.record_id
          left join app_user u on u.id = cr.decided_by_user_id
         where v.project_id = %s
         order by w.line_no, v.wbs_id
        """,
        (project_id,),
    )
    facts = item_facts(cur, project_id, at) if rows else {}
    total_w = sum(float(r["weight"]) for r in rows)
    confirmed_w = sum(float(r["weight"]) for r in rows if r["completion_status"] == "CONFIRMED")
    reported = (
        sum(float(r["weight"]) * float(r["actual"] or 0) for r in rows) / total_w
        if total_w else None
    )
    items = []
    for r in rows:
        now = facts.get(r["wbs_id"], {})
        then = (r["confirmed_evidence"] or {}).get("facts", {}) if r["record_id"] else {}
        # 확인 뒤 근거가 바뀌었는가. 파일·저장소 기준·산출물 버전 중 하나라도 다르면 개정이다
        revised = bool(then) and r["completion_status"] == "CONFIRMED" and any(
            then.get(k) != now.get(k) for k in ("file_ref", "repo_revision", "product_version")
        )
        items.append({
            "wbsId": r["wbs_id"], "taskKey": str(r["task_key"]), "name": r["name"],
            "deliverable": r["deliverable"], "weight": float(r["weight"]),
            "reportedActual": _f(r["actual"]), "keyReason": r["key_reason"],
            "fileCheck": now.get("file_check"), "fileRef": now.get("file_ref"),
            "submission": now.get("submission", "UNKNOWN"),
            "approval": now.get("approval", "UNKNOWN"),
            "productVersion": now.get("product_version"),
            "completionStatus": r["completion_status"],
            "predecessorConfirmed": r["predecessor_confirmed"],
            "confirmedAt": r["confirmed_at"].isoformat() if r["confirmed_at"] else None,
            "confirmedBy": r["confirmed_by"],
            "weightAtConfirm": _f(r["weight_at"]), "planVersionAtConfirm": r["plan_version"],
            "actualAtConfirm": _f(r["actual_at"]),
            "evidenceRevised": revised,
            "openRequestId": str(r["open_request_id"]) if r["open_request_id"] else None,
            "openRequestStatus": r["open_request_status"],
        })
    reported_full = [i for i in items if (i["reportedActual"] or 0) >= 1]
    return {
        "reportedPct": reported,
        "completionRate": confirmed_w / total_w if total_w else None,
        "basis": "완료 확인 기록 기준 · 가중치는 현재 WBS"
        + (f"(계획서 {rows[0]['plan_version_now']})" if rows and rows[0]["plan_version_now"]
           else "") + " 기준",
        "leafCount": len(items),
        "confirmedCount": sum(i["completionStatus"] == "CONFIRMED" for i in items),
        "reconfirmCount": sum(
            i["completionStatus"] == "RECONFIRM" or (
                i["completionStatus"] == "NONE" and i["predecessorConfirmed"]
            )
            for i in items
        ),
        "reported100Count": len(reported_full),
        "reported100Pending": sum(i["completionStatus"] != "CONFIRMED" for i in reported_full),
        "inProgressCount": sum(i["openRequestId"] is not None for i in items),
        "items": items,
    }
