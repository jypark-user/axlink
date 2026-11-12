"""WBS 항목 저장소 (ARC-016). 파일에서 읽은 계획을 행으로 남기고, 그 뒤로는 행만 읽는다.

한 계획서 버전은 한 번만 읽는다. 같은 work_product_id 로 적재된 행이 있으면 파일을 다시
열지 않는다. 계획서를 다시 올리면(새 버전) 같은 번호는 갱신하고 빠진 번호는 active=false
로 남긴다. 이슈·확인 요청이 가리키던 항목이 조용히 사라지면 안 된다.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from psycopg.types.json import Jsonb

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


def name_key(name: str) -> str:
    """작업명 비교 키. V46 의 wbs_item.name_key 생성식과 같아야 한다(btrim 은 공백만 깎는다)."""
    return re.sub(r"[ \t\n\r\f\v]+", " ", name.strip(" ")).lower()


def _decide_key(
    prev: dict[str, Any] | None, *, name: str, weight: Any, restructured: bool
) -> tuple[str | None, str]:
    """이 행이 직전 계획의 같은 작업인지. (이어 갈 task_key 또는 None, 이유).

    이을 수 있다는 증거가 모두 있을 때만 잇는다. 하나라도 모자라면 새 작업으로 보고
    예전 확인을 승계하지 않는다(재확인 대상).
    """
    if prev is None:
        return None, "NEW"
    if not prev["active"]:
        return None, "REAPPEARED"  # 한 번 빠졌다 돌아온 번호. 같은 작업이라는 증거가 없다
    if (prev["weight"] is None) != (weight is None):
        return None, "LEAF_CHANGED"  # 말단이 묶음이 됐거나(분할) 그 반대
    if prev["name_key"] != name_key(name):
        return None, "RENAMED"  # 번호만 같은 다른 작업일 수 있다
    if weight is not None and restructured and float(prev["weight"]) != float(weight):
        return None, "RESTRUCTURED"  # 형제 작업이 생기거나 빠지면서 가중치가 옮겨 갔다(병합·분할)
    return str(prev["task_key"]), "CONTINUED"


def replace_plan(cur: Any, project_id: str, work_product_id: str | None, plan: wbs.WbsPlan) -> None:
    """계획 하나를 통째로 반영한다. 말단은 weight 가 있고 묶음은 없다.

    번호(wbs_id)는 같아도 다른 작업일 수 있다. 작업의 정체는 task_key 로 따로 두고,
    직전 계획과 같은 작업임이 확인될 때만 이어 간다(_decide_key).
    """
    prev = {
        r["wbs_id"]: r
        for r in fetch_all(
            cur,
            """
            select wbs_id, task_key, name_key, weight, active, parent_wbs_id
              from wbs_item where project_id = %s
            """,
            (project_id,),
        )
    }
    # 부모마다 말단 구성이 바뀌었는가. 바뀐 자리의 가중치 변화는 단순 조정으로 보지 않는다
    before: dict[str | None, set[str]] = {}
    for r in prev.values():
        if r["active"] and r["weight"] is not None:
            before.setdefault(r["parent_wbs_id"], set()).add(r["wbs_id"])
    after: dict[str | None, set[str]] = {}
    for row in plan.rows:
        after.setdefault(_parent_of(row.wbs_id), set()).add(row.wbs_id)
    restructured = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}

    seen: list[str] = []
    line = 0
    for group in plan.groups:
        line += 1
        key, reason = _decide_key(
            prev.get(group.wbs_id), name=group.name, weight=None, restructured=False
        )
        _upsert(
            cur, project_id, work_product_id, line,
            wbs_id=group.wbs_id, name=group.name, deliverable=None,
            start=group.start, end=group.end, weight=None, declared_planned=None, actual=None,
            task_key=key, key_reason=reason, estimated=False,
        )
        seen.append(group.wbs_id)
    for row in plan.rows:
        line += 1
        key, reason = _decide_key(
            prev.get(row.wbs_id), name=row.name, weight=row.weight,
            restructured=_parent_of(row.wbs_id) in restructured,
        )
        _upsert(
            cur, project_id, work_product_id, line,
            wbs_id=row.wbs_id, name=row.name, deliverable=row.deliverable,
            start=row.start, end=row.end, weight=row.weight,
            declared_planned=row.declared_planned, actual=row.actual,
            task_key=key, key_reason=reason, estimated=plan.estimated,
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
    task_key: str | None, key_reason: str, estimated: bool,
) -> None:
    key = task_key or str(uuid.uuid4())
    cur.execute(
        """
        insert into wbs_item (project_id, wbs_id, parent_wbs_id, name, deliverable, start_on,
                              end_on, weight, declared_planned, actual, line_no,
                              work_product_id, active, task_key, key_reason, weight_estimated)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s)
        on conflict (project_id, wbs_id) do update set
          parent_wbs_id = excluded.parent_wbs_id, name = excluded.name,
          deliverable = excluded.deliverable, start_on = excluded.start_on,
          end_on = excluded.end_on, weight = excluded.weight,
          declared_planned = excluded.declared_planned, actual = excluded.actual,
          line_no = excluded.line_no, work_product_id = excluded.work_product_id,
          active = true, task_key = excluded.task_key, key_reason = excluded.key_reason,
          weight_estimated = excluded.weight_estimated, updated_at = now()
        """,
        (
            project_id, wbs_id, _parent_of(wbs_id), name[:500], deliverable, start, end,
            weight, declared_planned, actual, line, work_product_id, key, key_reason, estimated,
        ),
    )


def load_plan(cur: Any, project_id: str) -> wbs.WbsPlan | None:
    """활성 행을 파서가 내는 것과 같은 꼴로 돌려준다. 말단이 없으면 None."""
    rows = fetch_all(
        cur,
        """
        select wbs_id, name, deliverable, start_on, end_on, weight, declared_planned, actual,
               weight_estimated
          from wbs_item
         where project_id = %s and active
         order by line_no, wbs_id
        """,
        (project_id,),
    )
    leaves: list[wbs.WbsRow] = []
    groups: list[wbs.WbsGroup] = []
    estimated = False
    for r in rows:
        if r["weight"] is None:
            groups.append(
                wbs.WbsGroup(
                    wbs_id=r["wbs_id"], name=r["name"], start=r["start_on"], end=r["end_on"]
                )
            )
            continue
        declared = r["declared_planned"]
        estimated = estimated or bool(r["weight_estimated"])
        leaves.append(
            wbs.WbsRow(
                wbs_id=r["wbs_id"],
                name=r["name"],
                deliverable=r["deliverable"],
                start=r["start_on"],
                end=r["end_on"],
                weight=float(r["weight"]),
                # 비어 있으면 실적을 모른다. 0 으로 채우면 산출 불가가 0% 로 바뀐다(DEC-19)
                actual=None if r["actual"] is None else float(r["actual"]),
                declared_planned=None if declared is None else float(declared),
            )
        )
    if not leaves:
        return None
    total = round(sum(r.weight for r in leaves), 6)
    warnings: list[str] = []
    if estimated:
        warnings.append(
            "가중치 열이 없어 계획 기간에 비례해 가중치를 산정했습니다(추정). "
            "실적은 파일의 실적 열을 씁니다"
        )
    elif abs(total - 1.0) > 0.005:
        warnings.append(f"가중치 합이 1.00 이 아닙니다({total:.3f}). 합으로 나눠 맞췄습니다")
    return wbs.WbsPlan(
        rows=leaves, weight_total=total, warnings=warnings, groups=groups, estimated=estimated
    )


def save_recognition(
    cur: Any, project_id: str, work_product_id: str | None,
    plan: wbs.WbsPlan | None = None, error: str | None = None,
) -> None:
    """계획서 판을 읽은 결과(UC-030 3단계). 읽었으면 plan, 못 읽었으면 error 를 준다."""
    if plan is not None:
        values = (
            "OK", plan.header_row, Jsonb(plan.columns), len(plan.rows), len(plan.groups),
            plan.weight_total, sum(1 for r in plan.rows if not r.deliverable),
            Jsonb(plan.warnings), None,
        )
    else:
        values = ("FAILED", None, Jsonb([]), None, None, None, None, Jsonb([]), error)
    cur.execute(
        """
        insert into wbs_recognition (project_id, work_product_id, status, header_row,
                                     columns_json, leaf_count, group_count, weight_total,
                                     missing_deliverable_count, warnings_json, error, read_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (project_id) do update set
          work_product_id = excluded.work_product_id, status = excluded.status,
          header_row = excluded.header_row, columns_json = excluded.columns_json,
          leaf_count = excluded.leaf_count, group_count = excluded.group_count,
          weight_total = excluded.weight_total,
          missing_deliverable_count = excluded.missing_deliverable_count,
          warnings_json = excluded.warnings_json, error = excluded.error, read_at = now()
        """,
        (project_id, work_product_id, *values),
    )


def load_recognition(cur: Any, project_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select r.*, wp.version as plan_version
          from wbs_recognition r
          left join work_product wp on wp.id = r.work_product_id
         where r.project_id = %s
        """,
        (project_id,),
    )


