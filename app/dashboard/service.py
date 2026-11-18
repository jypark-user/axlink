"""진척 산정 (SWFR.PIP.010).

진척을 **세 갈래로 따로 낸다.** 하나로 합치지 않는 이유가 이 모듈의 요점이다.

| 갈래 | 성격 | 조작 난이도 |
|---|---|---|
| WBS 기반 | 자기신고 — 업체가 실적 칸에 적은 값 | 쉽다 |
| 이슈 해결률 | 관측 — 도구에 남은 상태 | 중간 |
| 산출물 제출률 | 관측 — 파일이 실제로 올라와 있는가 | 어렵다 |

**셋의 격차 자체가 신호다.** 신고는 80% 인데 산출물이 10% 면 그 간극이 감독이 봐야 할
지점이다. 착수보고서가 말한 *"보고 시점에 의존하는 사후적 방식"* 을 벗어나는 실체가 이것이다.

대표값은 진척률-산정체계 §1 의 L1~L4 저하 순서를 따른다 — WBS 가 완비되면 WBS 를 쓰고,
없으면 이슈로, 그것도 없으면 산출물로 내려간다. 대표값 하나만 보이면 자기신고가 관측을
가리므로 **화면에는 셋을 함께 낸다**(절대 규칙 1 — 수치는 전부 이 집계에서만 나온다).
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.activity import service as activity
from app.auth import repository as auth_repo
from app.auth.deps import AuthPrincipal
from app.common import clock, errors
from app.config import settings
from app.dashboard import deliverable, designation, repository, wbs, wbs_issue
from app.dashboard.models import (
    OBSERVED,
    SELF_REPORTED,
    WBS_SOURCE_FILE,
    WBS_SOURCE_NONE,
    WBS_SOURCE_REDMINE,
    DeliverableReview,
    DeliverableSummary,
    DesignatedDeliverable,
    LinkedIssue,
    ProgressMeasure,
    ProgressResponse,
    WbsDeliverableDocument,
    WbsDeliverableItem,
    WbsDeliverablesResponse,
    WbsItemResponse,
    WbsRecognitionColumn,
    WbsRecognitionResponse,
    WbsScheduleResponse,
    WbsSourceFile,
)
from app.db import fetch_all, fetch_one
from app.integration import repository as integration_repo
from app.standard import repository as standard_repo
from app.standard import wbs_repository

# WBS 가 들어오는 산출물 항목. 저장소에 커밋된 계획 파일이 여기로 승격된다.
PLAN_TYPE = "PROJECT_PLAN"

_NONE = "NONE"
# L3 대표값의 근거 코드(DEC-17). 옛 L3(일반 이슈 해결률) 기록은 "ISSUE" 로 남아 있다
ISSUE_PROGRESS = "ISSUE_PROGRESS"


def require_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def project_progress(
    cur: Any, principal: AuthPrincipal, project_id: str, at: date | None = None
) -> ProgressResponse:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    return compute(cur, project_id, at or clock.today())


def _issue_note(issue_total: int, defect_mapped: bool) -> str:
    """일반 이슈 해결률의 범위. 결함 매핑이 없으면 결함을 가르지 못한 것까지 적는다(DEC-02)."""
    if not issue_total:
        return "연동된 일반 이슈가 없습니다"
    return _issue_scope(defect_mapped)


def _issue_scope(defect_mapped: bool) -> str:
    if defect_mapped:
        return "리스크·결함·예전에 요구사항으로 만든 이슈 제외"
    return (
        "리스크·예전에 요구사항으로 만든 이슈 제외. 결함 매핑이 없어 수집한 이슈 전부를 "
        "일반 이슈로 셉니다"
    )


ISSUE_ESTIMATE_LABEL = "이슈 기반 추정 진척률"


def issue_estimate_measure(
    done_sum: float, total: int, reported: int, defect_mapped: bool
) -> ProgressMeasure:
    """이슈 기반 추정 진척률(DEC-17). 대상 이슈마다 같은 가중치로 진척도를 평균한다.

    진척도가 없는 이슈는 0 으로 세고 그 건수를 남긴다. 마일스톤별 평균을 이슈 수 비례로 다시
    평균한 값과 같으므로 버전 없는(미배정) 이슈를 따로 묶어도 값은 같다. 대상 이슈가 없거나
    모든 이슈의 진척도가 없으면 산출 불가다. 일반 이슈 해결률(issue)과는 다른 지표다.
    """
    missing = total - reported
    if not total:
        value, note = None, "산출 불가: 대상 일반 이슈가 없습니다"
    elif not reported:
        value = None
        note = f"산출 불가: 대상 일반 이슈 {total}건 모두 진척도가 없습니다"
    else:
        value = round(done_sum / 100.0 / total, 4)
        note = (
            f"대상 일반 이슈 {total}건({_issue_scope(defect_mapped)})의 진척도를 같은 가중치로 "
            f"평균했습니다. 진척도가 없는 이슈는 0으로 셉니다(결측 {missing}건)"
        )
    return ProgressMeasure(
        value=value,
        numerator=None,
        denominator=total,
        label=ISSUE_ESTIMATE_LABEL,
        unit="이슈 진척도 평균",
        kind=SELF_REPORTED,
        note=note,
        missing=missing if total else None,
    )


def _defect_note(defect_total: int, defect_mapped: bool) -> str | None:
    if not defect_mapped:
        return (
            "산출 불가: 연결 설정에 결함 트래커(Redmine)·결함 라벨(GitHub)이 없어 결함을 "
            "가를 수 없습니다"
        )
    if not defect_total:
        return "산출 불가: 결함으로 분류된 이슈가 없습니다"
    return "결함 트래커·결함 라벨로 분류한 이슈만 셉니다. 일반 이슈에는 들지 않습니다"


def compute(cur: Any, project_id: str, at: date) -> ProgressResponse:
    """접근 검사 없는 산정. 화면(위)과 일별 스냅샷이 같은 함수를 쓴다."""
    warnings: list[str] = []

    plan_row = standard_repo.current_work_product(cur, project_id, PLAN_TYPE)
    wbs_progress, plan_warning = _read_plan(cur, project_id, plan_row, at)
    if plan_warning:
        warnings.append(plan_warning)
    if wbs_progress is not None:
        warnings.extend(wbs_progress.warnings)

    issue_done, issue_total = repository.issue_resolution(cur, project_id)
    done_sum, estimate_total, reported = repository.issue_progress(cur, project_id)
    defect_mapped = repository.defect_mapped(cur, project_id)
    defect_done, defect_total = repository.defect_resolution(cur, project_id)
    product_done, product_total = repository.work_product_submission(cur, project_id)

    wbs_measure = ProgressMeasure(
        value=None if wbs_progress is None else wbs_progress.actual,
        numerator=None,
        denominator=None if wbs_progress is None else wbs_progress.leaf_count,
        label="WBS 기반 진척률" + (" (추정)" if wbs_progress and wbs_progress.estimated else ""),
        unit="말단 작업 가중합",
        kind=SELF_REPORTED,
        note=_wbs_note(wbs_progress),
    )
    issue_measure = ProgressMeasure(
        value=_ratio(issue_done, issue_total),
        numerator=issue_done,
        denominator=issue_total,
        label="일반 이슈 해결률",
        unit="건",
        kind=OBSERVED,
        # 출처 이슈(예전에 요구사항으로 만든 이슈)와 리스크·결함은 분모에 없다. 범위를 같이 보인다
        note=_issue_note(issue_total, defect_mapped),
    )
    estimate_measure = issue_estimate_measure(done_sum, estimate_total, reported, defect_mapped)
    defect_measure = ProgressMeasure(
        value=_ratio(defect_done, defect_total) if defect_mapped else None,
        numerator=defect_done if defect_mapped else None,
        denominator=defect_total if defect_mapped else None,
        label="결함 처리율",
        unit="건",
        kind=OBSERVED,
        note=_defect_note(defect_total, defect_mapped),
    )
    product_measure = ProgressMeasure(
        value=_ratio(product_done, product_total),
        numerator=product_done,
        denominator=product_total,
        label="산출물 제출률",
        unit="건",
        kind=OBSERVED,
        note=None if product_total else "산출물 목록이 아직 만들어지지 않았다",
    )

    level, basis, representative = _representative(
        wbs_progress, estimate_measure, product_measure
    )
    note = _basis_note(level, wbs_progress, issue_measure, product_measure, estimate_measure)
    if level != "L1" or representative is None:
        # 대표값이 WBS 실적이 아니거나 산출 불가다. 경고 줄에도 같은 문장을 둔다(DEF-V037)
        warnings.append(note)
    shown_row = _shown_plan_row(cur, project_id, plan_row) if wbs_progress else plan_row
    warnings.extend(_gap_warnings(wbs_progress, issue_measure, product_measure))
    achieved, evaluated = repository.schedule_compliance(cur, [project_id], at).get(
        project_id, (0, 0)
    )
    approved, defined = deliverable_approval_now(cur, project_id, at)

    return ProgressResponse(
        baseDate=at.isoformat(),
        level=level,
        representative=representative,
        basis=basis,
        gap=_gap(wbs_measure, issue_measure, product_measure),
        wbs=wbs_measure,
        wbsPlanned=None if wbs_progress is None else wbs_progress.planned,
        wbsDeviation=None if wbs_progress is None else wbs_progress.deviation,
        wbsDeclaredPlanned=None if wbs_progress is None else wbs_progress.declared_planned,
        issue=issue_measure,
        issueEstimate=estimate_measure,
        workProduct=product_measure,
        defect=defect_measure,
        behind=[] if wbs_progress is None else wbs_progress.behind,
        delayed=[] if wbs_progress is None else wbs_progress.delayed,
        warnings=warnings,
        planVersion=None if shown_row is None else shown_row["version"],
        planUpdatedAt=None if shown_row is None else shown_row["updated_at"].isoformat(),
        estimated=level != "L1" and representative is not None,
        basisNote=note,
        scheduleCompliance=schedule_compliance_measure(achieved, evaluated),
        deliverableApproval=deliverable_approval_measure(approved, defined),
    )


SCHEDULE_COMPLIANCE_BASIS = (
    "기한이 기준일보다 앞선 마일스톤 중 기한 안에 닫힌 비율. 기한 없는 마일스톤과 기한 전 "
    "마일스톤은 세지 않는다"
)
DELIVERABLE_APPROVAL_BASIS = "WBS 가 정한 산출물 중 현행 버전이 승인된 비율"


def schedule_compliance_measure(achieved: int, evaluated: int) -> ProgressMeasure:
    """일정 준수율(DEC-01). 계획선 편차와 다른 지표다. 평가 대상이 없으면 산출 불가."""
    return ProgressMeasure(
        value=_ratio(achieved, evaluated),
        numerator=achieved,
        denominator=evaluated,
        label="일정 준수율",
        unit="마일스톤",
        kind=OBSERVED,
        note=SCHEDULE_COMPLIANCE_BASIS
        if evaluated
        else "산출 불가: 기한이 지난 마일스톤이 없습니다",
    )


def deliverable_approval_measure(approved: int, defined: int) -> ProgressMeasure:
    """산출물 승인률(DEC-12). 분모는 WBS 가 정한 산출물이다. WBS 가 없으면 산출 불가."""
    return ProgressMeasure(
        value=_ratio(approved, defined),
        numerator=approved,
        denominator=defined,
        label="산출물 승인률",
        unit="건",
        kind=OBSERVED,
        note=DELIVERABLE_APPROVAL_BASIS
        if defined
        else "산출 불가: WBS 가 정한 산출물이 없습니다",
    )


def deliverable_approval_now(cur: Any, project_id: str, at: date) -> tuple[int, int]:
    """산출물 승인 수(DEC-12): (현행 버전이 승인된 수, WBS 가 정한 산출물 수). 읽기만 한다.

    판정을 지금 다시 해서(저장하지 않음) 문서를 붙이거나 산출물을 확정한 직후에도 맞는다.
    진척 산정은 스냅샷·확인 요청 상태 뜨기에도 쓰이므로 판정 저장·활동 기록을 남기면 안 된다.
    분모·분자 조건은 시맨틱 지표 deliverable_approval_rate(V64)와 같다. 지표는 일정·산출물 화면이
    남긴 판정(wbs_item.deliverable_product_id)을 읽는다.
    """
    check = judge_deliverables(cur, project_id, at)
    leaves = {
        i["wbs_id"] for i in check.items
        if i.get("weight") is not None and (i.get("deliverable") or "").strip()
    }
    judged = [j for j in check.judgements if j.wbs_id in leaves]
    status = repository.current_status_by_product(
        cur, [j.product_id for j in judged if j.product_id]
    )
    approved = sum(1 for j in judged if j.product_id and status.get(j.product_id) == "APPROVED")
    return approved, len(leaves)


def sync_product_links(cur: Any, project_id: str, at: date | None = None) -> None:
    """판정이 맞춘 산출물 항목만 wbs_item 에 맞춘다(시맨틱 지표 deliverable_approval_rate 의 재료).

    산출물 항목이 생기거나 문서가 작업에 붙는 쓰기 요청(문서 올리기·초안 확정·수집)이 부른다.
    진척 산정(compute)·상태 뜨기 같은 읽기 경로에서는 부르지 않는다. 읽기 경로가 wbs_item 에
    쓰면 그 트랜잭션이 끝날 때까지 행 잠금이 남아, 같은 행을 갱신하는 일정 화면 요청이 기다린다
    (5174 원격 시험의 GET /wbs 시간 초과). 판정 상태·판정 시각·활동 기록은 건드리지 않는다.
    """
    check = judge_deliverables(cur, project_id, at or clock.today())
    wbs_repository.save_product_links(
        cur, project_id, [(j.wbs_id, j.product_id) for j in check.judgements]
    )


def _wbs_note(wbs_progress: wbs.WbsProgress | None) -> str | None:
    if wbs_progress is None:
        return "WBS 파일이 수집되지 않았다. 저장소에 커밋하면 자동으로 잡힌다"
    if wbs_progress.unavailable:
        return "산출 불가: " + " / ".join(wbs_progress.unavailable)
    if wbs_progress.estimated:
        return "추정: 가중치 미지정, 계획 기간 비례 가중치 × 파일 실적"
    return None


def _basis_note(
    level: str,
    wbs_progress: wbs.WbsProgress | None,
    issue: ProgressMeasure,
    product: ProgressMeasure,
    estimate: ProgressMeasure,
) -> str:
    """대표값의 산출 근거 한 문장. 값은 넣지 않는다(분자·분모 건수만). 수치는 응답 필드가 낸다."""
    if level == "L1":
        assert wbs_progress is not None
        if wbs_progress.unavailable:
            return "산출 불가: " + " / ".join(wbs_progress.unavailable)
        return (
            f"WBS 말단 작업 {wbs_progress.leaf_count}건의 가중치 × 실적 합입니다. "
            "실적은 용역사가 계획서에 적은 값입니다."
        )
    if level == "L2":
        assert wbs_progress is not None
        if wbs_progress.unavailable:
            return (
                "산출 불가: WBS 에 가중치가 없어 계획 기간 비례로 추정해야 하는데 재료가 "
                "모자랍니다. " + " / ".join(wbs_progress.unavailable)
            )
        return (
            f"추정: WBS 에 가중치가 없어 말단 작업 {wbs_progress.leaf_count}건의 계획 기간"
            "(시작일~종료일)에 비례한 가중치 × 파일의 실적으로 산정했습니다. 산출물 제출 여부로 "
            "실적을 대신하지 않습니다."
        )
    if level == "L3":
        # DEC-17. 해결률은 대표값이 아니라 별도 지표로 남는다
        if estimate.value is None:
            return (
                f"산출 불가: WBS 가 없고 대상 일반 이슈 {estimate.denominator}건 모두 진척도가 "
                f"없어 {ISSUE_ESTIMATE_LABEL}을 낼 수 없습니다. 일반 이슈 해결률(해결 "
                f"{issue.numerator} / 전체 {issue.denominator}건)은 별도 지표로 봅니다."
            )
        return (
            f"추정: WBS 가 없어 {ISSUE_ESTIMATE_LABEL}로 산정했습니다. 대상 일반 이슈 "
            f"{estimate.denominator}건의 진척도를 같은 가중치로 평균했고, 진척도가 없는 "
            f"{estimate.missing}건은 0으로 셌습니다. WBS 실적 기준(L1)이 아닙니다. 일반 이슈 "
            "해결률은 별도 지표입니다. WBS 를 등록하면 작업 단위 진척률과 실적 대조가 됩니다."
        )
    if level == "L4":
        return (
            f"추정: WBS 와 이슈가 없어 산출물 제출률(제출 {product.numerator} / 적용 대상 "
            f"{product.denominator}건)로 산정했습니다. WBS 실적 기준(L1)이 아닙니다. WBS 를 "
            "등록하면 산출됩니다."
        )
    return "산출 불가: WBS·이슈 진척·산출물 제출본이 없어 진척률을 산정할 근거가 없습니다."


# ---------------------------------------------------------------- 일정 (WBS)

_NO_WBS_NOTICE = (
    "일정과 진척률 산정의 핵심 입력인 WBS 가 없습니다. 용역사의 WBS 파일(사업수행계획서)을 "
    "저장소에 두거나 산출물로 올리거나, Redmine 이슈에 시작일·종료일을 채우면 여기에 나타납니다. "
    "그전까지 진척률은 이슈·산출물 기준의 추정치입니다."
)


def wbs_schedule(
    cur: Any, principal: AuthPrincipal, project_id: str, at: date | None = None
) -> WbsScheduleResponse:
    """일정 화면의 작업 줄. 표준 산출물 목록으로 흉내 내지 않는다 — 실제 WBS 가 있으면
    그것, 없으면 Redmine 이슈의 일정, 둘 다 없으면 빈 목록과 고지문이다."""
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    return schedule(cur, project_id, at or clock.today())


def schedule(cur: Any, project_id: str, at: date) -> WbsScheduleResponse:
    warnings: list[str] = []
    plan_row = standard_repo.current_work_product(cur, project_id, PLAN_TYPE)
    plan, plan_warning = _load_plan(cur, project_id, plan_row)
    if plan_warning:
        warnings.append(plan_warning)
    if plan is not None:
        assert plan_row is not None
        plan_row = _shown_plan_row(cur, project_id, plan_row) or plan_row
        judged = refresh_deliverables(cur, project_id, at)
        counts = deliverable.summarize(list(judged.values()))
        items = _items_from_plan(plan, at, judged, linked_issues(cur, project_id, plan))
        gaps = [f"격차 경고: {i.wbsId} {i.name} — {i.gapWarning}" for i in items if i.gapWarning]
        return WbsScheduleResponse(
            source=WBS_SOURCE_FILE,
            sourceLabel=f"용역사 WBS ({plan_row.get('file_uri') or '사업수행계획서'})",
            sourceUrl=plan_row.get("external_url"),
            baseDate=at.isoformat(),
            planVersion=plan_row["version"],
            planUpdatedAt=plan_row["updated_at"].isoformat(),
            items=items,
            warnings=[*warnings, *plan.warnings, *gaps],
            notice=None,
            deliverables=DeliverableSummary(
                submitted=counts[deliverable.SUBMITTED],
                missing=counts[deliverable.MISSING],
                overdue=counts[deliverable.OVERDUE],
                none=counts[deliverable.NONE],
            ),
            recognition=_recognition(cur, project_id, plan),
            sourceFile=_source_file(cur, plan_row),
        )

    issues = integration_repo.redmine_issue_payloads(cur, project_id)
    items = _items_from_redmine(issues, at)
    if items:
        warnings.append(
            "WBS 파일이 없어 Redmine 이슈의 시작일·종료일을 일정으로 씁니다. 가중치가 없으므로 "
            "진척률 산정 기준(L1)으로는 쓰지 않습니다."
        )
        return WbsScheduleResponse(
            source=WBS_SOURCE_REDMINE,
            sourceLabel="Redmine 이슈 일정",
            sourceUrl=None,
            baseDate=at.isoformat(),
            planVersion=None,
            planUpdatedAt=None,
            items=items,
            warnings=warnings,
            notice=None,
        )

    return WbsScheduleResponse(
        source=WBS_SOURCE_NONE,
        sourceLabel="WBS 없음",
        sourceUrl=None,
        baseDate=at.isoformat(),
        planVersion=None,
        planUpdatedAt=None,
        items=[],
        warnings=warnings,
        notice=_NO_WBS_NOTICE,
        # 계획서를 올렸는데 못 읽었으면 그 사유를 보인다. 0건·0% 로 보이지 않는다
        recognition=_recognition(cur, project_id, None) if plan_row is not None else None,
    )


RECOGNITION_GUIDANCE = (
    "WBS 는 이 화면에서 고치지 않습니다. 열 이름·가중치·실적이 잘못 읽혔으면 원본 파일을 고쳐 "
    "저장소에 커밋하거나 사업수행계획서 새 버전으로 올리세요. 다음 수집 때 다시 읽습니다."
)


def _recognition(
    cur: Any, project_id: str, plan: wbs.WbsPlan | None
) -> WbsRecognitionResponse | None:
    """계획서 인식 결과(UC-030 3단계). 판을 읽을 때 남긴 기록을 보인다(DEC-04 (b))."""
    rec = wbs_repository.load_recognition(cur, project_id)
    if rec is None:
        if plan is None:
            return None
        # V61 전에 읽은 판: 열 매핑은 모르고 수는 행에서 센다
        total = plan.weight_total
        return WbsRecognitionResponse(
            status="OK", planVersion=None, readAt=None, headerRow=None, columns=[],
            leafCount=len(plan.rows), groupCount=len(plan.groups), weightTotal=total,
            normalized=abs(total - 1.0) > 0.005,
            missingDeliverableCount=sum(1 for r in plan.rows if not r.deliverable),
            warnings=list(plan.warnings), error=None, usingPrevious=False,
            recordedBeforeTracking=True, guidance=RECOGNITION_GUIDANCE,
        )
    total = None if rec["weight_total"] is None else float(rec["weight_total"])
    return WbsRecognitionResponse(
        status=rec["status"],
        planVersion=rec["plan_version"],
        readAt=rec["read_at"].isoformat(),
        headerRow=rec["header_row"],
        columns=[WbsRecognitionColumn(**c) for c in rec["columns_json"]],
        leafCount=rec["leaf_count"],
        groupCount=rec["group_count"],
        weightTotal=total,
        normalized=total is not None and abs(total - 1.0) > 0.005,
        missingDeliverableCount=rec["missing_deliverable_count"],
        warnings=list(rec["warnings_json"]),
        error=rec["error"],
        usingPrevious=rec["status"] == "FAILED" and plan is not None,
        guidance=RECOGNITION_GUIDANCE,
    )


def _load_plan(
    cur: Any, project_id: str, plan_row: dict[str, Any] | None
) -> tuple[wbs.WbsPlan | None, str | None]:
    """현행 계획서의 WBS. 행이 그 버전에서 왔으면 행을 읽고, 아니면 파일을 한 번 읽어 남긴다.

    파일은 계획서 버전마다 한 번만 연다(ARC-016). 그 뒤로 진척·일정·확인 요청·항목 화면이
    같은 행을 본다. 새 판을 못 읽으면 직전 판에서 읽어 둔 행을 「이전 기준선」으로 쓰고 그렇다고
    경고한다(IM-007 AC-030-3, DEF-V038). 화면이 갑자기 비는 것보다 어느 판인지 밝히고 직전 값을
    보이는 편이 낫다. 읽어 둔 행이 없으면 못 읽었다고만 한다.
    """
    if plan_row is None or _placeholder(plan_row):
        return None, None
    plan_id = str(plan_row["id"])
    if wbs_repository.loaded_version(cur, project_id) == plan_id:
        _sync_recognition(cur, project_id, plan_row, plan_id)
        return wbs_repository.load_plan(cur, project_id), None

    path = _plan_path(project_id, plan_row, cur)
    if path is None:
        return _failed(
            cur, project_id, plan_id,
            "WBS 항목은 있지만 보관된 원본 파일을 찾지 못했습니다. 다시 수집해 주세요.",
        )
    try:
        plan = wbs.parse(path.read_bytes())
    except wbs.WbsParseError as exc:
        return _failed(cur, project_id, plan_id, f"WBS 를 읽지 못했습니다. {exc}")
    except OSError as exc:
        return _failed(cur, project_id, plan_id, f"WBS 원본 파일을 열지 못했습니다. {exc}")
    wbs_repository.replace_plan(cur, project_id, plan_id, plan)
    wbs_repository.save_recognition(cur, project_id, plan_id, plan=plan)
    return plan, None


def _placeholder(plan_row: dict[str, Any]) -> bool:
    """사업을 만들 때 깔아 둔 산출물 목록 자리(DEF-V046). 아직 계획서가 없다는 뜻이다.

    create_checklist 가 유형마다 버전 '0' 행을 하나씩 만든다. 파일도 업로드도 수집 판도
    없으니 「못 읽은 계획서」가 아니라 「계획서 없음」으로 본다.
    """
    return (
        not plan_row.get("file_uri")
        and not plan_row.get("document_upload_id")
        and not plan_row.get("source_revision")
        and (plan_row.get("version") or "0") == "0"
    )


def _sync_recognition(cur: Any, project_id: str, plan_row: dict[str, Any], plan_id: str) -> None:
    """행은 이 판에서 왔는데 인식 결과가 다른 판(또는 없음)이면 이 판을 한 번 읽어 맞춘다.

    실패한 새 판 뒤에 예전 판이 현행으로 돌아오면(같은 내용 되돌림) 행은 다시 읽지 않아 인식
    결과가 「읽지 못함」으로 남는다. V61 전에 읽은 판은 기록이 없다. 둘 다 파일을 한 번 연다.
    """
    rec = wbs_repository.load_recognition(cur, project_id)
    if rec is not None and str(rec["work_product_id"]) == plan_id:
        return
    path = _plan_path(project_id, plan_row, cur)
    if path is None:
        return
    try:
        plan = wbs.parse(path.read_bytes())
    except Exception:  # noqa: BLE001 — 기록 맞추기는 보조다. 본 흐름(행 사용)을 깨지 않는다
        # 행은 이 판에서 읽어 둔 것이다. 지금 못 읽는 사정은 기록을 바꾸지 않는다
        return
    wbs_repository.save_recognition(cur, project_id, plan_id, plan=plan)


def _failed(
    cur: Any, project_id: str, plan_id: str, reason: str
) -> tuple[wbs.WbsPlan | None, str]:
    """이 판을 못 읽었다. 사유를 인식 결과로 남기고 직전 판으로 돌아간다(AC-030-3)."""
    wbs_repository.save_recognition(cur, project_id, plan_id, error=reason)
    return _previous_baseline(cur, project_id, reason)


def _previous_baseline(
    cur: Any, project_id: str, reason: str
) -> tuple[wbs.WbsPlan | None, str]:
    """현행 판을 못 읽었을 때. 직전 판에서 읽어 둔 행이 있으면 그것과 경고를 낸다."""
    loaded = wbs_repository.loaded_version(cur, project_id)
    plan = wbs_repository.load_plan(cur, project_id) if loaded else None
    if plan is None:
        return None, reason
    previous = standard_repo.work_product_row(cur, loaded)
    label = f"버전 {previous['version']}" if previous else "직전 판"
    return plan, f"{reason} 직전에 읽은 계획서({label})의 작업을 이전 기준선으로 보입니다."


def _source_file(cur: Any, plan_row: dict[str, Any]) -> WbsSourceFile:
    """계획서 행이 어디서 왔는지. 저장소에서 수집했으면 연결·경로·커밋, 올렸으면 파일 이름."""
    row = fetch_one(
        cur,
        """
        select wp.file_uri, wp.external_url, wp.source_kind, wp.source_revision, wp.version,
               wp.updated_at, tc.tool, tc.target_resource, tc.last_synced_at,
               du.original_filename
          from work_product wp
          left join tool_connection tc on tc.id = wp.tool_connection_id
          left join document_upload du on du.id = wp.document_upload_id
         where wp.id = %s
        """,
        (plan_row["id"],),
    )
    if row is None:
        row = {}
    if row.get("tool"):
        origin = "REPOSITORY"
    elif row.get("original_filename"):
        origin = "UPLOAD"
    else:
        origin = "OTHER"
    read_at = row.get("updated_at")
    synced = row.get("last_synced_at")
    return WbsSourceFile(
        origin=origin,
        path=row.get("file_uri") or row.get("original_filename"),
        url=row.get("external_url"),
        tool=row.get("tool"),
        repository=row.get("target_resource"),
        revision=row.get("source_revision") or row.get("version"),
        readAt=read_at.isoformat() if read_at else None,
        lastSyncedAt=synced.isoformat() if synced else None,
    )


def _shown_plan_row(
    cur: Any, project_id: str, plan_row: dict[str, Any] | None
) -> dict[str, Any] | None:
    """화면에 판 정보로 보일 계획서 행. 이전 기준선을 쓰고 있으면 그 직전 판이다."""
    if plan_row is None:
        return None
    loaded = wbs_repository.loaded_version(cur, project_id)
    if loaded is None or loaded == str(plan_row["id"]):
        return plan_row
    return standard_repo.work_product_row(cur, loaded) or plan_row


def _level_of(wbs_id: str) -> int:
    """'1' → 0, '1.2' → 1, '1.2.3' → 2. 번호가 없으면 말단으로 본다."""
    parts = [p for p in wbs_id.replace("-", ".").split(".") if p]
    return max(0, len(parts) - 1) if parts else 1


def _sort_key(wbs_id: str) -> tuple:
    out: list[tuple[int, int | str]] = []
    for part in wbs_id.replace("-", ".").split("."):
        out.append((0, int(part)) if part.isdigit() else (1, part))
    return tuple(out)


@dataclass(frozen=True)
class DeliverableCheck:
    """산출물 대조 한 번의 결과와 그때의 재료. 저장하지 않는다."""

    items: list[dict[str, Any]]
    judgements: list[deliverable.Judgement]
    tree_sha: str | None  # 대조에 쓴 저장소 트리. 수집 전이면 None


def judge_deliverables(cur: Any, project_id: str, at: date) -> DeliverableCheck:
    """말단 항목의 산출물을 지금 있는 파일·문서·산출물과 대조한다. 읽기만 한다.

    확인 요청 스냅샷도 이걸 부른다. 상태를 떠 두는 일이 판정 저장·활동 기록을 남기면 안 된다.
    """
    items = wbs_repository.list_items(cur, project_id)
    raw_tree = integration_repo.github_repo_tree(cur, project_id)
    tree = None
    if raw_tree and raw_tree.get("paths"):
        tree = deliverable.RepoTree(
            sha=str(raw_tree.get("sha") or ""),
            paths=frozenset(raw_tree["paths"]),
            blob_url_base=raw_tree.get("html_url"),
        )
    live = {str(i["task_key"]) for i in items if i.get("task_key") and i.get("weight") is not None}
    judgements = deliverable.judge(
        items,
        tree=tree,
        products=wbs_repository.current_products(cur, project_id),
        documents=wbs_repository.project_documents(cur, project_id),
        today=at,
        designated=designation.coverage(cur, project_id, live),
    )
    return DeliverableCheck(items, judgements, (tree.sha or None) if tree else None)


def refresh_deliverables(
    cur: Any, project_id: str, at: date
) -> dict[str, deliverable.Judgement]:
    """말단 항목의 산출물을 지금 있는 파일·문서·산출물과 대조해 행에 남긴다(ARC-016 2단계).

    조회 때마다 다시 한다. 재료(저장소 트리·문서·산출물)가 바뀌면 판정도 바뀌어야 하고,
    36개 항목을 집합으로 맞추는 일이라 비싸지 않다.
    """
    check = judge_deliverables(cur, project_id, at)
    items, judgements = check.items, check.judgements
    changed = wbs_repository.save_judgements(cur, project_id, judgements)
    names = {i["wbs_id"]: i["name"] for i in items}
    for wbs_id, before, now in changed:
        # 제출로 바뀐 것은 발주기관이, 지연이 된 것은 둘 다 알아야 한다. 그 외 전이는 조용히
        if now == deliverable.SUBMITTED and before in (deliverable.MISSING, deliverable.OVERDUE):
            activity.record(
                cur, project_id=project_id, kind=activity.DELIVERABLE_SUBMITTED,
                audience=activity.CLIENT, actor_label="판정",
                summary=f"산출물 제출됨: {wbs_id} {names.get(wbs_id, '')}",
                target_type="WBS_ITEM", target_key=wbs_id,
            )
        elif now == deliverable.OVERDUE and before == deliverable.MISSING:
            activity.record(
                cur, project_id=project_id, kind=activity.DELIVERABLE_OVERDUE,
                audience=activity.ALL, actor_label="판정",
                summary=f"산출물 지연: {wbs_id} {names.get(wbs_id, '')}",
                target_type="WBS_ITEM", target_key=wbs_id,
            )
    # 묶음은 저장만 하고 돌려주지 않는다. 요약이 말단만 세야 "산출물 열 없음" 이 뜻을 가진다
    leaves = {i["wbs_id"] for i in items if i.get("weight") is not None}
    return {j.wbs_id: j for j in judgements if j.wbs_id in leaves}


def ensure_wbs_loaded(cur: Any, project_id: str) -> None:
    """현행 계획서의 항목 행이 있게 한다. 문서를 항목에 붙일 때처럼 행이 먼저 필요한 곳이 부른다."""
    plan_row = standard_repo.current_work_product(cur, project_id, PLAN_TYPE)
    _load_plan(cur, project_id, plan_row)


def wbs_deliverables(
    cur: Any, principal: AuthPrincipal, project_id: str, at: date | None = None
) -> WbsDeliverablesResponse:
    """산출물 화면. WBS 말단 작업마다 산출물·판정·붙은 문서·29110 태그를 한 줄로 낸다."""
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    today = at or clock.today()
    # 행이 그 계획서 버전에서 왔는지부터 맞춘다. 없으면 파일을 한 번 읽어 남긴다
    plan_row = standard_repo.current_work_product(cur, project_id, PLAN_TYPE)
    _load_plan(cur, project_id, plan_row)
    judged = refresh_deliverables(cur, project_id, today)
    items = wbs_repository.list_items(cur, project_id)
    documents = wbs_repository.project_documents(cur, project_id)
    products = wbs_repository.current_products(cur, project_id)
    doc_type_by_id = {str(p["id"]): p["type"] for p in products}
    live = {str(i["task_key"]) for i in items if i.get("task_key") and i.get("weight") is not None}
    designated_by_task, redesignation = designation.build(cur, project_id, live)

    by_item: dict[str, list[dict]] = {}
    by_stem: dict[str, list[dict]] = {}
    for d in documents:
        if d.get("wbs_item_id"):
            by_item.setdefault(str(d["wbs_item_id"]), []).append(d)
        by_stem.setdefault(deliverable_stem(d["original_filename"]), []).append(d)

    # 양식이 없는 작업의 검토 대상: 판정이 맞춘 산출물(11-18)
    plain_products = _review_rows(
        cur, [j.product_id for j in judged.values() if j.product_id and j.rule != "DESIGNATED"]
    )

    out: list[WbsDeliverableItem] = []
    for item in items:
        if item["weight"] is None:
            continue
        j = judged.get(item["wbs_id"])
        docs = list(by_item.get(str(item["id"]), []))
        if item.get("deliverable"):
            for d in by_stem.get(deliverable_stem(item["deliverable"]), []):
                if d not in docs:
                    docs.append(d)
        # 확정된 유형 > 사람이 단 태그 > 초안 추정 순
        product_type = (
            next(
                (doc_type_by_id[str(d["work_product_id"])] for d in docs
                 if d.get("work_product_id") and str(d["work_product_id"]) in doc_type_by_id),
                None,
            )
            or next((d["product_type"] for d in docs if d.get("product_type")), None)
            or next((d["proposed_type"] for d in docs if d.get("proposed_type")), None)
        )
        out.append(
            WbsDeliverableItem(
                wbsId=item["wbs_id"],
                name=item["name"],
                deliverable=item.get("deliverable"),
                endDate=item["end_on"].isoformat() if item.get("end_on") else None,
                status=j.status if j else deliverable.NONE,
                rule=j.rule if j else None,
                ref=j.ref if j else None,
                url=j.url if j else None,
                productType=product_type,
                documents=[
                    WbsDeliverableDocument(
                        id=str(d["id"]),
                        fileName=d["original_filename"],
                        status=d["status"],
                        uploadedAt=d["created_at"].isoformat(),
                        proposedType=d.get("proposed_type"),
                        # 유형을 바꿔 확정한 것(MANUAL_OVERRIDE)도 확정이다
                        confirmed=d.get("draft_status") in ("CONFIRMED", "MANUAL_OVERRIDE"),
                    )
                    for d in docs
                ],
                taskKey=str(item["task_key"]) if item.get("task_key") else None,
                designated=designated_by_task.get(str(item.get("task_key")), []),
                review=_review_of(
                    designated_by_task.get(str(item.get("task_key")), []), j, plain_products
                ),
            )
        )
    counts = deliverable.summarize(list(judged.values()))
    return WbsDeliverablesResponse(
        baseDate=today.isoformat(),
        items=out,
        summary=DeliverableSummary(
            submitted=counts[deliverable.SUBMITTED],
            missing=counts[deliverable.MISSING],
            overdue=counts[deliverable.OVERDUE],
            none=counts[deliverable.NONE],
        ),
        redesignation=redesignation,
    )


def _review_rows(cur: Any, ids: list[str]) -> dict[str, DeliverableReview]:
    if not ids:
        return {}
    rows = fetch_all(
        cur,
        """
        select w.id, w.title, w.type, w.version, w.status, w.reject_reason, w.is_current,
               w.file_uri, d.original_filename
          from work_product w
          left join document_upload d on d.id = w.document_upload_id
         where w.id = any(%s::uuid[])
        """,
        (list(set(ids)),),
    )
    return {
        str(r["id"]): DeliverableReview(
            workProductId=str(r["id"]),
            name=r["title"] or r["type"],
            fileName=r["original_filename"]
            or (r["file_uri"].rsplit("/", 1)[-1] if r.get("file_uri") else None),
            version=r["version"],
            status=r["status"],
            rejectReason=r["reject_reason"],
            isCurrent=bool(r["is_current"]),
        )
        for r in rows
        if r["status"] in ("SUBMITTED", "APPROVED", "REJECTED")
    }


def _review_of(
    designated: list[DesignatedDeliverable],
    j: deliverable.Judgement | None,
    plain: dict[str, DeliverableReview],
) -> list[DeliverableReview]:
    """한 작업에서 발주기관이 승인·반려할 제출본. 양식이 있으면 양식마다 가장 최근 제출본."""
    if designated:
        out: list[DeliverableReview] = []
        for d in designated:
            v = next((v for v in d.versions if v.workProductId), None)
            if v is None or v.state not in ("SUBMITTED", "APPROVED", "REJECTED"):
                continue
            out.append(DeliverableReview(
                workProductId=v.workProductId, name=d.name, fileName=v.fileName,
                version=v.version, status=v.state, rejectReason=v.rejectReason,
                isCurrent=v.isCurrent,
            ))
        return out
    if j is not None and j.product_id and j.product_id in plain:
        return [plain[j.product_id]]
    return []


def deliverable_stem(value: str) -> str:
    return deliverable.stem_of(value)


def linked_issues(cur: Any, project_id: str, plan: wbs.WbsPlan) -> dict[str, list[LinkedIssue]]:
    """말단 번호별로 이어진 이슈. 번호 토큰이 하나로 정확히 맞은 것만 잇는다(ARC-016 3-4)."""
    return linked_issues_by_ids(cur, project_id, {r.wbs_id for r in plan.rows if r.wbs_id})


def linked_issues_by_ids(
    cur: Any, project_id: str, ids: set[str]
) -> dict[str, list[LinkedIssue]]:
    """번호 집합으로 잇는다. 확인 요청 저장 상태도 이 규칙을 쓴다(DEF-V027)."""
    out: dict[str, list[LinkedIssue]] = {}
    if not ids:
        return out
    for row in wbs_repository.issues_for_linking(cur, project_id):
        wbs_id = wbs_issue.assign(ids, row["title"], row["payload"])
        if wbs_id is None:
            continue
        out.setdefault(wbs_id, []).append(
            LinkedIssue(
                key=row["issue_key"], title=row["title"], status=row["status"],
                url=row["external_url"],
            )
        )
    return out


def _items_from_plan(
    plan: wbs.WbsPlan,
    at: date,
    judged: dict[str, deliverable.Judgement] | None = None,
    linked: dict[str, list[LinkedIssue]] | None = None,
) -> list[WbsItemResponse]:
    """상위 항목은 하위 말단의 가중 평균으로 진척을 낸다. 말단은 파일의 실적 그대로다."""
    items: list[WbsItemResponse] = []
    judged = judged or {}
    leaves = plan.rows
    for group in plan.groups:
        prefix = group.wbs_id.rstrip(".") + "."
        under = [r for r in leaves if r.wbs_id.startswith(prefix)]
        total = sum(r.weight for r in under)
        actual = sum(r.weight * (r.actual or 0.0) for r in under) / total if total else 0.0
        planned = sum(r.weight * r.planned_at(at) for r in under) / total if total else 0.0
        start = group.start or min((r.start for r in under if r.start), default=None)
        end = group.end or max((r.end for r in under if r.end), default=None)
        items.append(
            WbsItemResponse(
                wbsId=group.wbs_id,
                name=group.name,
                level=_level_of(group.wbs_id),
                owner="",
                deliverable=None,
                startDate=start.isoformat() if start else None,
                endDate=end.isoformat() if end else None,
                weight=round(total, 4) if total else None,
                progress=_pct(actual),
                planned=_pct(planned),
                externalUrl=None,
            )
        )
    for row in leaves:
        j = judged.get(row.wbs_id)
        issues = (linked or {}).get(row.wbs_id, [])
        items.append(
            WbsItemResponse(
                wbsId=row.wbs_id,
                name=row.name,
                level=_level_of(row.wbs_id),
                owner="",
                deliverable=row.deliverable,
                startDate=row.start.isoformat() if row.start else None,
                endDate=row.end.isoformat() if row.end else None,
                weight=row.weight,
                progress=_pct(row.actual or 0.0),
                planned=_pct(row.planned_at(at)),
                externalUrl=None,
                deliverableStatus=j.status if j else deliverable.NONE,
                deliverableRule=j.rule if j else None,
                deliverableRef=j.ref if j else None,
                deliverableUrl=j.url if j else None,
                linkedIssues=issues,
                gapWarning=gap_warning(row.actual, j.status if j else deliverable.NONE, issues),
            )
        )
    items.sort(key=lambda i: _sort_key(i.wbsId))
    return items


# 작업 단위 격차 경고 문턱(DEC-20 = ARC-016 4절). 진행 중 작업마다 경고가 뜨면 소음이 된다
GAP_ACTUAL_THRESHOLD = 0.8
_OPEN_ISSUE = ("OPEN", "IN_PROGRESS")


def gap_warning(actual: float | None, status: str, issues: list[LinkedIssue]) -> str | None:
    """실적이 80 이상인데 산출물이 미제출(지연 포함)이거나 열린 연결 이슈가 있으면 한 줄."""
    if actual is None or actual + 1e-9 < GAP_ACTUAL_THRESHOLD:
        return None
    reasons: list[str] = []
    if status in (deliverable.MISSING, deliverable.OVERDUE):
        reasons.append("산출물 미제출")
    still_open = [i.key or i.title for i in issues if i.status in _OPEN_ISSUE]
    if still_open:
        reasons.append(f"열린 연결 이슈 {', '.join(still_open)}")
    if not reasons:
        return None
    return f"실적 {_pct(actual)}% 신고, " + " · ".join(reasons)


def _items_from_redmine(issues: list[dict[str, Any]], at: date) -> list[WbsItemResponse]:
    """시작일이나 종료일이 있는 이슈만 일정이다. 둘 다 없으면 일정이 아니라 목록이다."""
    items: list[WbsItemResponse] = []
    for issue in issues:
        start = _iso_date(issue.get("start_date"))
        end = _iso_date(issue.get("due_date"))
        if start is None and end is None:
            continue
        parent = issue.get("parent") or {}
        assignee = issue.get("assigned_to") or {}
        done = issue.get("done_ratio")
        row = wbs.WbsRow(
            wbs_id=str(issue.get("id", "")),
            name=str(issue.get("subject") or "").strip(),
            deliverable=None,
            start=start,
            end=end,
            weight=1.0,
            actual=(float(done) / 100.0) if isinstance(done, int | float) else 0.0,
            declared_planned=None,
        )
        base = (issue.get("_base_url") or "").rstrip("/")
        items.append(
            WbsItemResponse(
                wbsId=f"#{row.wbs_id}",
                name=row.name,
                level=1 if parent.get("id") else 0,
                owner=str(assignee.get("name") or ""),
                deliverable=None,
                startDate=start.isoformat() if start else None,
                endDate=end.isoformat() if end else None,
                weight=None,
                progress=_pct(row.actual),
                planned=_pct(row.planned_at(at)) if start and end else 0,
                externalUrl=f"{base}/issues/{row.wbs_id}" if base and row.wbs_id else None,
            )
        )
    items.sort(key=lambda i: (i.startDate or "9999", i.wbsId))
    return items


def _iso_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _pct(ratio: float) -> int:
    return max(0, min(100, round(ratio * 100)))


def current_wbs_rows(cur: Any, project_id: str) -> list[wbs.WbsRow]:
    """현행 WBS 의 말단 행. 없거나 못 읽으면 빈 목록이다. 확인 요청이 항목을 고를 때 쓴다."""
    plan_row = standard_repo.current_work_product(cur, project_id, PLAN_TYPE)
    plan, _ = _load_plan(cur, project_id, plan_row)
    return [] if plan is None else plan.rows


def _read_plan(
    cur: Any, project_id: str, plan_row: dict[str, Any] | None, at: date | None = None
) -> tuple[wbs.WbsProgress | None, str | None]:
    """현행 WBS 의 진척. 못 읽어도 나머지 두 갈래는 나와야 한다."""
    plan, warning = _load_plan(cur, project_id, plan_row)
    if plan is None:
        return None, warning
    # 이전 기준선으로 산정했으면 그 경고도 같이 낸다
    return wbs.progress(plan, at or clock.today()), warning


def _plan_path(project_id: str, plan_row: dict[str, Any], cur: Any = None) -> Path | None:
    """계획서 원본 파일. 자료로 올려 확정한 계획서는 업로드 보관 위치에 있다(DEF-V019).

    수집한 파일은 내용 주소로 보관된다 — <root>/<project>/repo/<sha><ext>.

    source_revision 이 없는 행은 이 컬럼이 생기기 전에 수집된 것이다. 버전이 sha 앞
    12자리이므로 접두로 찾으면 다시 수집하지 않아도 도달한다. 12자리면 사실상 유일하다.
    """
    if plan_row.get("document_upload_id") and cur is not None:
        stored = standard_repo.document_stored_path(cur, str(plan_row["document_upload_id"]))
        if stored:
            path = Path(settings.document_root) / stored
            return path if path.is_file() else None
    folder = Path(settings.document_root) / project_id / "repo"
    if not folder.is_dir():
        return None

    for prefix in (plan_row.get("source_revision"), plan_row.get("version")):
        if not prefix or prefix == "0":
            continue
        for candidate in sorted(folder.glob(f"{prefix}*")):
            if candidate.is_file():
                return candidate
    return None


def _representative(
    wbs_progress: wbs.WbsProgress | None,
    issue_estimate: ProgressMeasure,
    product: ProgressMeasure,
) -> tuple[str, str, float | None]:
    """L1~L4 저하. 위에서부터 성립하는 첫 수준을 쓴다 (진척률-산정체계 §1).

    WBS 가 있으면 값을 못 내도 아래로 내려가지 않는다. 가중치가 없으면 기간 비례 추정(L2)이고,
    기간·실적이 모자라면 대표값 없음이다(DEC-19). 이슈·산출물로 WBS 실적을 대신하지 않는다.
    """
    if wbs_progress is not None:
        if wbs_progress.estimated:
            return "L2", "WBS_ESTIMATED", wbs_progress.actual
        return "L1", "WBS", wbs_progress.actual
    # L3 는 이슈 기반 추정 진척률(DEC-17). 대상 이슈가 있으면 진척도가 모두 없어도 L3 에
    # 머물고 산출 불가다. 해결률(ISSUE)은 2026-11-16 전까지의 L3 산식이라 근거 코드를 바꿨다
    if issue_estimate.denominator:
        return "L3", ISSUE_PROGRESS, issue_estimate.value
    # 점검표만 있고 제출본이 하나도 없으면 L4 를 세우지 않는다. 0% 는 「진척이 없다」는 주장이라
    # 재료가 없는 것과 다르다(DEF-V003, IM-007 AC-002-1 「데이터 없음·산출 불가」)
    if product.denominator and product.numerator:
        return "L4", "WORK_PRODUCT", product.value
    return _NONE, _NONE, None


def _gap(*measures: ProgressMeasure) -> float | None:
    """가장 높은 갈래와 가장 낮은 갈래의 차이. 이 값이 크면 신고와 관측이 어긋난 것이다."""
    values = [m.value for m in measures if m.value is not None]
    if len(values) < 2:
        return None
    return round(max(values) - min(values), 4)


def _gap_warnings(
    wbs_progress: wbs.WbsProgress | None,
    issue: ProgressMeasure,
    product: ProgressMeasure,
) -> list[str]:
    """자기신고가 관측을 크게 앞서면 짚는다. 판정하지 않고 확인할 지점만 알린다."""
    if wbs_progress is None or wbs_progress.actual is None:
        return []
    out: list[str] = []
    for measure in (issue, product):
        if measure.value is None or not measure.denominator:
            continue
        gap = wbs_progress.actual - measure.value
        if gap >= 0.2:
            out.append(
                f"신고 진척률이 {measure.label}({measure.value:.0%})보다 "
                f"{gap:.0%}p 높습니다. 근거를 확인해 주세요"
            )
    return out


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else round(numerator / denominator, 4)
