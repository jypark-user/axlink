"""일별 스냅샷 (SWFR.PIP.005). 진척·일정·품질·산출물 핵심 지표를 하루 한 줄로 남긴다.

추이는 지금 값을 세어서는 나오지 않는다. 오늘 세어 둔 값이 내일의 추이가 된다.
같은 날 두 번 찍으면 나중 값이 이긴다. 수집이 더 들어온 뒤의 값이 그날의 사실이다.

서버 안 스케줄러(app/scheduler.py)가 사업별 설정 시각에 매일 찍는다. 수동 트리거
(POST /projects/{id}/snapshots)는 그대로 두어 시연·점검 때 바로 찍을 수 있다.

손으로 찍는 것은 발주기관 담당자와 관리자만, 사업 기준 오늘 날짜만 된다(점검 SNAP-01).
스냅샷은 찍는 순간의 값을 센다. 과거 날짜로 찍으면 지금 값이 그날 값처럼 남아 추이가 거짓이
된다. 과거 정정 경로는 두지 않았다. 필요하면 정정 사유와 이전 값을 남기는 경로를 따로 만든다.
"""

from datetime import date
from typing import Any

from app.activity import service as activity
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import clock, errors
from app.dashboard import service as progress_service
from app.dashboard.models import ProgressSnapshotResponse
from app.db import fetch_all, fetch_one


def take(
    cur: Any, principal: AuthPrincipal, project_id: str, at: date | None = None
) -> ProgressSnapshotResponse:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    if principal.role not in ("CLIENT", "SUPER_ADMIN"):
        raise errors.ApiError(403, "FORBIDDEN", "발주기관 담당자만 스냅샷을 기록할 수 있습니다.")
    today = clock.today()
    if at is not None and at != today:
        raise errors.validation_failed(
            f"스냅샷은 오늘({today.isoformat()}) 날짜로만 기록합니다. "
            "지금 값을 다른 날짜에 남기면 그날 값처럼 보입니다."
        )
    return take_unchecked(cur, project_id, today, actor=principal)


def list_recent(
    cur: Any, principal: AuthPrincipal, project_id: str, limit: int = 90
) -> list[ProgressSnapshotResponse]:
    """스냅샷 화면. 최근 것이 앞이다. 값이 어떻게 움직였는지 이 줄들만 봐도 읽히게 한다."""
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    rows = fetch_all(
        cur,
        """
        select * from progress_snapshot
         where project_id = %s
         order by snapshot_date desc
         limit %s
        """,
        (project_id, limit),
    )
    return [_response(r) for r in rows]


