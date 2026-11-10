"""확인 요청 대상의 상태를 그 시점 그대로 떠 둔다 (SWFR.WEB.004).

대상은 다섯 종류다. WBS 항목·산출물·이슈·리스크·지표. 종류마다 "상태"라 부를 만한
값이 다르므로 종류별로 뽑는 값을 여기서 정한다. 값은 전부 DB 나 WBS 파일에서 읽은
것이고, 지표는 진척 집계 결과다. 사람이 적거나 모델이 만든 값은 없다.

보고·확인 시점에는 같은 함수를 다시 불러 "그때"와 "지금"을 나란히 놓는다(SWFR.WEB.005).
"""

from typing import Any

from app.auth.models import AuthPrincipal
from app.common import clock
from app.dashboard import completion
from app.dashboard import service as dashboard_service
from app.db import fetch_all, fetch_one
from app.review.models import ReviewStateChange, ReviewTargetOption
from app.semantic import service as semantic
from app.semantic.models import WidgetQuery, WidgetSpec
from app.standard import work_product_type

# 화면에 보여 줄 필드 이름. 발주기관 어휘로 (작업 규약 1절 9번).
FIELD_LABELS = {
    "status": "상태",
    "severity": "심각도",
    "assignee": "담당",
    "owner": "담당",
    "resolved_at": "해결일",
    "closed_at": "종료일",
    "title": "제목",
    "version": "버전",
    "submitted_at": "제출일",
    "approved_at": "승인일",
    "file_uri": "파일",
    "actual": "실적률",
    "declared_planned": "계획률",
    "deliverable": "연결 산출물",
    "weight": "가중치",
    "file_check": "파일 대조",
    "file_rule": "대조 방법",
    "file_ref": "대조된 파일",
    "repo_revision": "저장소 기준",
    "submission": "정식 제출",
    "approval": "산출물 승인",
    "product_version": "산출물 버전",
    "plan_version": "WBS 계획서 버전",
    "task_key": "작업 식별자",
    "scope_hash": "작업 범위",
    "end": "종료일",
    "value": "값",
    "numerator": "분자",
    "denominator": "분모",
    "level": "산정 수준",
    "basis": "근거",
    "source_priority": "우선순위",
    "linked_issues": "연결 이슈",
    "progress_representative": "보고 진척률",
    "progress_level": "진척률 산정 수준",
    "issue_resolution_rate": "일반 이슈 처리율",
    "risk_resolution_rate": "위험 처리율",
    "open_risk_count": "열린 리스크",
}

METRIC_KEYS = {
    "REPRESENTATIVE": "대표 진척률",
    "PROGRESS_WBS": "WBS 기반 진척률",
    "PROGRESS_ISSUE": "일반 이슈 해결률",
    "PROGRESS_WORK_PRODUCT": "산출물 제출률",
}


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _measure(cur: Any, principal: AuthPrincipal, project_id: str, key: str) -> Any:
    """사업 하나의 지표 값. 화면·질의와 같은 시맨틱 레이어 값이다(절대 규칙 1). 없으면 None."""
    spec = WidgetSpec(
        template="STAT_CARD", title=key,
        query=WidgetQuery(measure=key, dimensions=[], filters=[], projectScope=[project_id]),
    )
    try:
        # 세이브포인트 안에서 묻는다. 지표 쿼리가 실패해도 요청 트랜잭션은 살아 있어야 한다
        with cur.connection.transaction():
            data = semantic.run(cur, principal, spec)
    except Exception:  # noqa: BLE001 — 지표가 없어도 요청은 남는다. 값이 없음으로 둔다
        return None
    row = data.total or (data.rows[0] if data.rows else None)
    value = row.values.get("value") if row else None
    return float(value) if value is not None else None


