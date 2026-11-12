"""진척 집계 SQL. 세 갈래의 분자·분모를 각각 센다.

분모가 셋 다 다르다. WBS 는 가중치 합, 이슈는 일반 이슈(결함 제외) 수, 산출물은 적용 대상 항목 수다.
값만 나란히 두면 "왜 다르냐" 는 질문에 답할 수 없으므로 분모를 함께 돌려준다.
"""

from typing import Any

from app.db import fetch_one


def issue_resolution(cur: Any, project_id: str) -> tuple[int, int]:
    """일반 이슈 해결률. 닫힌 일반 이슈 / 전체 일반 이슈. 결함은 빼고 센다(DEC-02)."""
    return _resolution(cur, project_id, "GENERAL")


def defect_resolution(cur: Any, project_id: str) -> tuple[int, int]:
    """결함 처리율. 닫힌 결함 / 전체 결함(DEC-02)."""
    return _resolution(cur, project_id, "DEFECT")


def _resolution(cur: Any, project_id: str, kind: str) -> tuple[int, int]:
    row = fetch_one(
        cur,
        """
        select count(*) filter (where status in ('RESOLVED', 'CLOSED')) as resolved,
               count(*) as total
          from issue
         where project_id = %s and issue_kind = %s
        """,
        (project_id, kind),
    )
    return int(row["resolved"]), int(row["total"])


def defect_mapped(cur: Any, project_id: str) -> bool:
    """사업의 연결 가운데 결함 매핑(결함 트래커·결함 라벨)을 둔 것이 있는가(DEC-02).

    없으면 결함을 가를 수 없다. 결함 처리율은 산출하지 않고 일반 이슈 = 전체 이슈다.
    """
    row = fetch_one(
        cur,
        """
        select exists (
          select 1 from tool_connection
           where project_id = %s
             and jsonb_typeof(mapping_rules_json) = 'object'
             and (coalesce(btrim(mapping_rules_json ->> 'defectTracker'), '') <> ''
                  or coalesce(btrim(mapping_rules_json ->> 'defectLabel'), '') <> '')
        ) as mapped
        """,
        (project_id,),
    )
    return bool(row["mapped"])


def work_product_submission(cur: Any, project_id: str) -> tuple[int, int]:
    """산출물 제출률. 낸 것 / 내야 할 항목.

    적용 대상이 아닌 항목(applicable = false)은 분모에서 뺀다. 사업마다 해당 없는
    관리객체가 있는데 그걸 분모에 두면 아무리 잘해도 100% 가 안 나온다.
    """
    row = fetch_one(
        cur,
        """
        select count(*) filter (where status in ('SUBMITTED', 'APPROVED')) as submitted,
               count(*) as total
          from work_product
         where project_id = %s and is_current and applicable
        """,
        (project_id,),
    )
    return int(row["submitted"]), int(row["total"])


def requirement_implementation(cur: Any, project_id: str) -> tuple[int, int]:
    """요구사항 이행률. 구현 이상 / 전체. 화면에는 아직 안 쓰고 경고 판단에만 쓴다."""
    row = fetch_one(
        cur,
        """
        select count(*) filter (
                 where status in ('IMPLEMENTED', 'VERIFIED', 'ACCEPTED')
               ) as done,
               count(*) as total
          from requirement
         where project_id = %s
        """,
        (project_id,),
    )
    return int(row["done"]), int(row["total"])