def save_judgements(cur: Any, project_id: str, judgements: list) -> list[tuple[str, str, str]]:
    """판정 결과를 행에 남긴다. 시맨틱 레이어와 질의가 SQL 로 센다.

    바뀐 항목을 (wbs_id, 이전, 지금) 으로 돌려준다. 활동 기록이 이걸 본다.
    """
    before = {
        r["wbs_id"]: r["deliverable_status"]
        for r in fetch_all(
            cur,
            "select wbs_id, deliverable_status from wbs_item where project_id = %s",
            (project_id,),
        )
    }
    changed = [
        (j.wbs_id, before[j.wbs_id], j.status)
        for j in judgements if j.wbs_id in before and before[j.wbs_id] != j.status
    ]
    cur.executemany(
        """
        update wbs_item
           set deliverable_status = %s, deliverable_rule = %s, deliverable_ref = %s,
               deliverable_url = %s, deliverable_product_id = %s, judged_at = now()
         where project_id = %s and wbs_id = %s
           and (deliverable_status is distinct from %s or deliverable_rule is distinct from %s
                or deliverable_ref is distinct from %s or deliverable_url is distinct from %s
                or deliverable_product_id is distinct from %s::uuid)
        """,
        [
            (j.status, j.rule, j.ref, j.url, j.product_id, project_id, j.wbs_id,
             j.status, j.rule, j.ref, j.url, j.product_id)
            for j in judgements
        ],
    )
    return changed


