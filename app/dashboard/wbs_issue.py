"""이슈를 WBS 말단 항목에 잇는다 (ARC-016 3-4).

근거는 그 사업의 WBS 번호와 **정확히 같은 토큰**뿐이다. 라벨(`WBS: 3.2`·`wbs-3.2`·`3.2`),
제목 앞머리(`[3.2] …`·`3.2 …`), Redmine 커스텀 필드 `WBS ID`. 번호 집합에 없는 값이나
서로 다른 번호가 둘 이상 나오면 잇지 않는다. 비슷해 보인다고 추측하지 않는다.
읽을 때마다 계산하고 저장하지 않는다. 계획서 판이 바뀌면 번호 집합도 바뀌기 때문이다.
"""

from __future__ import annotations

import re
from typing import Any

_LABEL = re.compile(r"^\s*(?:wbs\s*[:\-]\s*)?([0-9]+(?:\.[0-9]+)*)\s*$", re.IGNORECASE)
_TITLE = re.compile(r"^\s*(?:\[\s*([0-9]+(?:\.[0-9]+)*)\s*\]|([0-9]+(?:\.[0-9]+)+)\s)")
_FIELD_NAMES = frozenset({"wbsid", "wbs"})


def tokens(title: str | None, payload: dict[str, Any] | None) -> set[str]:
    """이슈 하나에서 읽은 WBS 번호 후보."""
    found: set[str] = set()
    m = _TITLE.match(title or "")
    if m:
        found.add(m.group(1) or m.group(2))
    payload = payload or {}
    for label in payload.get("labels") or []:
        name = label.get("name") if isinstance(label, dict) else label
        m = _LABEL.match(str(name or ""))
        if m:
            found.add(m.group(1))
    for field in payload.get("custom_fields") or []:
        if str(field.get("name") or "").lower().replace(" ", "") not in _FIELD_NAMES:
            continue
        m = _LABEL.match(str(field.get("value") or ""))
        if m:
            found.add(m.group(1))
    return found


def assign(wbs_ids: set[str], title: str | None, payload: dict[str, Any] | None) -> str | None:
    """이 이슈가 딸린 말단 번호. 하나로 정해질 때만 돌려준다."""
    hits = tokens(title, payload) & wbs_ids
    return next(iter(hits)) if len(hits) == 1 else None
