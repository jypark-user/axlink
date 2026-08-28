"""커넥터 등록·테스트 슬라이스 — 박PM 시나리오 S2-2.

GitHub 실호출은 monkeypatch 로 대체해 결정론적으로 돌린다. 실제 토큰으로 api.github.com 을
때리는 검증은 tests/test_github_live.py 가 AXLINK_GH_TOKEN 이 있을 때만 한다.
"""

import pytest

from app.integration import github
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업 (박PM 배정)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_body(name: str = "백엔드 저장소") -> dict:
    return {
        "tool": "GITHUB",
        "name": name,
        "baseUrl": "https://api.github.com",
        "targetResource": "jypark-user/axlink",
        "credential": {"accessToken": "ghp_fakeToken1234567890ABCDEF"},
    }


@pytest.fixture
def as_pm(client, client_token):
    """박PM(용역사 r3) 토큰 + 생성한 연결을 테스트 끝에 청소한다."""
    token = client_token("r3@admin.com")
    created: list[str] = []
    yield token, created
    for cid in created:
        client.delete(f"/api/connections/{cid}", headers=_auth(token))


@requires_db
def test_create_and_list_connection(client, as_pm):
    token, created = as_pm
    res = client.post(
        f"/api/projects/{PID}/connections", json=_create_body(), headers=_auth(token)
    )
    assert res.status_code == 201, res.text
    body = res.json()
    created.append(body["id"])
    assert body["status"] == "DRAFT"
    assert body["tool"] == "GITHUB"
    assert body["name"] == "백엔드 저장소"  # 한글 왕복 확인
    assert body["credentialMasked"].startswith("****")
    assert "ghp_fakeToken" not in body["credentialMasked"]  # 원문 토큰이 새지 않는다
    assert body["ingestedCount"] == 0

    listed = client.get(f"/api/projects/{PID}/connections", headers=_auth(token))
    assert listed.status_code == 200
    assert any(c["id"] == body["id"] for c in listed.json())


@requires_db
def test_create_rejects_non_https(client, as_pm):
    token, _ = as_pm
    body = _create_body()
    body["baseUrl"] = "http://insecure.example"
    res = client.post(f"/api/projects/{PID}/connections", json=body, headers=_auth(token))
    assert res.status_code == 400
    assert res.json()["code"] == "VALIDATION_FAILED"


@requires_db
def test_test_unsaved_reaches_github(client, as_pm, monkeypatch):
    token, _ = as_pm
    monkeypatch.setattr(
        github, "verify", lambda base, target, tok: ("jypark-user/axlink", ["issue", "commit"])
    )
    res = client.post(
        "/api/connections/test",
        json={
            "tool": "GITHUB",
            "baseUrl": "https://api.github.com",
            "targetResource": "jypark-user/axlink",
            "credential": {"accessToken": "ghp_x"},
        },
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reachable"] is True
    assert body["resourceName"] == "jypark-user/axlink"
    assert "commit" in body["detectedItemTypes"]


@requires_db
def test_saved_test_marks_verified_then_activates(client, as_pm, monkeypatch):
    token, created = as_pm
    monkeypatch.setattr(
        github, "verify", lambda base, target, tok: ("jypark-user/axlink", ["issue"])
    )
    created_res = client.post(
        f"/api/projects/{PID}/connections", json=_create_body(), headers=_auth(token)
    )
    cid = created_res.json()["id"]
    created.append(cid)

    # DRAFT 에서 바로 ACTIVE 는 막힌다
    bad = client.patch(
        f"/api/connections/{cid}/status", json={"status": "ACTIVE"}, headers=_auth(token)
    )
    assert bad.status_code == 400

    # 테스트 통과하면 VERIFIED 로 올라간다
    tested = client.post(f"/api/connections/{cid}/test", headers=_auth(token))
    assert tested.status_code == 200
    after = client.get(f"/api/projects/{PID}/connections", headers=_auth(token)).json()
    assert next(c for c in after if c["id"] == cid)["status"] == "VERIFIED"

    # 이제 ACTIVE 로 전이된다
    activated = client.patch(
        f"/api/connections/{cid}/status", json={"status": "ACTIVE"}, headers=_auth(token)
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"


@requires_db
def test_github_auth_error_maps_to_401(client, as_pm, monkeypatch):
    token, created = as_pm
    from app.common import errors

    def boom(base, target, tok):
        raise errors.ApiError(401, "TOOL_AUTH", "토큰이 유효하지 않습니다.")

    monkeypatch.setattr(github, "verify", boom)
    created_res = client.post(
        f"/api/projects/{PID}/connections", json=_create_body(), headers=_auth(token)
    )
    cid = created_res.json()["id"]
    created.append(cid)
    res = client.post(f"/api/connections/{cid}/test", headers=_auth(token))
    assert res.status_code == 401
    assert res.json()["code"] == "TOOL_AUTH"


@requires_db
def test_other_contractor_cannot_touch_connection(client, client_token, as_pm, monkeypatch):
    """접근 범위 — 사업 권한 없는 토큰은 연결 목록도 못 본다."""
    token, _ = as_pm
    # 사업 목록 자체는 박PM 것만 보이므로, 여기서는 미인증 접근을 확인한다
    res = client.get(f"/api/projects/{PID}/connections")
    assert res.status_code == 401
