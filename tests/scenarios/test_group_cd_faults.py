# ruff: noqa: E501
"""C·D 그룹의 저장 실패 롤백 (UC-021-S06, UC-032-S07) 예제 시나리오.

확정·완료 확인은 한 번 성공하면 되돌릴 수 없어, 같은 S0 을 쓰는 C·D 그룹 흐름 안에서는 명세의 시작
상태를 만들 수 없다. 이 모듈은 자기 S0 을 따로 깔고(모듈 범위 s0) 끝나면 지운다.

실패는 흐름의 뒤쪽 단계 테이블에 그 행만 막는 트리거로 주입한다(tests/fixtures/im009/db_faults.py).
트리거는 DB 이름이 axlink_test 로 끝나는 시험 DB 에만 걸리고 끝나면 지운다.
"""

from __future__ import annotations

import pytest

from app.db import fetch_all, fetch_one, tx
from tests.fixtures.im009 import data as d
from tests.fixtures.im009.db_faults import fail_insert, rejected
from tests.scenarios.conftest import auth

pytestmark = pytest.mark.db

T0 = d.T0.isoformat()


def _base(s0) -> str:
    return f"/api/projects/{s0.ids['TD-PRJ-1']}/requirement-baseline"


def _reqs(target, s0) -> dict[str, tuple]:
    res = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/requirements?size=100", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text
    return {r["code"]: (r["id"], r["title"], r["priority"], r["inBaseline"], r["status"]) for r in res.json()["content"]}


def _activity_kinds(target, s0, baseline_id: str) -> list[str]:
    res = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/activity?size=100", headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code == 200, res.text
    rows = [a for a in res.json()["content"] if a["targetType"] == "REQUIREMENT_BASELINE" and a["targetKey"] == baseline_id]
    return [a["kind"] for a in sorted(rows, key=lambda a: a["occurredAt"])]


def test_UC_021_S06_확정_실패_롤백(target, s0):
    """UC-021-S02 의 3단계(확정)에서 저장 실패 주입 → 요구사항 3행 그대로, 확정본 연결 없음, 상태 확정 대기.
    추적관계·이력·활동 기록도 그대로. 실패를 걷고 같은 확정을 다시 하면 성공한다 (AC-021-5).

    시작 상태는 S02 와 같다: TD-PRJ-1 에 기존 A·B·C, UC-020-S01 처럼 명세서(TD-DOC-1) 등록·제출.
    실패는 확정의 뒤쪽 단계(기준선 상태 이력 저장)에 건다. 그 앞에서 요구사항을 만들고 붙인 것까지
    되돌아가는지 본다."""
    pid = s0.ids["TD-PRJ-1"]
    v1, c1 = auth(s0.tokens["TD-ACC-V1"]), auth(s0.tokens["TD-ACC-C1"])
    made = target.post(_base(s0), json={"documentId": s0.ids["TD-DOC-1"]}, headers=v1)
    assert made.status_code == 201, made.text
    bid = made.json()["id"]
    sub = target.post(f"{_base(s0)}/{bid}/submit", headers=v1)
    assert sub.status_code == 200 and sub.json()["status"] == "SUBMITTED", sub.text

    def state() -> dict:
        with tx() as cur:
            counts = fetch_one(
                cur,
                """
                select (select count(*) from requirement where project_id = %(p)s) as requirements,
                       (select count(*) from entity_history where project_id = %(p)s) as history
                """,
                {"p": pid},
            )
            links = {
                tuple(r.values())
                for r in fetch_all(
                    cur,
                    "select from_type, from_id::text, to_type, to_id::text, link_kind, status "
                    "from trace_link where project_id = %s",
                    (pid,),
                )
            }
        return {
            **counts,
            "links": links,
            "reqs": _reqs(target, s0),
            "status": target.get(f"{_base(s0)}/{bid}", headers=c1).json()["status"],
            "state": target.get(_base(s0), headers=c1).json()["state"],
            "activity": _activity_kinds(target, s0, bid),
        }

    before = state()
    assert before["status"] == "SUBMITTED", before["status"]
    assert set(before["reqs"]) == {"UR.PORT.001", "UR.PORT.002", "UR.PORT.003"}, before["reqs"]
    body = {"applySpecCodes": ["UR.PORT.002"]}  # S02 2단계: 다름 B 선택
    with fail_insert("entity_history", "entity_id", bid, "baseline_confirm"):
        failed = rejected(lambda: target.post(f"{_base(s0)}/{bid}/confirm", json=body, headers=c1))
    assert failed, "저장 실패를 주입했는데 확정이 성공했다"
    after = state()
    assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert after["state"] != "CONFIRMED"

    # 재시도 성공: 실패를 걷고 같은 확정을 다시 한다
    retry = target.post(f"{_base(s0)}/{bid}/confirm", json=body, headers=c1)
    assert retry.status_code == 200 and retry.json()["status"] == "CONFIRMED", retry.text
    reqs = _reqs(target, s0)
    assert len(reqs) == 4 and sum(1 for r in reqs.values() if r[3]) == 3, reqs
    assert _activity_kinds(target, s0, bid)[-1] == "BASELINE_CONFIRMED"


