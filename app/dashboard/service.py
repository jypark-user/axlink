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
from app.dashboard import deliverable, repository, wbs
from app.dashboard.models import (
    OBSERVED,
    SELF_REPORTED,
    WBS_SOURCE_FILE,
    WBS_SOURCE_NONE,
    WBS_SOURCE_REDMINE,
    DeliverableSummary,
    ProgressMeasure,
    ProgressResponse,
    WbsDeliverableDocument,
    WbsDeliverableItem,
    WbsDeliverablesResponse,
    WbsItemResponse,
    WbsScheduleResponse,
)
from app.integration import repository as integration_repo
from app.standard import repository as standard_repo
from app.standard import wbs_repository

# WBS 가 들어오는 산출물 항목. 저장소에 커밋된 계획 파일이 여기로 승격된다.
PLAN_TYPE = "PROJECT_PLAN"

_NONE = "NONE"


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
        label="일반 이슈 해결률",
        unit="건",
        kind=OBSERVED,
        # 명세서 전에 이슈로 만든 요구사항의 출처 이슈는 분모에 없다. 범위를 같이 보인다
        note="예전에 요구사항으로 만든 이슈 제외" if issue_total else "연동된 일반 이슈가 없습니다",
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
        judged = refresh_deliverables(cur, project_id, at)
        counts = deliverable.summarize(list(judged.values()))
        return WbsScheduleResponse(
            source=WBS_SOURCE_FILE,
            sourceLabel=f"용역사 WBS ({plan_row.get('file_uri') or '사업수행계획서'})",
            sourceUrl=plan_row.get("external_url"),
            baseDate=at.isoformat(),
            planVersion=plan_row["version"],
            planUpdatedAt=plan_row["updated_at"].isoformat(),
            items=_items_from_plan(plan, at, judged),
            warnings=[*warnings, *plan.warnings],
            notice=None,
            deliverables=DeliverableSummary(
                submitted=counts[deliverable.SUBMITTED],
                missing=counts[deliverable.MISSING],
                overdue=counts[deliverable.OVERDUE],
                none=counts[deliverable.NONE],
            ),
        )

    issues = integration_repo.redmine_issue_payloads(cur, project_id)
    items = _items_from_redmine(issues, at)
    if items:
        warnings.append(
            "WBS 파일이 없어 Redmine 이슈의 시작일·종료일을 일정으로 씁니다. 가중치가 없으므로 "
            "진척률 산정의 기준선(L1)은 아닙니다."
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
    )


def _load_plan(
    cur: Any, project_id: str, plan_row: dict[str, Any] | None
) -> tuple[wbs.WbsPlan | None, str | None]:
    """현행 계획서의 WBS. 행이 그 버전에서 왔으면 행을 읽고, 아니면 파일을 한 번 읽어 남긴다.

    파일은 계획서 버전마다 한 번만 연다(ARC-016). 그 뒤로 진척·일정·확인 요청·항목 화면이
    같은 행을 본다. 파일을 못 읽으면 예전 행이 있어도 쓰지 않는다. 틀린 버전의 값을 현행
    이라고 보이는 것보다 "못 읽었다" 가 낫다.
    """
    if plan_row is None:
        return None, None
    plan_id = str(plan_row["id"])
    if wbs_repository.loaded_version(cur, project_id) == plan_id:
        return wbs_repository.load_plan(cur, project_id), None

    path = _plan_path(project_id, plan_row)
    if path is None:
        return None, "WBS 항목은 있지만 보관된 원본 파일을 찾지 못했습니다. 다시 수집해 주세요."
    try:
        plan = wbs.parse(path.read_bytes())
    except wbs.WbsParseError as exc:
        return None, f"WBS 를 읽지 못했습니다. {exc}"
    except OSError as exc:
        return None, f"WBS 원본 파일을 열지 못했습니다. {exc}"
    wbs_repository.replace_plan(cur, project_id, plan_id, plan)
    return plan, None


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
    judgements = deliverable.judge(
        items,
        tree=tree,
        products=wbs_repository.current_products(cur, project_id),
        documents=wbs_repository.project_documents(cur, project_id),
        today=at,
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

    by_item: dict[str, list[dict]] = {}
    by_stem: dict[str, list[dict]] = {}
    for d in documents:
        if d.get("wbs_item_id"):
            by_item.setdefault(str(d["wbs_item_id"]), []).append(d)
        by_stem.setdefault(deliverable_stem(d["original_filename"]), []).append(d)

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
                        confirmed=d.get("draft_status") == "CONFIRMED",
                    )
                    for d in docs
                ],
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
    )


def deliverable_stem(value: str) -> str:
    return deliverable.stem_of(value)


def _items_from_plan(
    plan: wbs.WbsPlan, at: date, judged: dict[str, deliverable.Judgement] | None = None
) -> list[WbsItemResponse]:
    """상위 항목은 하위 말단의 가중 평균으로 진척을 낸다. 말단은 파일의 실적 그대로다."""
    items: list[WbsItemResponse] = []
    judged = judged or {}
    leaves = plan.rows
    for group in plan.groups:
        prefix = group.wbs_id.rstrip(".") + "."
        under = [r for r in leaves if r.wbs_id.startswith(prefix)]
        total = sum(r.weight for r in under)
        actual = sum(r.weight * r.actual for r in under) / total if total else 0.0
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
                progress=_pct(row.actual),
                planned=_pct(row.planned_at(at)),
                externalUrl=None,
                deliverableStatus=j.status if j else deliverable.NONE,
                deliverableRule=j.rule if j else None,
                deliverableRef=j.ref if j else None,
                deliverableUrl=j.url if j else None,
            )
        )
    items.sort(key=lambda i: _sort_key(i.wbsId))
    return items


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
    return wbs.progress(plan, at or clock.today()), None


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
                f"{gap:.0%}p 높습니다. 근거를 확인해 주세요"
            )
    return out


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else round(numerator / denominator, 4)
