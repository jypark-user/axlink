"""ISO/IEC 29110 산출물 22종 충족 현황(11-19 사용자 결정). 인도 점검표를 대신하는 읽기 전용 화면.

22종 하나하나를 네 상태로 가른다.

- 계획 없음: 예상 산출물(WBS 자동 + 발주사 요청) 중 이 분류가 없다. 계획에 없으면 결과로도
  오지 않는다
- 미제출: 계획에는 있는데 아직 안 올라왔다(가장 최근 것이 반려면 여기다)
- 제출: 올라왔고 아직 승인 전이다
- 승인: 이 분류의 예상 산출물 중 하나라도 발주기관이 승인했다

예상 산출물의 분류는 발주사가 정한 분류가 먼저고, 없으면 이름(22종 이름이나 흔한 별칭)으로,
그래도 없으면 가장 최근 올라온 문서의 분류로 본다. 진척 지표가 아니다. 셈에 섞지 않는다.
"""

from __future__ import annotations

from typing import Any

from app.auth.models import AuthPrincipal
from app.dashboard import designation, designation_repository
from app.dashboard.models import Iso29110Item, Iso29110Response, Iso29110Source
from app.standard import wbs_repository
from app.standard.work_product_type import ACTIVITIES, DISPLAY_NAMES

UNPLANNED, PLANNED, SUBMITTED, APPROVED = "UNPLANNED", "PLANNED", "SUBMITTED", "APPROVED"
_RANK = {UNPLANNED: 0, PLANNED: 1, SUBMITTED: 2, APPROVED: 3}

# 22종 이름 말고 흔히 쓰는 이름. 긴 것부터 맞춘다
_ALIASES: dict[str, str] = {
    "사업수행계획": "PROJECT_PLAN",
    "수행계획서": "PROJECT_PLAN",
    "wbs": "PROJECT_PLAN",
    "요구사항추적": "TRACEABILITY_RECORD",
    "추적표": "TRACEABILITY_RECORD",
    "시험계획": "TEST_CASES_PROCEDURES",
    "테스트계획": "TEST_CASES_PROCEDURES",
    "시험결과": "TEST_REPORT",
    "테스트결과": "TEST_REPORT",
    "사용자매뉴얼": "SOFTWARE_USER_DOC",
    "사용자설명서": "SOFTWARE_USER_DOC",
    "운영매뉴얼": "PRODUCT_OPERATION_GUIDE",
    "운영지침": "PRODUCT_OPERATION_GUIDE",
    "회의록": "MEETING_RECORD",
    "진척보고": "PROGRESS_STATUS_RECORD",
    "주간보고": "PROGRESS_STATUS_RECORD",
    "월간보고": "PROGRESS_STATUS_RECORD",
    "검수확인": "ACCEPTANCE_RECORD",
    "변경요청": "CHANGE_REQUEST",
}


def _norm(value: str) -> str:
    return "".join(value.split()).casefold()


_NAME_KEYS: list[tuple[str, str]] = sorted(
    [(_norm(label), code) for code, label in DISPLAY_NAMES.items()]
    + [(_norm(alias), code) for alias, code in _ALIASES.items()],
    key=lambda pair: -len(pair[0]),
)


def type_from_name(name: str) -> str | None:
    """이름에 22종 이름이나 별칭이 들어 있으면 그 분류."""
    key = _norm(name)
    return next((code for text, code in _NAME_KEYS if text and text in key), None)


def _process(code: str) -> str:
    pm, _ = ACTIVITIES.get(code, ("PM_1", None))
    return "PM" if pm else "SI"


def build(cur: Any, principal: AuthPrincipal, project_id: str) -> Iso29110Response:
    from app.dashboard import service as dashboard_service

    dashboard_service.require_project(cur, principal, project_id)
    designation_repository.sync_wbs_expected(cur, project_id)
    items = wbs_repository.list_items(cur, project_id)
    live = {str(i["task_key"]) for i in items if i.get("task_key") and i.get("weight") is not None}
    by_task, _ = designation.build(cur, project_id, live)
    wbs_id_of = {str(i["task_key"]): i["wbs_id"] for i in items if i.get("task_key")}

    # 올라온 문서의 분류(확정한 산출물 유형 > 사람이 단 태그 > 초안 추정)
    products = {str(p["id"]): p["type"] for p in wbs_repository.current_products(cur, project_id)}
    doc_type: dict[str, str] = {}
    for d in wbs_repository.project_documents(cur, project_id):
        code = (
            products.get(str(d.get("work_product_id")))
            or d.get("product_type")
            or d.get("proposed_type")
        )
        if code:
            doc_type[str(d["id"])] = code

    found: dict[str, list[Iso29110Source]] = {}
    for task_key, entries in by_task.items():
        for e in entries:
            code = e.productType or type_from_name(e.name) or next(
                (doc_type[v.documentId] for v in e.versions if v.documentId in doc_type), None
            )
            if code not in DISPLAY_NAMES:
                continue
            state = {"APPROVED": APPROVED, "SUBMITTED": SUBMITTED}.get(e.status, PLANNED)
            found.setdefault(code, []).append(Iso29110Source(
                wbsId=wbs_id_of.get(task_key, e.wbsIdAt), name=e.name, origin=e.origin,
                status=state,
            ))

    out = []
    for code, label in DISPLAY_NAMES.items():
        sources = found.get(code, [])
        status = max((s.status for s in sources), key=_RANK.__getitem__, default=UNPLANNED)
        out.append(Iso29110Item(
            type=code, name=label, process=_process(code), status=status, sources=sources,
        ))
    counts = {k: sum(1 for i in out if i.status == k) for k in _RANK}
    return Iso29110Response(items=out, counts=counts)
