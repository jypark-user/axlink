"""대시보드·위젯 API (SWFR.WEB.001). 프런트가 부르는 경로와 응답 모양을 그대로 본다.

값은 전부 DB 집계다. 시드 이슈를 넣고 위젯이 그 수를 그대로 세는지 확인한다.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _spec(measure: str, dims: list[str], template: str = "BAR_CHART", title: str = "t") -> dict:
    return {
        "template": template,
        "title": title,
        "query": {
            "measure": measure,
            "dimensions": dims,
            "filters": [],
            "projectScope": [PID],
            "limit": None,
        },
        "options": {
            "unit": None, "sort": "desc", "threshold": None, "stacked": None,
            "showLegend": None, "compareWithPrevious": None, "columns": None,
        },
    }


@pytest.fixture
def dashboard_id(client, client_token) -> str:
    res = client.get(f"/api/dashboards?projectId={PID}", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    boards = res.json()
    default = next(b for b in boards if b["isDefault"])
    yield default["id"]
    # 이 스위트가 만든 위젯은 지우고 레이아웃도 되돌린다
    with tx() as cur:
        cur.execute("delete from widget where dashboard_id = %s and title like 'TST %%'",
                    (default["id"],))
        cur.execute(
            "update dashboard set layout_json = '{\"version\":1,\"lg\":[],\"md\":[],\"sm\":[]}'"
            " where id = %s",
            (default["id"],),
        )


@pytest.fixture
def seeded_issues():
    """열린 이슈 3건(MAJOR 2·CRITICAL 1), 닫힌 이슈 1건."""
    ids = [str(uuid.uuid4()) for _ in range(4)]
    now = datetime.now(UTC)
    with tx() as cur:
        for iid, status, severity, resolved in (
            (ids[0], "OPEN", "MAJOR", None),
            (ids[1], "IN_PROGRESS", "MAJOR", None),
            (ids[2], "OPEN", "CRITICAL", None),
            (ids[3], "CLOSED", "MINOR", now),
        ):
            cur.execute(
                """
                insert into issue (id, project_id, title, status, severity, resolved_at,
                                   source_created_at)
                values (%s, %s, 'TST 이슈', %s, %s, %s, %s)
                """,
                (iid, PID, status, severity, resolved, now),
            )
    yield ids
    with tx() as cur:
        cur.execute("delete from issue where id = any(%s::uuid[])", (ids,))


@requires_db
def test_사업의_기본_대시보드를_찾는다(client, client_token, dashboard_id):
    res = client.get(f"/api/dashboards/{dashboard_id}", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["projectId"] == PID and body["isDefault"] is True
    assert set(body["layout"]) == {"lg", "md", "sm"}
    assert body["editable"] is True  # 발주기관 담당자는 기본 대시보드를 꾸민다


@requires_db
def test_용역사는_보기만_한다(client, client_token, dashboard_id):
    r3 = _auth(client_token("r3"))
    assert client.get(f"/api/dashboards/{dashboard_id}", headers=r3).json()["editable"] is False
    res = client.post(
        f"/api/dashboards/{dashboard_id}/widgets",
        json={"spec": _spec("open_issue_count", ["issue_severity"], title="TST x"),
              "gridItem": None},
        headers=r3,
    )
    assert res.status_code == 403
    assert res.json()["code"] == "ROLE_FORBIDDEN"


@requires_db
def test_위젯_생명주기와_레이아웃(client, client_token, dashboard_id):
    r2 = _auth(client_token("r2"))
    grid = {"i": "", "x": 0, "y": 0, "w": 6, "h": 4, "minW": 3, "minH": 3}
    res = client.post(
        f"/api/dashboards/{dashboard_id}/widgets",
        json={"spec": _spec("open_issue_count", ["issue_severity"], title="TST 위젯"),
              "gridItem": grid},
        headers=r2,
    )
    assert res.status_code == 201, res.text
    widget = res.json()
    assert widget["template"] == "BAR_CHART" and widget["spec"]["title"] == "TST 위젯"

    # 자리는 서버 레이아웃에 위젯 id 로 박힌다 (설계 제약 4)
    detail = client.get(f"/api/dashboards/{dashboard_id}", headers=r2).json()
    assert [g["i"] for g in detail["layout"]["lg"]] == [widget["id"]]
    assert detail["layout"]["lg"][0]["w"] == 6

    # 명세 수정
    res = client.patch(
        f"/api/widgets/{widget['id']}",
        json={"spec": _spec("open_issue_count", [], template="STAT_CARD", title="TST 카드")},
        headers=r2,
    )
    assert res.status_code == 200, res.text
    assert res.json()["template"] == "STAT_CARD"

    # 레이아웃 교체. 없는 위젯을 가리키면 거부
    layout = {"lg": [{**grid, "i": widget["id"], "x": 3}], "md": [], "sm": []}
    res = client.put(f"/api/dashboards/{dashboard_id}/layout", json={"layout": layout}, headers=r2)
    assert res.status_code == 200 and res.json()["layout"]["lg"][0]["x"] == 3
    bad = {"lg": [{**grid, "i": str(uuid.uuid4())}], "md": [], "sm": []}
    res = client.put(f"/api/dashboards/{dashboard_id}/layout", json={"layout": bad}, headers=r2)
    assert res.status_code == 400

    # 삭제하면 자리도 빠진다
    assert client.delete(f"/api/widgets/{widget['id']}", headers=r2).status_code == 204
    detail = client.get(f"/api/dashboards/{dashboard_id}", headers=r2).json()
    assert detail["widgets"] == [] and detail["layout"]["lg"] == []
    assert client.post(f"/api/widgets/{widget['id']}/data", json={}, headers=r2).status_code == 404


@requires_db
def test_카탈로그에_없는_지표는_저장되지_않는다(client, client_token, dashboard_id):
    res = client.post(
        f"/api/dashboards/{dashboard_id}/widgets",
        json={"spec": _spec("made_up", [], title="TST 없음"), "gridItem": None},
        headers=_auth(client_token("r2")),
    )
    assert res.status_code == 400
    assert res.json()["code"] == "CATALOG_VALIDATION_FAILED"


@requires_db
def test_위젯_값은_DB_집계와_같다(client, client_token, dashboard_id, seeded_issues):
    r2 = _auth(client_token("r2"))
    created = client.post(
        f"/api/dashboards/{dashboard_id}/widgets",
        json={"spec": _spec("open_issue_count", ["issue_severity"], title="TST 심각도"),
              "gridItem": None},
        headers=r2,
    ).json()
    res = client.post(f"/api/widgets/{created['id']}/data", json={}, headers=r2)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["measure"] == "open_issue_count" and body["unit"] == "건"
    # 심각도 차원은 표시 이름(d0_label)도 낸다. 미지정을 '미지정'으로 보이기 위해서다(GH-116)
    assert [c["key"] for c in body["columns"]] == ["d0", "d0_label", "value"]
    by_sev = {r["values"]["d0"]: r["values"]["value"] for r in body["rows"]}

    with tx() as cur:
        expected = fetch_one(
            cur,
            "select count(*) filter (where severity = 'MAJOR') as major,"
            " count(*) filter (where severity = 'CRITICAL') as critical"
            " from issue where project_id = %s and status in ('OPEN','IN_PROGRESS')",
            (PID,),
        )
    assert by_sev["MAJOR"] == expected["major"] >= 2
    assert by_sev["CRITICAL"] == expected["critical"] >= 1
    assert body["appliedProjectIds"] == [PID]
    assert body["truncated"] is False

    # 용역사도 값은 본다 (읽기 전용)
    assert client.post(
        f"/api/widgets/{created['id']}/data", json={}, headers=_auth(client_token("r3"))
    ).status_code == 200


@requires_db
def test_숫자_카드는_기간_축이_있어도_전체값을_함께_준다(client, client_token, seeded_issues):
    spec = _spec("issue_count", ["period_month"], template="STAT_CARD")
    res = client.post(
        "/api/widgets/preview", json={"spec": spec}, headers=_auth(client_token("r2"))
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rows"], "월별 행이 있어야 한다"
    assert body["total"]["values"]["value"] >= 4  # 시드 4건 이상
    assert body["columns"][0]["type"] == "date"


@requires_db
def test_이전_구간_비교는_같은_길이의_직전_구간이다(client, client_token, seeded_issues):
    spec = _spec("issue_count", [], template="STAT_CARD")
    spec["query"]["filters"] = [{"field": "period", "op": "LAST_N_DAYS", "value": 7}]
    spec["options"]["compareWithPrevious"] = True
    body = client.post("/api/widgets/preview", json={"spec": spec},
                       headers=_auth(client_token("r2"))).json()
    assert body["total"]["values"]["value"] >= 4
    assert body["previousTotal"] is not None and "value" in body["previousTotal"]["values"]


# 프런트 추천 구성(dashboard-presets.ts)이 쓰는 지표 × 차원 × 템플릿 전부.
# 하나라도 안 돌면 화면의 「추천 구성 적용」이 중간에 죽는다.
PRESET_WIDGETS = [
    ("STAT_CARD", "schedule_variance_pct", ["period_month"]),
    ("BULLET_CHART", "issue_resolution_rate", ["contractor_org"]),
    ("SPARKLINE", "issue_count", ["period_month", "issue_status"]),
    ("LINE_CHART", "test_pass_rate", ["period_month"]),
    ("AREA_CHART", "issue_resolution_rate", ["period_week"]),
    ("CUMULATIVE_FLOW", "issue_count", ["period_month", "issue_status"]),
    ("CALENDAR_HEATMAP", "code_activity_count", ["period_day"]),
    ("BAR_CHART", "open_issue_count", ["issue_severity"]),
    ("PARETO", "open_issue_count", ["assignee"]),
    ("STACKED_BAR_CHART", "issue_count", ["contractor_org", "issue_severity"]),
    ("HEATMAP", "work_product_missing_count", ["iso_activity", "work_product_type"]),
    ("TREEMAP", "work_product_missing_count", ["work_product_type"]),
    ("PIE_CHART", "open_risk_count", ["risk_status"]),
    ("DONUT_CHART", "requirement_fulfillment_rate", ["requirement_priority"]),
    ("STATUS_FLOW", "requirement_fulfillment_rate", ["requirement_status"]),
    ("RADAR_CHART", "work_product_approval_rate", ["iso_activity"]),
    ("SLOPE_CHART", "issue_count", ["period_month", "contractor_org"]),
    ("BUMP_CHART", "issue_count", ["period_month", "issue_severity"]),
    ("PROGRESS_LIST", "requirement_fulfillment_rate", ["contractor_org"]),
    ("HORIZONTAL_BAR_CHART", "work_product_approval_rate", ["work_product_type"]),
    ("CHECKLIST", "work_product_approval_rate", ["work_product_type"]),
    ("DATA_TABLE", "issue_avg_resolution_days", ["assignee"]),
    ("STAT_CARD", "requirement_fulfillment_rate", ["period_month"]),
    ("STAT_CARD", "work_product_approval_rate", []),
    ("STATUS_FLOW", "work_product_approval_rate", ["work_product_status"]),
    ("STAT_CARD", "requirement_test_trace_rate", []),
    ("STAT_CARD", "issue_avg_resolution_days", []),
    ("STACKED_BAR_CHART", "open_issue_count", ["contractor_org", "issue_severity"]),
    ("HORIZONTAL_BAR_CHART", "open_issue_count", ["assignee"]),
    ("RADAR_CHART", "issue_resolution_rate", ["contractor_org"]),
    ("DONUT_CHART", "open_risk_count", ["risk_severity"]),
]


@requires_db
@pytest.mark.parametrize("template,measure,dims", PRESET_WIDGETS)
def test_추천_구성의_모든_위젯이_돈다(client, client_token, template, measure, dims):
    spec = _spec(measure, dims, template=template)
    res = client.post(
        "/api/widgets/preview", json={"spec": spec}, headers=_auth(client_token("r2"))
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["measure"] == measure and body["dimensions"] == dims
    assert body["columns"][-1]["key"] == "value"


@requires_db
def test_카탈로그를_준다(client, client_token):
    res = client.get("/api/semantic/catalog", headers=_auth(client_token("r3")))
    assert res.status_code == 200
    body = res.json()
    keys = {m["key"] for m in body["measures"]}
    assert {"open_issue_count", "issue_count", "work_product_approval_rate"} <= keys
    assert {d["key"] for d in body["dimensions"]} >= {"period_day", "project"}
    assert any(f["key"] == "period__last_n_days" for f in body["filters"])