def save_product_links(
    cur: Any, project_id: str, links: list[tuple[str, str | None]]
) -> None:
    """판정이 맞춘 산출물 항목만 행에 맞춘다(승인률 분자의 재료, DEC-12). 판정 상태는 그대로다."""
    if not links:
        return
    cur.executemany(
        """
        update wbs_item set deliverable_product_id = %s::uuid
         where project_id = %s and wbs_id = %s and active
           and deliverable_product_id is distinct from %s::uuid
        """,
        [(product_id, project_id, wbs_id, product_id) for wbs_id, product_id in links],
    )


def project_documents(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """올린 문서. 파일 이름 규칙과 항목 연결 규칙의 재료다. 실패·반려된 문서는 뺀다."""
    return fetch_all(
        cur,
        """
        select d.id, d.original_filename, d.wbs_item_id, d.status, d.created_at,
               d.product_type, s.proposed_type, s.status as draft_status, s.work_product_id
          from document_upload d
          left join structuring_draft s on s.document_upload_id = d.id
         where d.project_id = %s and d.status not in ('FAILED', 'REJECTED')
         order by d.created_at desc
        """,
        (project_id,),
    )


def find_item(cur: Any, project_id: str, wbs_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        "select id, wbs_id, name, deliverable from wbs_item "
        "where project_id = %s and wbs_id = %s and active",
        (project_id, wbs_id),
    )


def current_products(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """현행 산출물 항목. 경로·제목·유형 규칙의 재료다."""
    return fetch_all(
        cur,
        """
        select id, type, title, status, file_uri, external_url
          from work_product
         where project_id = %s and is_current
        """,
        (project_id,),
    )


def list_items(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """항목 화면·질의용 원본 행. 활성만."""
    return fetch_all(
        cur,
        """
        select id, wbs_id, parent_wbs_id, name, deliverable, start_on, end_on, weight,
               declared_planned, actual, line_no, work_product_id,
               deliverable_status, deliverable_rule, deliverable_ref, deliverable_url
          from wbs_item
         where project_id = %s and active
         order by line_no, wbs_id
        """,
        (project_id,),
    )


def issues_for_linking(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """WBS 항목에 이을 재료. 표준 이슈와 그 수집 원본(라벨·커스텀 필드)을 함께 읽는다.

    직접 등록한 이슈는 원본이 없어 제목만 본다.
    """
    return fetch_all(
        cur,
        """
        select i.issue_key, i.title, i.status, i.external_url, ra.payload_jsonb as payload
          from issue i
          left join raw_artifact ra
            on ra.tool_connection_id = i.tool_connection_id and ra.external_id = i.external_id
         where i.project_id = %s
         order by i.issue_key nulls last, i.created_at
        """,
        (project_id,),
    )
