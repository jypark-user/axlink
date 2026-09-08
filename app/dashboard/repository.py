"""진척 집계 SQL. 세 갈래의 분자·분모를 각각 센다.

분모가 셋 다 다르다. WBS 는 가중치 합, 이슈는 전체 이슈 수, 산출물은 적용 대상 자리 수다.
값만 나란히 두면 "왜 다르냐" 는 질문에 답할 수 없으므로 분모를 함께 돌려준다.
"""

from typing import Any

from app.db import fetch_one


def issue_resolution(cur: Any, project_id: str) -> tuple[int, int]:
    """이슈 해결률. 닫힌 이슈 / 전체 이슈."""
    row = fetch_one(
        cur,
        """
        select count(*) filter (where status in ('RESOLVED', 'CLOSED')) as resolved,
               count(*) as total
          from issue
         where project_id = %s
        """,
        (project_id,),
    )
    return int(row["resolved"]), int(row["total"])


def work_product_submission(cur: Any, project_id: str) -> tuple[int, int]:
    """산출물 제출률. 낸 것 / 내야 할 자리.

    적용 대상이 아닌 자리(applicable = false)는 분모에서 뺀다. 사업마다 해당 없는
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
