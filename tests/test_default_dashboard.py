"""진행 상황 기본 구성이 쓰는 지표와 위젯 근거 (2026-11-18 사용자 지시, SWFR.WEB.001).

기본 구성은 WBS·산출물·요구사항 세 기준 진척률을 일별로 한 그래프에 그리고, 지금 진행 중인
WBS 작업을 보인다. 세 기준 추이는 스냅샷 값을 펼친 것이라 카드(스냅샷 지표)와 같은 값이어야
한다. 위젯 근거는 명세에 같이 저장돼 고칠 때 보인다.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.common import clock
from app.db import tx
from tests.conftest import requires_db
from tests.test_answer_intents import no_snapshots  # noqa: F401 (fixture)
from tests.test_dashboard_api import dashboard_id  # noqa: F401 (fixture)

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _spec(template: str, measure: str, dims: list[str], limit: int | None = None) -> dict:
    return {
        "template": template,
        "title": "TST 기본 구성",
        "query": {"measure": measure, "dimensions": dims, "filters": [],
                  "projectScope": [PID], "limit": limit},
        "options": None,
    }


def _preview(client, token, spec) -> dict:
    res = client.post("/api/widgets/preview", json={"spec": spec}, headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


@requires_db
def test_세_기준_일별_추이는_스냅샷_값을_펼친다(client, client_token, no_snapshots):  # noqa: F811
    with tx() as cur:
        for day, wbs, dl, req in (
            (date(2026, 10, 1), 40.0, (2, 10), (1, 4)),
            (date(2026, 10, 2), 45.5, (3, 10), (2, 4)),
            (date(2026, 10, 3), 50.0, (0, 0), (2, 4)),  # 산출물 대상이 없는 날은 그 선만 비운다
        ):
            cur.execute(
                """
                insert into progress_snapshot (project_id, snapshot_date, level, representative_pct,
                       wbs_actual_pct, deliverable_approved_count, deliverable_total_count,
                       requirement_verified_count, requirement_total_count)
                values (%s, %s, 'L1', %s, %s, %s, %s, %s, %s)
                """,
                (PID, day, wbs, wbs, *dl, *req),
            )
    token = client_token("r2")
    body = _preview(
        client, token,
        _spec("LINE_CHART", "progress_metric_pct", ["period_day", "progress_metric"], 400),
    )
    got = {
        (r["values"]["d0"], r["values"]["d1"]): float(r["values"]["value"]) for r in body["rows"]
    }
    assert got == {
        ("2026-10-01", "WBS 진척률"): 40.0,
        ("2026-10-01", "산출물 승인률"): 20.0,
        ("2026-10-01", "요구사항 이행률"): 25.0,
        ("2026-10-02", "WBS 진척률"): 45.5,
        ("2026-10-02", "산출물 승인률"): 30.0,
        ("2026-10-02", "요구사항 이행률"): 50.0,
        ("2026-10-03", "WBS 진척률"): 50.0,
        ("2026-10-03", "요구사항 이행률"): 50.0,
    }

    # 카드(스냅샷 지표)는 같은 스냅샷의 가장 최근 값이다. 그래프 마지막 점과 맞아야 한다
    def card(measure: str) -> float:
        b = _preview(client, token, _spec("STAT_CARD", measure, []))
        row = b["rows"][0] if b["rows"] else b["total"]
        return float(row["values"]["value"])

    assert card("progress_wbs_pct") == got[("2026-10-03", "WBS 진척률")]
    assert card("snapshot_requirement_fulfillment_pct") == got[("2026-10-03", "요구사항 이행률")]
    assert card("snapshot_work_product_approval_pct") == got[("2026-10-02", "산출물 승인률")]


@pytest.fixture
def wbs_tasks():
    """시작일·실적이 다른 말단 작업 넷. 진행 중으로 잡혀야 하는 것은 둘이다."""
    today = clock.today()
    d = timedelta
    rows = [
        ("TST-W1", "TST 진행 중 작업", today - d(days=3), today + d(days=5), 0.4),
        ("TST-W2", "TST 기한 지난 미완료", today - d(days=20), today - d(days=2), 0.7),
        ("TST-W3", "TST 시작 전 작업", today + d(days=2), today + d(days=9), 0),
        ("TST-W4", "TST 끝난 작업", today - d(days=10), today - d(days=1), 1),
    ]
    ids = [str(uuid.uuid4()) for _ in rows]
    with tx() as cur:
        for n, (iid, (wbs_id, name, start, end, actual)) in enumerate(zip(ids, rows, strict=True)):
            cur.execute(
                """
                insert into wbs_item (id, project_id, wbs_id, name, start_on, end_on, weight,
                                      actual, line_no, active)
                values (%s, %s, %s, %s, %s, %s, 1, %s, %s, true)
                """,
                (iid, PID, wbs_id, name, start, end, actual, 9000 + n),
            )
    yield
    with tx() as cur:
        cur.execute("delete from wbs_item where id = any(%s::uuid[])", (ids,))


@requires_db
def test_진행_중_작업은_시작했고_안_끝난_것만이다(client, client_token, wbs_tasks):
    body = _preview(
        client, client_token("r2"), _spec("PROGRESS_LIST", "wbs_task_actual_pct", ["wbs_task"])
    )
    got = {r["values"]["d0"]: float(r["values"]["value"]) for r in body["rows"]}
    assert got["TST-W1 TST 진행 중 작업"] == 40.0
    assert got["TST-W2 TST 기한 지난 미완료"] == 70.0  # 기한이 지났어도 안 끝났으면 남는다
    assert "TST-W3 TST 시작 전 작업" not in got
    assert "TST-W4 TST 끝난 작업" not in got


@requires_db
def test_위젯_근거는_명세와_같이_저장된다(client, client_token, dashboard_id):  # noqa: F811
    r2 = _auth(client_token("r2"))
    spec = {**_spec("STAT_CARD", "progress_wbs_pct", ["period_day"]),
            "rationale": "WBS 실적을 가중치로 합친 값. 스냅샷 기준"}
    grid = {"i": "", "x": 0, "y": 0, "w": 3, "h": 2, "minW": 3, "minH": 2}
    res = client.post(
        f"/api/dashboards/{dashboard_id}/widgets", json={"spec": spec, "gridItem": grid},
        headers=r2,
    )
    assert res.status_code == 201, res.text
    widget = res.json()
    assert widget["spec"]["rationale"] == "WBS 실적을 가중치로 합친 값. 스냅샷 기준"

    detail = client.get(f"/api/dashboards/{dashboard_id}", headers=r2).json()
    saved = next(w for w in detail["widgets"] if w["id"] == widget["id"])
    assert saved["spec"]["rationale"] == "WBS 실적을 가중치로 합친 값. 스냅샷 기준"
