"""WBS 항목 저장소 (ARC-016). 파일에서 읽은 계획을 행으로 남기고, 그 뒤로는 행만 읽는다.

한 계획서 버전은 한 번만 읽는다. 같은 work_product_id 로 적재된 행이 있으면 파일을 다시
열지 않는다. 계획서를 다시 올리면(새 버전) 같은 번호는 갱신하고 빠진 번호는 active=false
로 남긴다. 이슈·확인 요청이 가리키던 항목이 조용히 사라지면 안 된다.
"""

from __future__ import annotations

from typing import Any

from app.dashboard import wbs
from app.db import fetch_all, fetch_one


def loaded_version(cur: Any, project_id: str) -> str | None:
    """지금 행들이 어느 계획서 버전에서 왔는가. 없으면 None."""
    row = fetch_one(
        cur,
        "select work_product_id from wbs_item where project_id = %s and active limit 1",
        (project_id,),
    )
    return None if row is None or row["work_product_id"] is None else str(row["work_product_id"])


def replace_plan(cur: Any, project_id: str, work_product_id: str | None, plan: wbs.WbsPlan) -> None:
    """계획 하나를 통째로 반영한다. 말단은 weight 가 있고 묶음은 없다."""
    seen: list[str] = []
    line = 0
    for group in plan.groups:
        line += 1
        _upsert(
            cur, project_id, work_product_id, line,
            wbs_id=group.wbs_id, name=group.name, deliverable=None,
            start=group.start, end=group.end, weight=None, declared_planned=None, actual=None,
        )
        seen.append(group.wbs_id)
    for row in plan.rows:
        line += 1
        _upsert(
            cur, project_id, work_product_id, line,
            wbs_id=row.wbs_id, name=row.name, deliverable=row.deliverable,
            start=row.start, end=row.end, weight=row.weight,
            declared_planned=row.declared_planned, actual=row.actual,
        )
        seen.append(row.wbs_id)
    cur.execute(
        """
        update wbs_item set active = false, updated_at = now()
         where project_id = %s and active and not (wbs_id = any(%s))
        """,
        (project_id, seen),
    )


def _parent_of(wbs_id: str) -> str | None:
    head, sep, _ = wbs_id.rpartition(".")
    return head if sep else None


def _upsert(
    cur: Any, project_id: str, work_product_id: str | None, line: int, *, wbs_id: str,
    name: str, deliverable: str | None, start, end, weight, declared_planned, actual,
) -> None:
    cur.execute(
        """
        insert into wbs_item (project_id, wbs_id, parent_wbs_id, name, deliverable, start_on,
                              end_on, weight, declared_planned, actual, line_no,
                              work_product_id, active)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
        on conflict (project_id, wbs_id) do update set
          parent_wbs_id = excluded.parent_wbs_id, name = excluded.name,
          deliverable = excluded.deliverable, start_on = excluded.start_on,
          end_on = excluded.end_on, weight = excluded.weight,
          declared_planned = excluded.declared_planned, actual = excluded.actual,
          line_no = excluded.line_no, work_product_id = excluded.work_product_id,
          active = true, updated_at = now()
        """,
        (
            project_id, wbs_id, _parent_of(wbs_id), name[:500], deliverable, start, end,
            weight, declared_planned, actual, line, work_product_id,
        ),
    )


def load_plan(cur: Any, project_id: str) -> wbs.WbsPlan | None:
    """활성 행을 파서가 내는 것과 같은 꼴로 돌려준다. 말단이 없으면 None."""
    rows = fetch_all(
        cur,
        """
        select wbs_id, name, deliverable, start_on, end_on, weight, declared_planned, actual
          from wbs_item
         where project_id = %s and active
         order by line_no, wbs_id
        """,
        (project_id,),
    )
    leaves: list[wbs.WbsRow] = []
    groups: list[wbs.WbsGroup] = []
    for r in rows:
        if r["weight"] is None:
            groups.append(
                wbs.WbsGroup(
                    wbs_id=r["wbs_id"], name=r["name"], start=r["start_on"], end=r["end_on"]
                )
            )
            continue
        declared = r["declared_planned"]
        leaves.append(
            wbs.WbsRow(
                wbs_id=r["wbs_id"],
                name=r["name"],
                deliverable=r["deliverable"],
                start=r["start_on"],
                end=r["end_on"],
                weight=float(r["weight"]),
                actual=float(r["actual"] or 0),
                declared_planned=None if declared is None else float(declared),
            )
        )
    if not leaves:
        return None
    total = round(sum(r.weight for r in leaves), 6)
    warnings: list[str] = []
    if abs(total - 1.0) > 0.005:
        warnings.append(f"가중치 합이 1.00 이 아니다 ({total:.3f}). 합으로 나눠 정규화했다")
    return wbs.WbsPlan(rows=leaves, weight_total=total, warnings=warnings, groups=groups)


def list_items(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """항목 화면·질의용 원본 행. 활성만."""
    return fetch_all(
        cur,
        """
        select id, wbs_id, parent_wbs_id, name, deliverable, start_on, end_on, weight,
               declared_planned, actual, line_no, work_product_id
          from wbs_item
         where project_id = %s and active
         order by line_no, wbs_id
        """,
        (project_id,),
    )
