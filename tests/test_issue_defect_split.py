"""전체 이슈·일반 이슈·결함 구분 (DEC-02, SWFR.PIP.008, AC-041-10·AC-043-6).

결함은 연결 설정의 결함 트래커(Redmine)·결함 라벨(GitHub)로 가른다. 설정이 없으면 결함을
가르지 않는다. 전체 이슈(결함 포함) = 일반 이슈(결함 제외) + 결함이고, 셋은 따로 센다.
"""

from datetime import UTC, datetime

import pytest

from app.ai.embedding import embedding_port
from app.common import crypto, errors
from app.db import tx
from app.integration import repository as integ_repo
from app.standard import mapping, mapping_redmine
from app.standard import service as standard
from app.standard.mapping_rules import MappingRules
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- 매핑 규칙


def test_결함_매핑은_기본값이_없다():
    rules = MappingRules.from_json({})
    assert rules.defect_tracker == "" and rules.defect_label == ""
    assert not rules.has_defect_mapping
    assert "defectTracker" not in rules.to_json()


def test_결함_매핑_키를_읽고_다시_쓴다():
    rules = MappingRules.from_json({"defectTracker": "결함", "defectLabel": "유형: 결함"})
    assert rules.has_defect_mapping
    assert rules.to_json()["defectTracker"] == "결함"
    assert MappingRules.from_json(rules.to_json()) == rules


def test_결함_매핑_빈_값은_거절한다():
    with pytest.raises(errors.ApiError):
        MappingRules.from_json({"defectTracker": " "})


def test_Redmine_결함_트래커만_결함이다():
    rules = MappingRules.from_json({"defectTracker": "결함"})
    bug = {"id": 9, "subject": "오류", "tracker": {"name": "결함"}, "status": {"name": "신규"}}
    task = {"id": 8, "subject": "작업", "tracker": {"name": "일감"}, "status": {"name": "신규"}}
    assert mapping_redmine.to_issue(bug, "http://x", rules)["issue_kind"] == "DEFECT"
    assert mapping_redmine.to_issue(task, "http://x", rules)["issue_kind"] == "GENERAL"
    # 매핑이 없으면 결함 트래커라도 일반 이슈다
    assert mapping_redmine.to_issue(bug, "http://x")["issue_kind"] == "GENERAL"


def test_GitHub_결함_라벨만_결함이다():
    rules = MappingRules.from_json({"defectLabel": "유형: 결함"})
    bug = {"number": 3, "title": "오류", "state": "open", "labels": [{"name": "유형: 결함"}]}
    other = {"number": 4, "title": "개선", "state": "open", "labels": [{"name": "유형: 개선"}]}
    assert mapping.to_issue(bug, rules)["issue_kind"] == "DEFECT"
    assert mapping.to_issue(other, rules)["issue_kind"] == "GENERAL"
    assert mapping.to_issue(bug)["issue_kind"] == "GENERAL"


# ---------------------------------------------------------------- 승격·API·시맨틱


def _payload(n: int, tracker: str, closed: bool) -> dict:
    return {
        "id": 880 + n, "subject": f"DEC-02 시험 {n}", "description": "",
        "tracker": {"name": tracker},
        "status": {"name": "종료" if closed else "신규", "is_closed": closed},
        "created_on": "2026-09-01T00:00:00Z", "updated_on": "2026-09-02T00:00:00Z",
        "closed_on": "2026-09-02T00:00:00Z" if closed else None,
    }


@pytest.fixture
def split_connection():
    """결함 트래커 「결함」을 둔 Redmine 연결. 일감 3(닫힘 2) · 결함 2(닫힘 1)를 승격한다."""
    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        rules = MappingRules.from_json({"defectTracker": "결함"})
        conn = integ_repo.insert(
            cur, PID, org, "REDMINE", "DEC-02 시험", "http://localhost:3000",
            "dec02", crypto.encrypt("k"), "k***", rules.to_json(),
        )
        cid = str(conn["id"])
        job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
        items = [("일감", True), ("일감", True), ("일감", False), ("결함", True), ("결함", False)]
        for n, (tracker, closed) in enumerate(items):
            integ_repo.upsert_raw_artifact(
                cur, cid, str(880 + n), "issue", _payload(n, tracker, closed), job
            )
        result = standard.promote_connection(cur, conn, embedding_port())
        assert result.by_type == {"ISSUE": 5}
    yield cid
    with tx() as cur:
        cur.execute("delete from issue where tool_connection_id = %s", (cid,))
        cur.execute("delete from tool_connection where id = %s", (cid,))


