"""이슈 심각도 미지정 (GH-116, SWFR.PIP.002).

원천에 심각도가 없으면 null(미지정)이다. 고위험 집계에서 빼고 따로 세며, 낮은 위험으로
정렬하거나 말하지 않는다. Redmine 우선순위는 심각도로 바꾸지 않고 원문으로 남긴다.
"""

import uuid

import pytest

from app.db import fetch_one, tx
from app.rag import answer, entity_table
from app.standard import mapping, mapping_redmine
from app.standard import repository as standard_repo
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- 새 수집(매핑)


def test_GitHub_이슈는_심각도를_지어내지_않는다():
    rec = mapping.to_issue({"number": 7, "title": "작업", "state": "open", "labels": []})
    assert rec["severity"] is None and rec["source_priority"] is None


@pytest.mark.parametrize("priority", ["낮음", "보통", "높음", "긴급", "즉시"])
def test_Redmine_우선순위는_심각도로_바꾸지_않고_원문으로_남긴다(priority):
    rec = mapping_redmine.to_issue(
        {"id": 3, "subject": "결함", "status": {"name": "신규"}, "priority": {"name": priority}},
        "https://redmine.example.invalid",
    )
    assert rec["severity"] is None
    assert rec["source_priority"] == priority


def test_AI_는_미지정을_낮은_위험으로_말하지_않는다():
    assert "미지정" in answer.SYSTEM_PROMPT and "낮은 위험" in answer.SYSTEM_PROMPT


# ---------------------------------------------------------------- 적재·집계


@pytest.fixture
def connection():
    with tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn_id = str(uuid.uuid4())
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'GITHUB', 'TST', 'https://api.github.invalid/', 'sev/test',
                    'x', 'x', 'ACTIVE')
            """,
            (conn_id, PID, org["id"]),
        )
    yield conn_id
    with tx() as cur:
        cur.execute("delete from issue where tool_connection_id = %s", (conn_id,))
        cur.execute("delete from issue where issue_key like 'SEV-%%' and project_id = %s", (PID,))
        cur.execute("delete from tool_connection where id = %s", (conn_id,))


def _collect(cur, conn_id: str, number: int, state: str = "open") -> str:
    """새 수집과 같은 길(매핑 → upsert)로 GitHub 이슈 하나를 올린다."""
    rec = mapping.to_issue({"number": number, "title": f"수집 {number}", "state": state,
                            "labels": [], "html_url": "https://example.invalid"})
    return standard_repo.upsert_issue(cur, PID, conn_id, str(number), rec)


def _manual(cur, key: str, severity: str, status: str = "OPEN") -> None:
    cur.execute(
        """
        insert into issue (project_id, issue_key, title, status, severity, source_kind)
        values (%s, %s, %s, %s, %s, 'MANUAL')
        """,
        (PID, key, f"수기 {key}", status, severity),
    )


@requires_db
def test_수집하면_미지정이고_재수집이_예전_기본값을_고친다(connection):
    with tx() as cur:
        iid = _collect(cur, connection, 90001)
        row = fetch_one(cur, "select severity, source_priority from issue where id = %s", (iid,))
        assert row["severity"] is None and row["source_priority"] is None
        # 예전 매핑이 넣던 MAJOR 가 남아 있어도 다음 수집이 원천대로 되돌린다
        cur.execute("update issue set severity = 'MAJOR' where id = %s", (iid,))
        _collect(cur, connection, 90001)
        again = fetch_one(cur, "select severity from issue where id = %s", (iid,))
        assert again["severity"] is None


@requires_db
def test_카드는_미지정을_고위험에서_빼고_따로_센다(client, client_token, connection):
    token = client_token("r2")
    before = client.get(f"/api/projects/{PID}/issues/summary", headers=_auth(token)).json()
    with tx() as cur:
        _collect(cur, connection, 90002)            # 미지정, 열림
        _collect(cur, connection, 90003, "closed")  # 미지정, 닫힘(카드 밖)
        _manual(cur, "SEV-1", "CRITICAL")            # 명시, 열림
        _manual(cur, "SEV-2", "MINOR")               # 명시, 열림, 고위험 아님
    got = client.get(f"/api/projects/{PID}/issues/summary", headers=_auth(token)).json()
    assert got["heavyOpen"] == before["heavyOpen"] + 1
    assert got["unspecifiedOpen"] == before["unspecifiedOpen"] + 1
    assert got["open"] == before["open"] + 3

    listed = client.get(f"/api/projects/{PID}/issues?q=수집 90002", headers=_auth(token)).json()
    [item] = listed["content"]
    assert item["severity"] is None and item["sourcePriority"] is None


@requires_db
def test_위젯은_미지정을_따로_묶는다(client, client_token, connection):
    with tx() as cur:
        _collect(cur, connection, 90004)
        _manual(cur, "SEV-3", "MAJOR")
    res = client.post(
        "/api/widgets/preview",
        json={"spec": {"template": "BAR_CHART", "title": "심각도별",
                       "query": {"measure": "open_issue_count", "dimensions": ["issue_severity"],
                                 "filters": [], "projectScope": [PID]},
                       "options": {}}},
        headers=_auth(client_token("r2")),
    )
    assert res.status_code == 200, res.text
    rows = {r["values"]["d0"]: r["values"].get("d0_label") for r in res.json()["rows"]}
    assert rows.get("UNSPECIFIED") == "미지정"
    assert rows.get("MAJOR") == "중대"
    # 미지정만 골라 볼 수도 있다
    res = client.post(
        "/api/widgets/preview",
        json={"spec": {"template": "STAT_CARD", "title": "미지정",
                       "query": {"measure": "open_issue_count", "dimensions": [],
                                 "filters": [{"field": "issue_severity", "op": "IN",
                                              "value": ["UNSPECIFIED"]}],
                                 "projectScope": [PID]},
                       "options": {}}},
        headers=_auth(client_token("r2")),
    )
    assert res.status_code == 200, res.text


@requires_db
def test_AI_목록은_미지정을_등급_사이에_끼우지_않고_별도_묶음으로_둔다(connection):
    with tx() as cur:
        _manual(cur, "SEV-4", "TRIVIAL")
        _manual(cur, "SEV-5", "MINOR")
        _collect(cur, connection, 90005)
        _manual(cur, "SEV-6", "MAJOR")
        table = entity_table.build(cur, "ISSUE", entity_table.OPEN, [PID], 500)
    order = [r.values["severity"] for r in table.data.rows]
    unspecified = [i for i, s in enumerate(order) if s == "미지정"]
    specified = [i for i, s in enumerate(order) if s != "미지정"]
    # 지정된 것이 모두 먼저, 미지정은 그 뒤 한 묶음이다
    assert max(specified) < min(unspecified)
    ranks = ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "TRIVIAL"]
    seen = [ranks.index(order[i]) for i in specified]
    assert seen == sorted(seen)
    assert any("심각도 미지정" in line for line in table.lines)
    assert "미지정은 위험 등급이 아니다" in table.scope_line
