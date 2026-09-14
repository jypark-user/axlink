"""일별 스냅샷 (SWFR.PIP.005). 오늘 찍은 값이 추이 위젯의 한 점이 되는지 본다."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded_issues():
    """닫힌 2건, 열린 1건. 해결률 66.67%."""
    ids = [str(uuid.uuid4()) for _ in range(3)]
    now = datetime.now(UTC)
    with tx() as cur:
        for iid, status, resolved in (
            (ids[0], "CLOSED", now),
            (ids[1], "RESOLVED", now),
            (ids[2], "OPEN", None),
        ):
            cur.execute(
                "insert into issue (id, project_id, title, status, resolved_at)"
                " values (%s, %s, 'TST', %s, %s)",
                (iid, PID, status, resolved),
            )
    yield ids
    with tx() as cur:
        cur.execute("delete from issue where id = any(%s::uuid[])", (ids,))
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))


def _preview(client, token: str, measure: str, dims: list[str], template: str = "STAT_CARD"):
    spec = {
        "template": template, "title": "t",
        "query": {"measure": measure, "dimensions": dims, "filters": [],
                  "projectScope": [PID], "limit": None},
        "options": None,
    }
    res = client.post("/api/widgets/preview", json={"spec": spec}, headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


@requires_db
def test_스냅샷은_그날의_집계를_그대로_담는다(client, client_token, seeded_issues):
    token = client_token("r2")
    res = client.post(f"/api/projects/{PID}/snapshots", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["snapshotDate"] == date.today().isoformat()
    assert body["workProductTotalCount"] == 22

    with tx() as cur:
        expected = fetch_one(
            cur,
            "select count(*) filter (where status in ('RESOLVED','CLOSED')) as done,"
            " count(*) as total from issue where project_id = %s",
            (PID,),
        )
    assert body["issueResolvedCount"] == expected["done"] >= 2
    assert body["issueTotalCount"] == expected["total"] >= 3
    # WBS 가 없으면 이슈로 내려간다 (진척률-산정체계 L3)
    assert body["level"] in ("L1", "L3")
    assert body["representativePct"] is not None


@requires_db
def test_같은_날_다시_찍으면_덮어쓴다(client, client_token, seeded_issues):
    token = client_token("r2")
    first = client.post(f"/api/projects/{PID}/snapshots", headers=_auth(token)).json()
    with tx() as cur:
        cur.execute("update issue set status = 'CLOSED', resolved_at = now() where id = %s",
                    (seeded_issues[2],))
    second = client.post(f"/api/projects/{PID}/snapshots", headers=_auth(token)).json()
    assert second["issueResolvedCount"] == first["issueResolvedCount"] + 1
    with tx() as cur:
        row = fetch_one(
            cur,
            "select count(*) as n from progress_snapshot"
            " where project_id = %s and snapshot_date = current_date",
            (PID,),
        )
    assert row["n"] == 1


@requires_db
def test_스냅샷이_추이_위젯의_점이_된다(client, client_token, seeded_issues):
    token = client_token("r2")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.post(f"/api/projects/{PID}/snapshots?at={yesterday}", headers=_auth(token))
    client.post(f"/api/projects/{PID}/snapshots", headers=_auth(token))

    trend = _preview(client, token, "progress_issue_pct", ["period_day"], "LINE_CHART")
    days = [r["values"]["d0"] for r in trend["rows"]]
    assert days[-2:] == [yesterday, date.today().isoformat()]  # 시간순

    with tx() as cur:
        row = fetch_one(
            cur,
            "select round(100.0 * issue_resolved_count / issue_total_count, 2) as pct"
            " from progress_snapshot where project_id = %s and snapshot_date = current_date",
            (PID,),
        )
    assert trend["rows"][-1]["values"]["value"] == float(row["pct"])

    # 기간 축 없이 물으면 가장 최근 값. 평균이 아니다.
    latest = _preview(client, token, "progress_issue_pct", [])
    assert latest["total"]["values"]["value"] == float(row["pct"])
    assert latest["unit"] == "%"


# 진척 세 갈래(SWFR.PIP.006~009)가 카탈로그 지표로 위젯이 되는지. 하나라도 안 돌면 추이 화면이 죽는다.
PROGRESS_WIDGETS = [
    ("STAT_CARD", "progress_representative_pct", []),
    ("LINE_CHART", "progress_wbs_pct", ["period_day"]),
    ("LINE_CHART", "progress_planned_pct", ["period_week"]),
    ("STAT_CARD", "progress_variance_pct", []),
    ("STAT_CARD", "progress_behind_task_count", []),
    ("AREA_CHART", "progress_issue_pct", ["period_month"]),
    ("AREA_CHART", "progress_work_product_pct", ["period_month"]),
    ("LINE_CHART", "snapshot_requirement_fulfillment_pct", ["period_day"]),
    ("LINE_CHART", "snapshot_risk_closed_pct", ["period_day"]),
    ("BULLET_CHART", "snapshot_work_product_approval_pct", []),
]


@requires_db
@pytest.mark.parametrize("template,measure,dims", PROGRESS_WIDGETS)
def test_진척_지표가_위젯으로_나온다(client, client_token, template, measure, dims):
    body = _preview(client, client_token("r2"), measure, dims, template)
    assert body["measure"] == measure and body["columns"][-1]["key"] == "value"


@requires_db
def test_카탈로그에_진척_지표가_있다(client, client_token):
    body = client.get("/api/semantic/catalog", headers=_auth(client_token("r3"))).json()
    keys = {m["key"] for m in body["measures"]}
    assert {"progress_wbs_pct", "progress_issue_pct", "progress_work_product_pct"} <= keys


@requires_db
def test_접근_없는_사업은_찍지_못한다(client, client_token):
    other = "c0000000-0000-4000-8000-000000000099"
    res = client.post(f"/api/projects/{other}/snapshots", headers=_auth(client_token("r3")))
    assert res.status_code == 403