def capture(
    cur: Any, principal: AuthPrincipal, project_id: str, target_type: str, target_key: str
) -> tuple[str, dict[str, Any]]:
    """대상의 (표시 이름, 상태) 를 돌려준다. 대상이 없으면 ValueError."""
    if target_type == "WORK_PRODUCT":
        row = fetch_one(
            cur,
            """
            select type, title, version, status, submitted_at, approved_at, file_uri
              from work_product
             where project_id = %s and type = %s and is_current
            """,
            (project_id, target_key),
        )
        if row is None:
            raise ValueError("산출물 항목을 찾을 수 없습니다.")
        label = work_product_type.display_name(row["type"])
        return label, {
            "status": row["status"],
            "version": row["version"],
            "title": row["title"],
            "submitted_at": _iso(row["submitted_at"]),
            "approved_at": _iso(row["approved_at"]),
            "file_uri": row["file_uri"],
        }

    if target_type == "ISSUE":
        row = fetch_one(
            cur,
            """
            select issue_key, title, status, severity, source_priority, assignee, resolved_at
              from issue where project_id = %s and id = %s
            """,
            (project_id, target_key),
        )
        if row is None:
            raise ValueError("이슈를 찾을 수 없습니다.")
        # 관련 지표는 그 시점의 사업 값이다. 보고 때 다시 떠서 변화를 보인다(AC-050-2)
        return f"{row['issue_key'] or ''} {row['title']}".strip(), {
            "status": row["status"],
            "severity": row["severity"],
            "source_priority": row["source_priority"],
            "assignee": row["assignee"],
            "resolved_at": _iso(row["resolved_at"]),
            "issue_resolution_rate": _measure(
                cur, principal, project_id, "issue_resolution_rate"
            ),
        }

    if target_type == "RISK":
        row = fetch_one(
            cur,
            """
            select title, status, severity, owner, closed_at
              from risk where project_id = %s and id = %s
            """,
            (project_id, target_key),
        )
        if row is None:
            raise ValueError("리스크를 찾을 수 없습니다.")
        return row["title"], {
            "status": row["status"],
            "severity": row["severity"],
            "owner": row["owner"],
            "closed_at": _iso(row["closed_at"]),
            "risk_resolution_rate": _measure(cur, principal, project_id, "risk_resolution_rate"),
            "open_risk_count": _measure(cur, principal, project_id, "open_risk_count"),
        }

    if target_type == "WBS_ITEM":
        rows = dashboard_service.current_wbs_rows(cur, project_id)
        match = next((r for r in rows if r.wbs_id == target_key), None)
        if match is None:
            raise ValueError("WBS 항목을 찾을 수 없습니다.")
        # 근거는 지금 다시 대조한다(저장하지 않음). 저장된 판정은 화면을 연 때의 것이라 낡을
        # 수 있다. 파일 대조·정식 제출·승인은 서로 다른 사실이다. 산출물 항목에 닿지 못하면
        # 제출·승인은 UNKNOWN 으로 남긴다(completion.facts_from)
        check = dashboard_service.judge_deliverables(cur, project_id, clock.today())
        judged = next((j for j in check.judgements if j.wbs_id == target_key), None)
        facts = completion.facts_from(cur, judged, check.tree_sha)
        item = completion.current_item(cur, project_id, wbs_id=target_key)
        # 연결 이슈는 일정 화면과 같은 규칙(ARC-016 3-4)으로, 보고 진척률은 현황 화면 값이다
        linked = dashboard_service.linked_issues_by_ids(
            cur, project_id, {r.wbs_id for r in rows if r.wbs_id}
        ).get(target_key, [])
        progress = dashboard_service.project_progress(cur, principal, project_id)
        return f"{match.wbs_id} {match.name.strip()}", {
            "actual": match.actual,
            "declared_planned": match.declared_planned,
            "deliverable": match.deliverable,
            "weight": float(item["weight"]) if item else None,
            "file_check": facts["file_check"],
            "file_rule": facts["file_rule"],
            "file_ref": facts["file_ref"],
            "repo_revision": facts["repo_revision"],
            "submission": facts["submission"],
            "approval": facts["approval"],
            "product_version": facts["product_version"],
            "plan_version": item["plan_version"] if item else None,
            "task_key": str(item["task_key"]) if item else None,
            "scope_hash": item["scope_hash"] if item else None,
            "end": _iso(match.end),
            "linked_issues": [f"{i.key} {i.status}" for i in linked],
            "progress_representative": progress.representative,
            "progress_level": progress.level,
        }

    if target_type == "METRIC":
        if target_key not in METRIC_KEYS:
            raise ValueError("지표 종류가 아닙니다.")
        progress = dashboard_service.project_progress(cur, principal, project_id)
        if target_key == "REPRESENTATIVE":
            return METRIC_KEYS[target_key], {
                "value": progress.representative,
                "level": progress.level,
                "basis": progress.basis,
            }
        measure = {
            "PROGRESS_WBS": progress.wbs,
            "PROGRESS_ISSUE": progress.issue,
            "PROGRESS_WORK_PRODUCT": progress.workProduct,
        }[target_key]
        return METRIC_KEYS[target_key], {
            "value": measure.value,
            "numerator": measure.numerator,
            "denominator": measure.denominator,
        }

    raise ValueError(f"지원하지 않는 대상 종류입니다: {target_type}")


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[ReviewStateChange]:
    """요청 시점과 지금의 차이. 같은 값은 내지 않는다. 순서는 FIELD_LABELS 순서다."""
    keys = [k for k in FIELD_LABELS if k in before or k in after]
    keys += [k for k in sorted(set(before) | set(after)) if k not in keys]
    return [
        ReviewStateChange(
            field=k, label=FIELD_LABELS.get(k, k), before=before.get(k), after=after.get(k)
        )
        for k in keys
        if before.get(k) != after.get(k)
    ]