def take_unchecked(
    cur: Any, project_id: str, at: date, actor: AuthPrincipal | None = None
) -> ProgressSnapshotResponse:
    """접근 검사 없이 찍는다. 배치가 전 사업을 돌 때 쓴다. actor 가 없으면 스케줄러가 찍은 것이다.

    찍은 사실은 활동에 남긴다(알림은 안 간다). 언제 어떤 값이 기록됐는지가 곧 진척 보고의
    이력이고, "지난 보고 이후" 를 셀 때 이 줄이 기준점이 된다.
    """
    progress = progress_service.compute(cur, project_id, at)
    counts = fetch_one(
        cur,
        """
        select
          (select count(*) from requirement where project_id = %(p)s
             and status in ('VERIFIED', 'ACCEPTED'))             as requirement_verified,
          (select count(*) from requirement where project_id = %(p)s) as requirement_total,
          (select count(*) from risk where project_id = %(p)s
             and status = 'CLOSED')                               as risk_closed,
          (select count(*) from risk where project_id = %(p)s)    as risk_total,
          (select count(*) from work_product where project_id = %(p)s
             and is_current and applicable and status = 'APPROVED') as work_product_approved
        """,
        {"p": project_id},
    )
    row = fetch_one(
        cur,
        """
        insert into progress_snapshot (
          project_id, snapshot_date, level, representative_pct, wbs_actual_pct, wbs_planned_pct,
          behind_task_count, issue_resolved_count, issue_total_count,
          requirement_verified_count, requirement_total_count, risk_closed_count, risk_total_count,
          work_product_submitted_count, work_product_approved_count, work_product_total_count,
          defect_resolved_count, defect_total_count)
        values (%(project_id)s, %(snapshot_date)s, %(level)s, %(representative)s, %(wbs_actual)s,
                %(wbs_planned)s, %(behind)s, %(issue_resolved)s, %(issue_total)s,
                %(req_verified)s, %(req_total)s, %(risk_closed)s, %(risk_total)s,
                %(wp_submitted)s, %(wp_approved)s, %(wp_total)s,
                %(defect_resolved)s, %(defect_total)s)
        on conflict (project_id, snapshot_date) do update set
          level = excluded.level,
          representative_pct = excluded.representative_pct,
          wbs_actual_pct = excluded.wbs_actual_pct,
          wbs_planned_pct = excluded.wbs_planned_pct,
          behind_task_count = excluded.behind_task_count,
          issue_resolved_count = excluded.issue_resolved_count,
          issue_total_count = excluded.issue_total_count,
          requirement_verified_count = excluded.requirement_verified_count,
          requirement_total_count = excluded.requirement_total_count,
          risk_closed_count = excluded.risk_closed_count,
          risk_total_count = excluded.risk_total_count,
          work_product_submitted_count = excluded.work_product_submitted_count,
          work_product_approved_count = excluded.work_product_approved_count,
          work_product_total_count = excluded.work_product_total_count,
          defect_resolved_count = excluded.defect_resolved_count,
          defect_total_count = excluded.defect_total_count,
          created_at = now()
        returning *
        """,
        {
            "project_id": project_id,
            "snapshot_date": at,
            "level": progress.level,
            "representative": _pct(progress.representative),
            "wbs_actual": _pct(progress.wbs.value),
            "wbs_planned": _pct(progress.wbsPlanned),
            "behind": len(progress.behind),
            "issue_resolved": progress.issue.numerator or 0,
            "issue_total": progress.issue.denominator or 0,
            "req_verified": int(counts["requirement_verified"]),
            "req_total": int(counts["requirement_total"]),
            "risk_closed": int(counts["risk_closed"]),
            "risk_total": int(counts["risk_total"]),
            "wp_submitted": progress.workProduct.numerator or 0,
            "wp_approved": int(counts["work_product_approved"]),
            "wp_total": progress.workProduct.denominator or 0,
            # 결함 매핑이 없으면 비운다. 0 으로 두면 「결함 0건」과 구분되지 않는다(DEC-02)
            "defect_resolved": None if progress.defect is None else progress.defect.numerator,
            "defect_total": None if progress.defect is None else progress.defect.denominator,
        },
    )
    _record(cur, project_id, row, actor)
    return _response(row)


def _pct(ratio: float | None) -> float | None:
    """진척 서비스는 0~1 비율, 스냅샷과 카탈로그는 0~100 퍼센트다."""
    return None if ratio is None else round(ratio * 100, 2)


def _response(row: dict[str, Any]) -> ProgressSnapshotResponse:
    return ProgressSnapshotResponse(
        projectId=str(row["project_id"]),
        snapshotDate=row["snapshot_date"].isoformat(),
        level=row["level"],
        representativePct=_num(row["representative_pct"]),
        wbsActualPct=_num(row["wbs_actual_pct"]),
        wbsPlannedPct=_num(row["wbs_planned_pct"]),
        behindTaskCount=row["behind_task_count"],
        issueResolvedCount=row["issue_resolved_count"],
        issueTotalCount=row["issue_total_count"],
        defectResolvedCount=row.get("defect_resolved_count"),
        defectTotalCount=row.get("defect_total_count"),
        requirementVerifiedCount=row["requirement_verified_count"],
        requirementTotalCount=row["requirement_total_count"],
        riskClosedCount=row["risk_closed_count"],
        riskTotalCount=row["risk_total_count"],
        workProductSubmittedCount=row["work_product_submitted_count"],
        workProductApprovedCount=row["work_product_approved_count"],
        workProductTotalCount=row["work_product_total_count"],
        createdAt=row["created_at"].isoformat(),
    )


def _record(cur: Any, project_id: str, row: dict[str, Any], actor: AuthPrincipal | None) -> None:
    rep = _num(row["representative_pct"])
    planned = _num(row["wbs_planned_pct"])
    parts = [f"진척 {rep:.1f}%" if rep is not None else "진척 없음"]
    if planned is not None:
        parts.append(f"계획 {planned:.1f}%")
    parts.append(f"지연 {row['behind_task_count'] or 0}건")
    activity.record(
        cur, project_id=project_id, kind=activity.SNAPSHOT_TAKEN, audience=activity.LOG,
        summary=f"일별 스냅샷 기록 {row['snapshot_date'].isoformat()}: " + " · ".join(parts),
        actor=actor, actor_label=None if actor else "스케줄러",
        target_type="SNAPSHOT", target_key=row["snapshot_date"].isoformat(),
        detail={
            "representativePct": rep, "wbsPlannedPct": planned,
            "behindTaskCount": row["behind_task_count"], "level": row["level"],
        },
    )


def _num(value: Any) -> float | None:
    return None if value is None else float(value)