def _preview(client, token: str, measure: str, dims: list[str]) -> dict:
    spec = {"template": "STAT_CARD", "title": "TST",
            "query": {"measure": measure, "dimensions": dims, "filters": [],
                      "projectScope": [PID]}}
    res = client.post("/api/widgets/preview", json={"spec": spec}, headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


def _value(body: dict):
    return body["total"]["values"]["value"]


@requires_db
def test_종류별로_따로_세고_포함_관계가_맞다(client, client_token, split_connection):
    token = client_token("r2")
    cid = split_connection
    one = client.get(
        f"/api/projects/{PID}/issues/summary?connectionId={cid}", headers=_auth(token)
    ).json()
    assert one["kind"] == "GENERAL" and (one["total"], one["closed"]) == (3, 2)
    k = one["kinds"]
    assert (k["allTotal"], k["generalTotal"], k["defectTotal"]) == (5, 3, 2)
    assert k["defectMapped"] and k["defectRate"] == 0.5

    defect = client.get(
        f"/api/projects/{PID}/issues/summary?connectionId={cid}&kind=DEFECT",
        headers=_auth(token),
    ).json()
    assert (defect["total"], defect["open"], defect["closed"]) == (2, 1, 1)
    rows = client.get(
        f"/api/projects/{PID}/issues?connectionId={cid}&kind=ALL&size=50", headers=_auth(token)
    ).json()
    assert rows["totalElements"] == 5
    assert sorted(r["kind"] for r in rows["content"]) == ["DEFECT"] * 2 + ["GENERAL"] * 3
    general = client.get(
        f"/api/projects/{PID}/issues?connectionId={cid}&size=50", headers=_auth(token)
    ).json()
    assert general["totalElements"] == 3
    bad = client.get(f"/api/projects/{PID}/issues?kind=WRONG", headers=_auth(token))
    assert bad.status_code == 400


@requires_db
def test_시맨틱_지표가_결함을_가른다(client, client_token, split_connection):
    token = client_token("r2")
    general = _value(_preview(client, token, "issue_count", []))
    defects = _value(_preview(client, token, "defect_count", []))
    every = _preview(client, token, "all_issue_count", ["issue_kind"])
    assert _value(every) == general + defects  # 전체는 따로 센 값이고 둘을 품는다
    by_kind = {r["values"]["d0"]: r["values"]["value"] for r in every["rows"]}
    assert by_kind["DEFECT"] == defects == 2 and by_kind["GENERAL"] == general
    rate = _preview(client, token, "defect_resolution_rate", [])
    assert (rate["total"]["values"]["numerator"], rate["total"]["values"]["denominator"]) == (1, 2)
    assert "결함 트래커" in rate["basis"]
    assert "결함 제외" in _preview(client, token, "issue_resolution_rate", [])["measureLabel"]
    prog = client.get(f"/api/projects/{PID}/progress", headers=_auth(token)).json()
    assert (prog["defect"]["numerator"], prog["defect"]["denominator"]) == (1, 2)
    assert "결함" in prog["issue"]["note"]


@requires_db
def test_매핑이_없으면_결함_처리율은_산출_불가(client, client_token):
    token = client_token("r2")
    prog = client.get(f"/api/projects/{PID}/progress", headers=_auth(token)).json()
    assert prog["defect"]["value"] is None
    assert "산출 불가" in prog["defect"]["note"]
    kinds = client.get(f"/api/projects/{PID}/issues/summary", headers=_auth(token)).json()["kinds"]
    assert not kinds["defectMapped"] and kinds["defectRate"] is None
    assert kinds["generalTotal"] == kinds["allTotal"]
    assert _value(_preview(client, token, "defect_resolution_rate", [])) is None


@requires_db
def test_스냅샷은_결함을_새로_쌓는다(client, client_token, split_connection):
    token = client_token("r2")
    res = client.post(f"/api/projects/{PID}/snapshots", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["defectResolvedCount"], body["defectTotalCount"]) == (1, 2)
