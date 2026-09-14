"""확인 요청 대상의 상태를 그 시점 그대로 떠 둔다 (SWFR.WEB.004).

대상은 다섯 종류다. WBS 항목·산출물·이슈·리스크·지표. 종류마다 "상태"라 부를 만한
값이 다르므로 종류별로 뽑는 값을 여기서 정한다. 값은 전부 DB 나 WBS 파일에서 읽은
것이고, 지표는 진척 집계 결과다. 사람이 적거나 모델이 만든 값은 없다.

보고·확인 시점에는 같은 함수를 다시 불러 "그때"와 "지금"을 나란히 놓는다(SWFR.WEB.005).
"""

from typing import Any

from app.auth.models import AuthPrincipal
from app.dashboard import service as dashboard_service
from app.db import fetch_all, fetch_one
from app.review.models import ReviewStateChange, ReviewTargetOption
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
    "end": "종료일",
    "value": "값",
    "numerator": "분자",
    "denominator": "분모",
    "level": "산정 수준",
    "basis": "근거",
}

METRIC_KEYS = {
    "REPRESENTATIVE": "대표 진척률",
    "PROGRESS_WBS": "WBS 기반 진척률",
    "PROGRESS_ISSUE": "이슈 해결률",
    "PROGRESS_WORK_PRODUCT": "산출물 제출률",
}


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


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
            select issue_key, title, status, severity, assignee, resolved_at
              from issue where project_id = %s and id = %s
            """,
            (project_id, target_key),
        )
        if row is None:
            raise ValueError("이슈를 찾을 수 없습니다.")
        return f"{row['issue_key'] or ''} {row['title']}".strip(), {
            "status": row["status"],
            "severity": row["severity"],
            "assignee": row["assignee"],
            "resolved_at": _iso(row["resolved_at"]),
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
        }

    if target_type == "WBS_ITEM":
        rows = dashboard_service.current_wbs_rows(cur, project_id)
        match = next((r for r in rows if r.wbs_id == target_key), None)
        if match is None:
            raise ValueError("WBS 항목을 찾을 수 없습니다.")
        return f"{match.wbs_id} {match.name.strip()}", {
            "actual": match.actual,
            "declared_planned": match.declared_planned,
            "deliverable": match.deliverable,
            "end": _iso(match.end),
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
