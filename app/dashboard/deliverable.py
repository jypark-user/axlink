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
    today: date,
    designated: dict[str, Any] | None = None,
) -> list[Judgement]:
    """말단 항목마다 판정 하나. 묶음(weight 없음)과 예상 산출물이 없는 작업은 NONE.

    designated: 작업 정체(task_key) → 예상 산출물 현황(total · submitted).

    예상 산출물은 WBS 산출물 열에서 저절로 만든 항목과 발주기관이 요청한 항목이다(V73, 11-19).
    모두 올라왔으면 제출, 아니면 종료일이 지났으면 지연, 아니면 미제출. 예상 산출물이 없는 작업은
    판정하지 않는다.
    """
    designated = designated or {}
    out: list[Judgement] = []
    for item in items:
        wbs_id = item["wbs_id"]
        cover = designated.get(str(item.get("task_key"))) if item.get("task_key") else None
        if item.get("weight") is None or cover is None or cover.total == 0:
            out.append(Judgement(wbs_id, NONE))
            continue
        end = item.get("end_on")
        late = end is not None and end < today
        ref = f"예상 산출물 {cover.total}건 중 {cover.submitted}건 제출"
        if cover.submitted >= cover.total:
            out.append(Judgement(
                wbs_id, SUBMITTED, RULE_DESIGNATED, ref,
                product_id=getattr(cover, "product_id", None),
            ))
        else:
            out.append(Judgement(wbs_id, OVERDUE if late else MISSING, RULE_DESIGNATED, ref))
    return out


def summarize(judgements: list[Judgement]) -> dict[str, int]:
    counts = {SUBMITTED: 0, MISSING: 0, OVERDUE: 0, NONE: 0}
    for j in judgements:
        counts[j.status] = counts.get(j.status, 0) + 1
    return counts
