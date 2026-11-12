"""진척 집계 SQL. 세 갈래의 분자·분모를 각각 센다.

분모가 셋 다 다르다. WBS 는 가중치 합, 이슈는 전체 이슈 수, 산출물은 적용 대상 항목 수다.
값만 나란히 두면 "왜 다르냐" 는 질문에 답할 수 없으므로 분모를 함께 돌려준다.
"""

from typing import Any

from app.db import fetch_all, fetch_one


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


# 일정 준수율은 시맨틱 지표 schedule_compliance_rate(V64)와 같은 조건이다. 목록·현황(이 함수)과
# 질의·위젯(카탈로그)이 같은 값을 내야 한다.

_ACHIEVED = (
    "m.state = 'CLOSED' and m.closed_at is not null "
    "and (m.closed_at at time zone 'Asia/Seoul')::date <= m.due_on"
)


def schedule_compliance(cur: Any, project_ids: list[str], at: Any) -> dict[str, tuple[int, int]]:
    """일정 준수율(DEC-01). 사업별 (기한 안에 닫힌 수, 기한이 기준일 이전인 수).

    분자·분모가 같은 집합이다. 기한 없는 마일스톤은 빼고, 다시 열렸다 닫힌 것은 마지막
    닫힌 날(closed_at)로 본다. 평가 대상이 없는 사업은 결과에 없다(산출 불가).
    """
    rows = fetch_all(
        cur,
        f"""
        select m.project_id,
               count(*) filter (where {_ACHIEVED}) as achieved,
               count(*) as total
          from milestone m
         where m.project_id = any(%s::uuid[]) and m.due_on is not null and m.due_on < %s
         group by m.project_id
        """,
        (project_ids, at),
    )
    return {str(r["project_id"]): (int(r["achieved"]), int(r["total"])) for r in rows}


def current_status_by_product(cur: Any, product_ids: list[str]) -> dict[str, str | None]:
    """산출물 항목(버전) id → 그 유형의 현행 버전 상태. 승인률 분자는 현행 버전만 본다."""
    if not product_ids:
        return {}
    rows = fetch_all(
        cur,
        """
        select wpm.id, wpc.status
          from work_product wpm
          left join work_product wpc
            on wpc.project_id = wpm.project_id and wpc.type = wpm.type and wpc.is_current
         where wpm.id = any(%s::uuid[])
        """,
        (product_ids,),
    )
    return {str(r["id"]): r["status"] for r in rows}
