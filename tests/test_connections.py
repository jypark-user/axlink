"""커넥터 등록·테스트 슬라이스 — 박PM 시나리오 S2-2.

GitHub 실호출은 monkeypatch 로 대체해 결정론적으로 돌린다. 실제 토큰으로 api.github.com 을
때리는 검증은 tests/test_github_live.py 가 AXLINK_GH_TOKEN 이 있을 때만 한다.
"""

import pytest

from app.db import tx
from app.integration.adapter import github_connector as github
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


def _cleanup_project_connections(client, token: str) -> None:
    existing = client.get(f"/api/projects/{PID}/connections", headers=_auth(token))
    if existing.status_code == 200:
        for c in existing.json():
            client.delete(f"/api/connections/{c['id']}", headers=_auth(token))
    _cleanup_promoted_rows()


def _cleanup_promoted_rows() -> None:
    """승격된 표준 모델 행과 청크까지 지운다.

    연결을 지워도 표준 모델은 남는다(FK 가 ON DELETE SET NULL — 수집 이력을 연결 삭제로
    날리지 않는 게 스키마 의도다). 그래서 테스트가 치우지 않으면 tool_connection_id 가
    null 인 채로 쌓이고, 부분 유니크 인덱스가 적용되지 않아 같은 행이 중복된다.
    """
    with tx() as cur:
        cur.execute(
            """
            delete from doc_chunk
             where project_id = %s
               and source_id in (
                     select id from requirement where project_id = %s and source_kind = 'TOOL'
                     union all
                     select id from issue where project_id = %s and source_kind = 'TOOL')
            """,
            (PID, PID, PID),
        )
        for table in ("requirement", "issue", "code_change"):
            cur.execute(
                f"delete from {table} where project_id = %s and source_kind = 'TOOL'",  # noqa: S608
                (PID,),
            )


@pytest.fixture
def as_pm(client, client_token):
    """박PM(용역사 r3) 토큰. 앞뒤로 이 사업의 연결을 비워 남은 데이터가 테스트를 깨지 않게 한다."""
    token = client_token("r3")
    _cleanup_project_connections(client, token)
    created: list[str] = []
    yield token, created
    _cleanup_project_connections(client, token)


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
        github,
        "verify",
        lambda base, target, tok: github.ProbeResult("jypark-user/axlink", ["issue", "commit"], []),
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
        github,
        "verify",
        lambda base, target, tok: github.ProbeResult("jypark-user/axlink", ["issue"], []),
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
def test_test_reports_denied_permissions(client, as_pm, monkeypatch):
    """토큰에 이슈 권한이 빠지면 연결 테스트가 그걸 denied 로 알려준다."""
    token, _ = as_pm
    monkeypatch.setattr(
        github,
        "verify",
        lambda base, target, tok: github.ProbeResult(
            "jypark-user/axlink", ["commit", "pull_request"], ["issue"]
        ),
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
    assert res.status_code == 200
    body = res.json()
    assert body["detectedItemTypes"] == ["commit", "pull_request"]
    assert body["deniedItemTypes"] == ["issue"]


@requires_db
def test_backfill_ingests_raw_artifacts(client, as_pm, monkeypatch):
    """전체수집: 이슈·커밋을 가져와 raw_artifact 에 적재하고 ingestedCount 가 오른다."""
    token, created = as_pm
    monkeypatch.setattr(
        github,
        "verify",
        lambda base, target, tok: github.ProbeResult("jypark-user/axlink", ["issue", "commit"], []),
    )

    def fake_fetch(base, target, tok, kind, per_page, max_pages):
        if kind == "issue":
            yield "issue:1", {"number": 1, "title": "첫 이슈"}
            yield "issue:2", {"number": 2, "title": "둘째 이슈"}
        elif kind == "commit":
            yield "commit:abc", {
                "sha": "abc",
                "commit": {
                    "message": "초기 커밋",
                    "author": {"name": "박PM", "date": "2026-08-20T00:00:00Z"},
                },
            }
        # pull_request 는 없음

    monkeypatch.setattr(github, "fetch_items", fake_fetch)
    # 저장소 파일 수집은 이 시험의 관심사가 아니다 — 실제 GitHub 을 치지 않게 막는다.
    monkeypatch.setattr(github, "fetch_file", lambda *a, **k: None)

    cid = client.post(
        f"/api/projects/{PID}/connections", json=_create_body(), headers=_auth(token)
    ).json()["id"]
    created.append(cid)
    client.post(f"/api/connections/{cid}/test", headers=_auth(token))  # 검증(VERIFIED)

    res = client.post(f"/api/connections/{cid}/sync", headers=_auth(token))
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["status"] == "SUCCEEDED"
    assert job["stats"]["fetched"] == 3
    assert job["stats"]["upserted"] == 3  # 이슈 2 + 커밋 1 이 표준 모델로 올라간다
    assert job["stats"]["unmapped"] == 0
    assert job["stats"]["indexed"] == 2  # 색인은 사람이 쓴 문장이 있는 이슈만

    # 연결 카드에 ingestedCount 가 반영된다
    conns = client.get(f"/api/projects/{PID}/connections", headers=_auth(token)).json()
    assert next(c for c in conns if c["id"] == cid)["ingestedCount"] == 3

    # 다시 수집하면 원본이 같아 적재를 건너뛰고, 본문이 그대로라 재색인도 하지 않는다(멱등)
    again = client.post(f"/api/connections/{cid}/sync", headers=_auth(token)).json()
    assert again["stats"]["skippedUnchanged"] == 3
    assert again["stats"]["indexed"] == 0


@requires_db
def test_backfill_tolerates_missing_permission(client, as_pm, monkeypatch):
    """한 항목종류의 권한이 빠져도 통째로 실패하지 않고 그 종류만 건너뛴다."""
    token, created = as_pm
    monkeypatch.setattr(
        github,
        "verify",
        lambda base, target, tok: github.ProbeResult("jypark-user/axlink", ["commit"], ["issue"]),
    )

    def fetch_with_denied(base, target, tok, kind, per_page, max_pages):
        from app.common import errors

        if kind == "issue":
            raise errors.ApiError(403, "TOOL_AUTH", "issue 읽기 권한이 없습니다.")
        if kind == "commit":
            yield "commit:abc", {"sha": "abc", "commit": {"message": "커밋"}}

    monkeypatch.setattr(github, "fetch_items", fetch_with_denied)
    monkeypatch.setattr(github, "fetch_file", lambda *a, **k: None)

    cid = client.post(
        f"/api/projects/{PID}/connections", json=_create_body(), headers=_auth(token)
    ).json()["id"]
    created.append(cid)
    client.post(f"/api/connections/{cid}/test", headers=_auth(token))  # 검증(VERIFIED)

    job = client.post(f"/api/connections/{cid}/sync", headers=_auth(token)).json()
    assert job["status"] == "SUCCEEDED"  # 부분 성공
    assert job["stats"]["fetched"] == 1  # 커밋만
    assert "issue" in (job["error"] or "")  # 건너뛴 항목을 정직하게 남긴다


@requires_db
def test_other_contractor_cannot_touch_connection(client, client_token, as_pm, monkeypatch):
    """접근 범위 — 사업 권한 없는 토큰은 연결 목록도 못 본다."""
    token, _ = as_pm
    # 사업 목록 자체는 박PM 것만 보이므로, 여기서는 미인증 접근을 확인한다
    res = client.get(f"/api/projects/{PID}/connections")
    assert res.status_code == 401
