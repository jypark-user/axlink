"""건수가 비었을 때 0건인지, 셀 자료가 없는 것인지 (GH-127).

이슈·리스크·커밋은 도구에서 수집한다. 행이 없다는 것만으로는 "0건" 인지 "아직 안 모았다" 인지
모른다. 사업마다 연결과 마지막 수집 결과를 보고 가른다. 하나라도 못 믿을 사업이 있으면 0건이라고
말하지 않는다. 근거 없는 수치를 내지 않는 것과 같은 이유다(절대 규칙 1·3).
"""

from typing import Any

from app.db import fetch_all

# 도구 수집으로 채워지는 표. 문서·WBS 처럼 다른 길로 들어오는 표는 여기서 판정하지 않는다
COLLECTED_TABLES = frozenset({"issue", "risk", "code_change", "requirement"})

COLLECTED = "COLLECTED"
NOT_CONNECTED = "NOT_CONNECTED"
NOT_COLLECTED = "NOT_COLLECTED"
COLLECT_FAILED = "COLLECT_FAILED"

# 나쁜 쪽이 이긴다
_ORDER = (COLLECTED, NOT_COLLECTED, COLLECT_FAILED, NOT_CONNECTED)


def status(cur: Any, project_ids: list[str]) -> str:
    """사업 범위 전체의 수집 상태. 연결마다 가장 최근 수집 작업의 결과를 본다."""
    if not project_ids:
        return NOT_CONNECTED
    rows = fetch_all(
        cur,
        """
        select p.id as project_id, c.id as connection_id, j.status as last_job
          from project p
          left join tool_connection c on c.project_id = p.id
          left join lateral (
                select s.status from sync_job s
                 where s.tool_connection_id = c.id and s.status in ('SUCCEEDED', 'FAILED')
                 order by s.finished_at desc nulls last
                 limit 1
          ) j on true
         where p.id = any(%s::uuid[])
        """,
        (project_ids,),
    )
    worst = COLLECTED
    by_project: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_project.setdefault(str(row["project_id"]), []).append(row)
    for conns in by_project.values():
        state = _project_status(conns)
        if _ORDER.index(state) > _ORDER.index(worst):
            worst = state
    return worst


def _project_status(conns: list[dict[str, Any]]) -> str:
    real = [c for c in conns if c["connection_id"] is not None]
    if not real:
        return NOT_CONNECTED
    if any(c["last_job"] == "FAILED" for c in real):
        return COLLECT_FAILED
    if any(c["last_job"] is None for c in real):
        return NOT_COLLECTED
    return COLLECTED