def targets(
    cur: Any, project_id: str, target_type: str
) -> list[ReviewTargetOption]:
    """요청을 걸 수 있는 대상 목록. 화면의 고르기 상자가 이걸 그린다."""
    if target_type == "WORK_PRODUCT":
        rows = fetch_all(
            cur,
            """
            select type, status, version from work_product
             where project_id = %s and is_current and applicable
             order by pm_activity nulls last, si_activity nulls last, type
            """,
            (project_id,),
        )
        return [
            ReviewTargetOption(
                key=r["type"],
                label=f"{work_product_type.display_name(r['type'])} ({r['status']}"
                + (f" · v{r['version']}" if r["version"] and r["version"] != "0" else "")
                + ")",
            )
            for r in rows
        ]
    if target_type == "ISSUE":
        rows = fetch_all(
            cur,
            """
            select id, issue_key, title, status from issue where project_id = %s
             order by (status in ('RESOLVED', 'CLOSED')), source_updated_at desc nulls last
             limit 300
            """,
            (project_id,),
        )
        return [
            ReviewTargetOption(
                key=str(r["id"]),
                label=f"{r['issue_key'] or ''} {r['title']} ({r['status']})".strip(),
            )
            for r in rows
        ]
    if target_type == "RISK":
        rows = fetch_all(
            cur,
            "select id, title, status from risk where project_id = %s"
            " order by (status = 'CLOSED'), created_at desc limit 300",
            (project_id,),
        )
        return [
            ReviewTargetOption(key=str(r["id"]), label=f"{r['title']} ({r['status']})")
            for r in rows
        ]
    if target_type == "WBS_ITEM":
        return [
            ReviewTargetOption(key=r.wbs_id, label=f"{r.wbs_id} {r.name.strip()}")
            for r in dashboard_service.current_wbs_rows(cur, project_id)
        ]
    if target_type == "METRIC":
        return [ReviewTargetOption(key=k, label=v) for k, v in METRIC_KEYS.items()]
    return []
