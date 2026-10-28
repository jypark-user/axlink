"""연결별 매핑 규칙 (SWFR.CON.002) — 코드 수정 없이 설정으로.

업체마다 다른 판별 이름(요구사항 라벨·리스크 트래커·REQ ID 필드명)만 설정이고,
매핑 논리는 코드에 남는다. 기본값은 종전 하드코딩과 같아야 한다 — 설정 도입이
기존 연결의 동작을 바꾸면 안 된다.
"""

from datetime import UTC, datetime

import pytest

from app.common import crypto, errors
from app.db import tx
from app.integration import repository as integ_repo
from app.standard import mapping_redmine
from app.standard import service as standard
from app.standard.mapping_rules import MappingRules
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


# ── 규칙 파싱

def test_비어_있으면_기본값이고_기본값은_종전과_같다():
    rules = MappingRules.from_json(None)
    assert rules == MappingRules.from_json({})
    assert rules.risk_tracker == "리스크"
    assert rules.req_id_field == "REQ ID"


def test_파일럿_형식은_기본값으로_읽는다():
    """V1 컬럼 기본값({"version":1,"rules":[]})이 남은 행 — 수집이 여기서 죽으면 안 된다.
    실제로 2026-09-09 검수 중 이 형식 때문에 수집이 실패했다."""
    rules = MappingRules.from_json({"version": 1, "rules": []})
    assert rules == MappingRules()


def test_모르는_키는_오타로_거절한다():
    with pytest.raises(errors.ApiError):
        MappingRules.from_json({"riskTraker": "위험"})  # 오타
    with pytest.raises(errors.ApiError):
        MappingRules.from_json({"riskTracker": ""})  # 빈 값


def test_예전_요구사항_라벨_키는_받기만_하고_쓰지_않는다():
    """ARC-030 전 설정에 남은 키. 거절하면 그 연결의 수집이 멈춘다. 저장할 때는 빠진다."""
    rules = MappingRules.from_json({"requirementLabel": "Requirement", "riskTracker": "위험"})
    assert rules.risk_tracker == "위험"
    assert "requirementLabel" not in rules.to_json()


# ── 판별이 규칙을 따른다


def test_리스크_트래커와_REQ_ID_필드를_바꿀_수_있다():
    payload = {
        "tracker": {"name": "위험"},
        "custom_fields": [{"name": "요구사항ID", "value": "SWFR.CON.002"}],
    }
    assert not mapping_redmine.is_risk(payload)
    rules = MappingRules.from_json({"riskTracker": "위험", "reqIdField": "요구사항ID"})
    assert mapping_redmine.is_risk(payload, rules)
    assert mapping_redmine.req_id(payload, rules) == "SWFR.CON.002"
    assert mapping_redmine.req_id(payload) is None


# ── API — 등록·변경 (시험 DB)

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@requires_db
def test_등록과_변경이_설정으로_된다(client, client_token, monkeypatch):
    token = client_token("r3")
    body = {
        "tool": "GITHUB", "name": "규칙 시험", "baseUrl": "https://api.github.com",
        "targetResource": "o/r", "credential": {"accessToken": "t"},
        "mappingRules": {"reqIdField": "요구사항ID"},
    }
    created = client.post(f"/api/projects/{PID}/connections", json=body, headers=_auth(token))
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    try:
        assert created.json()["mappingRuleCount"] == 2  # 기본값 포함 전체 저장

        # 변경 — 코드 수정 없이
        res = client.patch(
            f"/api/connections/{cid}/mapping",
            json={"mappingRules": {"riskTracker": "위험"}},
            headers=_auth(token),
        )
        assert res.status_code == 200

        # 오타는 저장 전에 거절
        bad = client.patch(
            f"/api/connections/{cid}/mapping",
            json={"mappingRules": {"riskTraker": "위험"}},
            headers=_auth(token),
        )
        assert bad.status_code == 400
    finally:
        with tx() as cur:
            cur.execute("delete from tool_connection where id = %s", (cid,))


# ── 승격이 연결의 규칙을 읽는다 (시험 DB)

@requires_db
def test_승격이_연결_설정을_따른다(client):
    from app.ai.embedding import embedding_port

    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        rules = MappingRules.from_json({"riskTracker": "위험"})
        conn = integ_repo.insert(
            cur, PID, org, "REDMINE", "레드마인", "http://localhost:3000",
            "axlink", crypto.encrypt("k"), "k***", rules.to_json(),
        )
        cid = str(conn["id"])
        try:
            job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
            payload = {
                "id": 9, "subject": "위험 하나", "description": "",
                "tracker": {"name": "위험"},
                "status": {"name": "신규", "is_closed": False},
                "created_on": "2026-09-09T00:00:00Z",
            }
            integ_repo.upsert_raw_artifact(cur, cid, "9", "issue", payload, job)

            result = standard.promote_connection(cur, conn, embedding_port())

            assert result.by_type == {"RISK": 1}  # 기본 규칙이면 ISSUE 로 갔을 것이다
        finally:
            cur.execute("delete from tool_connection where id = %s", (cid,))
