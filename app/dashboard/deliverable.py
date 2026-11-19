"""WBS 항목의 산출물 제출 판정 (ARC-016 2단계). 순수 함수만 둔다.

제출은 그 작업(또는 그 작업의 산출물 양식)에 올라온 산출물이 있는 것이다. 파일을 직접 올렸든
저장소 파일을 골라 올렸든 같다(11-19 사용자 결정). 저장소에 이름이 맞는 파일이 있다고 저절로
제출로 보지 않는다. 그러면 제출인데 승인할 대상이 없는 작업이 생긴다. 올라온 것이 없으면
미제출이고, 종료일이 오늘보다 앞이면 지연이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

NONE = "NONE"
SUBMITTED = "SUBMITTED"
MISSING = "MISSING"
OVERDUE = "OVERDUE"

RULE_LINK = "LINKED_DOC"
RULE_DESIGNATED = "DESIGNATED"  # 발주기관 지정 항목으로 판정(UC-033)


@dataclass(frozen=True)
class RepoTree:
    """수집한 저장소 파일 목록. 한 번의 트리 조회 결과다."""

    sha: str
    paths: frozenset[str]
    blob_url_base: str | None  # https://github.com/o/r/blob/<sha>/  꼴. 없으면 링크를 못 만든다

    def url_for(self, path: str) -> str | None:
        return f"{self.blob_url_base}{path}" if self.blob_url_base else None


@dataclass(frozen=True)
class Judgement:
    wbs_id: str
    status: str
    rule: str | None = None
    ref: str | None = None
    url: str | None = None
    # 올라온 문서가 확정한 산출물 버전이 있으면 그 id
    product_id: str | None = None


def _id(value: Any) -> str | None:
    return str(value) if value else None


def judge(
    items: list[dict[str, Any]],
    *,
    documents: list[dict[str, Any]],
    today: date,
    designated: dict[str, Any] | None = None,
) -> list[Judgement]:
    """말단 항목마다 판정 하나. 묶음(weight 없음)과 산출물 열이 빈 항목은 NONE.

    documents: 올린 문서. id · original_filename · wbs_item_id · work_product_id (최근 것이 앞)
    designated: 작업 정체(task_key) → 산출물 양식 현황(total · submitted). 양식이 있는 작업은
        산출물 열 대신 「양식마다 올라왔는가」로 판정한다(UC-033 4단계).
    """
    designated = designated or {}
    linked: dict[str, dict] = {}
    for d in documents:  # 최근 것이 앞에 온다. 항목마다 첫 것만 근거로 쓴다
        key = str(d["wbs_item_id"]) if d.get("wbs_item_id") else None
        if key and key not in linked:
            linked[key] = d

    out: list[Judgement] = []
    for item in items:
        wbs_id = item["wbs_id"]
        deliverable = (item.get("deliverable") or "").strip()
        cover = designated.get(str(item.get("task_key"))) if item.get("task_key") else None
        end = item.get("end_on")
        late = end is not None and end < today
        if item.get("weight") is not None and cover is not None and cover.total > 0:
            ref = f"지정 산출물 {cover.total}건 중 {cover.submitted}건 제출"
            if cover.submitted >= cover.total:
                out.append(Judgement(
                    wbs_id, SUBMITTED, RULE_DESIGNATED, ref,
                    product_id=getattr(cover, "product_id", None),
                ))
            else:
                out.append(Judgement(wbs_id, OVERDUE if late else MISSING, RULE_DESIGNATED, ref))
            continue
        if item.get("weight") is None or not deliverable:
            out.append(Judgement(wbs_id, NONE))
            continue

        doc = linked.get(str(item.get("id"))) if item.get("id") else None
        if doc is not None:
            out.append(Judgement(
                wbs_id, SUBMITTED, RULE_LINK, doc["original_filename"],
                f"/api/documents/{doc['id']}/content", _id(doc.get("work_product_id")),
            ))
            continue
        out.append(Judgement(wbs_id, OVERDUE if late else MISSING))
    return out


def summarize(judgements: list[Judgement]) -> dict[str, int]:
    counts = {SUBMITTED: 0, MISSING: 0, OVERDUE: 0, NONE: 0}
    for j in judgements:
        counts[j.status] = counts.get(j.status, 0) + 1
    return counts