def test_UC_032_S07_기록_실패_롤백(target, s0):
    """S0a → 3.2 요청·보고 뒤 확인의 기록 저장 실패 주입 → 확인 실패, 요청 상태 「조치보고」·완료 기록·
    완료 확인율(15.0%)·3.2 판정 불변 (AC-032-7).

    실패는 확인의 마지막 단계(완료 기록 저장)에 건다. 그 앞의 상태 변경·이벤트가 되돌아가야 한다."""
    s0.s0a()
    pid = s0.ids["TD-PRJ-1"]
    c1, v1 = auth(s0.tokens["TD-ACC-C1"]), auth(s0.tokens["TD-ACC-V1"])

    def completion() -> dict:
        res = target.get(f"/api/projects/{pid}/wbs/completion?at={T0}", headers=c1)
        assert res.status_code == 200, res.text
        return res.json()

    assert round(completion()["completionRate"], 4) == 0.15  # S0a: 3.1 만 확인
    req = target.post(f"/api/projects/{pid}/review-requests", json={
        "targetType": "WBS_ITEM", "targetKey": "3.2", "title": "3.2 완료 확인", "body": "",
        "purpose": "WBS_COMPLETION", "completionScope": "설계서 v1 제출·승인",
    }, headers=c1)
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    rep = target.post(f"/api/review-requests/{rid}/report", json={
        "body": "제출본 근거", "evidence": [{"kind": "WORK_PRODUCT", "ref": "", "note": "", "workProductId": s0.ids["TD-DOC-3:wp"]}],
    }, headers=v1)
    assert rep.status_code == 200, rep.text

    def state() -> dict:
        detail = target.get(f"/api/review-requests/{rid}", headers=c1).json()
        c = completion()
        item = next(i for i in c["items"] if i["wbsId"] == "3.2")
        with tx() as cur:
            n = fetch_one(cur, "select count(*) as n from review_request_event where review_request_id = %s", (rid,))["n"]
        return {
            "status": detail["status"], "records": detail["completionRecords"], "events": n,
            "rate": c["completionRate"], "item": item["completionStatus"],
        }

    before = state()
    assert before["status"] == "REPORTED", before
    with fail_insert("wbs_completion_record", "review_request_id", rid, "completion_record"):
        failed = rejected(lambda: target.post(f"/api/review-requests/{rid}/confirm", json={"acknowledgeCompletion": True, "note": "확인"}, headers=c1))
    assert failed, "저장 실패를 주입했는데 확인이 성공했다"
    after = state()
    assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert round(after["rate"], 4) == 0.15
