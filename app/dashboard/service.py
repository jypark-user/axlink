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

from datetime import date
from pathlib import Path
from typing import Any

from app.auth import repository as auth_repo
from app.auth.deps import AuthPrincipal
from app.common import errors
from app.config import settings
from app.dashboard import repository, wbs
from app.dashboard.models import OBSERVED, SELF_REPORTED, ProgressMeasure, ProgressResponse
from app.standard import repository as standard_repo

# WBS 가 들어오는 산출물 자리. 저장소에 커밋된 계획 파일이 여기로 승격된다.
PLAN_TYPE = "PROJECT_PLAN"

_NONE = "NONE"


def project_progress(
    cur: Any, principal: AuthPrincipal, project_id: str, at: date | None = None
) -> ProgressResponse:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()

    at = at or date.today()
    warnings: list[str] = []

    plan_row = standard_repo.current_work_product(cur, project_id, PLAN_TYPE)
    wbs_progress, plan_warning = _read_plan(project_id, plan_row)
    if plan_warning:
        warnings.append(plan_warning)
    if wbs_progress is not None:
        warnings.extend(wbs_progress.warnings)

    issue_done, issue_total = repository.issue_resolution(cur, project_id)
    product_done, product_total = repository.work_product_submission(cur, project_id)

    wbs_measure = ProgressMeasure(
        value=None if wbs_progress is None else wbs_progress.actual,
        numerator=None,
        denominator=None if wbs_progress is None else wbs_progress.leaf_count,
        label="WBS 기반 진척률",
        unit="말단 작업 가중합",
        kind=SELF_REPORTED,
        note=None
        if wbs_progress is not None
        else "WBS 파일이 수집되지 않았다. 저장소에 커밋하면 자동으로 잡힌다",
    )
    issue_measure = ProgressMeasure(
        value=_ratio(issue_done, issue_total),
        numerator=issue_done,
        denominator=issue_total,
        label="이슈 해결률",
        unit="건",
        kind=OBSERVED,
        note=None if issue_total else "연동된 이슈가 없다",
    )
    product_measure = ProgressMeasure(
        value=_ratio(product_done, product_total),
        numerator=product_done,
        denominator=product_total,
        label="산출물 제출률",
        unit="건",
        kind=OBSERVED,
        note=None if product_total else "산출물 자리가 아직 만들어지지 않았다",
    )

    level, basis, representative = _representative(
        wbs_progress, issue_measure, product_measure
    )
    warnings.extend(_gap_warnings(wbs_progress, issue_measure, product_measure))

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
        workProduct=product_measure,
        behind=[] if wbs_progress is None else wbs_progress.behind,
        warnings=warnings,
        planVersion=None if plan_row is None else plan_row["version"],
        planUpdatedAt=None if plan_row is None else plan_row["updated_at"].isoformat(),
    )


def current_wbs_rows(cur: Any, project_id: str) -> list[wbs.WbsRow]:
    """현행 WBS 의 행. 파일이 없거나 못 읽으면 빈 목록이다. 확인 요청이 항목을 고를 때 쓴다."""
    plan_row = standard_repo.current_work_product(cur, project_id, PLAN_TYPE)
    if plan_row is None:
        return []
    path = _plan_path(project_id, plan_row)
    if path is None:
        return []
    try:
        return wbs.parse(path.read_bytes()).rows
    except (wbs.WbsParseError, OSError):
        return []


def _read_plan(
    project_id: str, plan_row: dict[str, Any] | None, at: date | None = None
) -> tuple[wbs.WbsProgress | None, str | None]:
    """수집해 둔 WBS 파일을 읽는다. 못 읽어도 나머지 두 갈래는 나와야 한다."""
    if plan_row is None:
        return None, None

    path = _plan_path(project_id, plan_row)
    if path is None:
        return None, "WBS 자리는 채워졌으나 보관된 원본을 찾지 못했다. 다시 수집이 필요하다"

    try:
        plan = wbs.parse(path.read_bytes())
    except wbs.WbsParseError as exc:
        return None, f"WBS 를 읽지 못했다 — {exc}"
    except OSError as exc:
        return None, f"WBS 원본을 열지 못했다 — {exc}"

    return wbs.progress(plan, at or date.today()), None


def _plan_path(project_id: str, plan_row: dict[str, Any]) -> Path | None:
    """수집한 파일은 내용 주소로 보관된다 — <root>/<project>/repo/<sha><ext>.

    source_revision 이 없는 행은 이 컬럼이 생기기 전에 수집된 것이다. 버전이 sha 앞
    12자리이므로 접두로 찾으면 다시 수집하지 않아도 도달한다. 12자리면 사실상 유일하다.
    """
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
    issue: ProgressMeasure,
    product: ProgressMeasure,
) -> tuple[str, str, float | None]:
    """L1~L4 저하. 위에서부터 성립하는 첫 수준을 쓴다 (진척률-산정체계 §1)."""
    if wbs_progress is not None:
        return "L1", "WBS", wbs_progress.actual
    if issue.denominator:
        return "L3", "ISSUE", issue.value
    if product.denominator:
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
    if wbs_progress is None:
        return []
    out: list[str] = []
    for measure in (issue, product):
        if measure.value is None or not measure.denominator:
            continue
        gap = wbs_progress.actual - measure.value
        if gap >= 0.2:
            out.append(
                f"신고 진척률이 {measure.label}({measure.value:.0%})보다 "
                f"{gap:.0%}p 높다. 근거 확인이 필요하다"
            )
    return out


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else round(numerator / denominator, 4)
