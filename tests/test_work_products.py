"""산출물 체크리스트. 22종 자리가 미리 있고 수집·업로드가 그 자리를 채운다."""

import base64

import pytest

from app.db import fetch_one, tx
from app.integration import github
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
WBS_PATH = "docs/00-management/WBS.xlsx"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _checklist(client, token: str) -> dict:
    res = client.get(f"/api/projects/{PID}/work-products", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


@requires_db
def test_checklist_lists_29110_slots(client, client_token):
    body = _checklist(client, client_token("r3"))
    assert body["totalCount"] == 22  # ISO/IEC 29110 관리객체 22종
    types = {i["type"] for i in body["items"]}
    assert {"PROJECT_PLAN", "REQUIREMENTS_SPEC", "SOFTWARE_DESIGN"} <= types


@requires_db
def test_display_name_is_korean(client, client_token):
    """발주기관 화면에 영문 코드가 노출되면 안 된다 — 이름은 서버가 준다."""
    body = _checklist(client, client_token("r3"))
    plan = next(i for i in body["items"] if i["type"] == "PROJECT_PLAN")
    assert plan["displayName"] == "사업수행계획서"


@requires_db
def test_other_project_is_denied(client, client_token):
    other = "c0000000-0000-4000-8000-000000000099"
    res = client.get(f"/api/projects/{other}/work-products", headers=_auth(client_token("r3")))
    assert res.status_code == 403


@pytest.fixture
def restore_project_plan():
    """수집이 쌓은 버전을 지우고 원래 빈 자리를 되살린다.

    버전이 누적되므로 현행 행 하나만 되돌려서는 부족하다 — 수집이 만든 행을 지워야 한다.
    """
    with tx() as cur:
        row = fetch_one(
            cur,
            """
            select id from work_product
             where project_id = %s and type = 'PROJECT_PLAN' and is_current
            """,
            (PID,),
        )
        original = str(row["id"])
    yield original
    with tx() as cur:
        cur.execute(
            """
            delete from work_product
             where project_id = %s and type = 'PROJECT_PLAN' and id <> %s
            """,
            (PID, original),
        )
        cur.execute(
            """
            update work_product
               set is_current = true, title = null, version = '0', file_uri = null,
                   external_url = null, tool_connection_id = null, external_id = null,
                   source_revision = null, source_kind = 'MANUAL',
                   status = 'NONE', submitted_at = null
             where id = %s
            """,
            (original,),
        )


def _github_returning(monkeypatch, sha_holder: dict) -> None:
    """저장소에 WBS 파일 하나만 있는 GitHub 를 흉내낸다. sha 는 호출 시점에 읽는다."""
    monkeypatch.setattr(
        github,
        "verify",
        lambda base, target, tok: github.ProbeResult("o/r", ["issue", "commit"], []),
    )
    monkeypatch.setattr(github, "fetch_items", lambda *a, **k: iter(()))
    monkeypatch.setattr(
        github,
        "fetch_file",
        lambda base, target, tok, path, ref=None: {
            "path": path,
            "sha": sha_holder["sha"],
            "size": 12,
            "htmlUrl": f"https://github.com/o/r/blob/main/{path}",
            "content": base64.b64encode(b"not a real xlsx").decode("ascii"),
        },
    )


def _connect_and_sync(client, token: str) -> str:
    created = client.post(
        f"/api/projects/{PID}/connections",
        json={
            "tool": "GITHUB",
            "name": "WBS 수집용",
            "baseUrl": "https://api.github.com",
            "targetResource": "o/r",
            "credential": {"accessToken": "ghp_fake"},
        },
        headers=_auth(token),
    ).json()
    client.post(f"/api/connections/{created['id']}/test", headers=_auth(token))
    job = client.post(f"/api/connections/{created['id']}/sync", headers=_auth(token)).json()
    assert job["status"] == "SUCCEEDED", job
    return created["id"]


def _versions() -> list[dict]:
    with tx() as cur:
        cur.execute(
            """
            select version, is_current from work_product
             where project_id = %s and type = 'PROJECT_PLAN'
             order by is_current desc, updated_at desc
            """,
            (PID,),
        )
        return cur.fetchall()


@requires_db
def test_collected_file_fills_the_slot(client, client_token, monkeypatch, restore_project_plan):
    """저장소에 커밋된 WBS 를 수집하면 사업수행계획서 자리가 채워진다.

    GitHub 만 쓰는 업체도 파일만 올려 두면 진척 산정이 성립한다는 전제가 이것이다.
    """
    token = client_token("r3")
    before = next(i for i in _checklist(client, token)["items"] if i["type"] == "PROJECT_PLAN")
    assert before["status"] == "NONE" and before["fileUri"] is None

    monkeypatch.setattr(
        github,
        "verify",
        lambda base, target, tok: github.ProbeResult("o/r", ["issue", "commit"], []),
    )
    monkeypatch.setattr(github, "fetch_items", lambda *a, **k: iter(()))
    monkeypatch.setattr(
        github,
        "fetch_file",
        lambda base, target, tok, path, ref=None: {
            "path": path,
            "sha": "0f1e2d3c4b5a6978",
            "size": 12,
            "htmlUrl": f"https://github.com/o/r/blob/main/{path}",
            "content": base64.b64encode(b"not a real xlsx").decode("ascii"),
        },
    )

    created = client.post(
        f"/api/projects/{PID}/connections",
        json={
            "tool": "GITHUB",
            "name": "WBS 수집용",
            "baseUrl": "https://api.github.com",
            "targetResource": "o/r",
            "credential": {"accessToken": "ghp_fake"},
        },
        headers=_auth(token),
    ).json()
    client.post(f"/api/connections/{created['id']}/test", headers=_auth(token))
    job = client.post(f"/api/connections/{created['id']}/sync", headers=_auth(token)).json()
    assert job["status"] == "SUCCEEDED", job

    after = next(i for i in _checklist(client, token)["items"] if i["type"] == "PROJECT_PLAN")
    assert after["status"] == "SUBMITTED"
    assert after["fileUri"] == WBS_PATH
    assert after["version"] == "0f1e2d3c4b5a"

    client.delete(f"/api/connections/{created['id']}", headers=_auth(token))


@requires_db
def test_new_version_accumulates_and_keeps_the_old_one(
    client, client_token, monkeypatch, restore_project_plan
):
    """WBS 는 사업 내내 갱신된다. 덮어쓰면 "계획을 언제 바꿨는가" 에 답할 수 없다."""
    token = client_token("r3")
    sha = {"sha": "aaaa1111bbbb2222"}
    _github_returning(monkeypatch, sha)

    first = _connect_and_sync(client, token)
    client.delete(f"/api/connections/{first}", headers=_auth(token))

    sha["sha"] = "cccc3333dddd4444"
    second = _connect_and_sync(client, token)
    client.delete(f"/api/connections/{second}", headers=_auth(token))

    rows = _versions()
    current = [r for r in rows if r["is_current"]]
    assert len(current) == 1, "현행은 언제나 하나여야 한다"
    assert current[0]["version"] == "cccc3333dddd"

    kept = {r["version"] for r in rows if not r["is_current"]}
    assert "aaaa1111bbbb" in kept, "앞 버전이 남아 있어야 이력이 성립한다"


@requires_db
def test_same_version_does_not_pile_up(
    client, client_token, monkeypatch, restore_project_plan
):
    """내용이 그대로면 새 버전이 아니다. 수집할 때마다 행이 늘면 이력이 잡음이 된다."""
    token = client_token("r3")
    sha = {"sha": "eeee5555ffff6666"}
    _github_returning(monkeypatch, sha)

    for _ in range(2):
        connection = _connect_and_sync(client, token)
        client.delete(f"/api/connections/{connection}", headers=_auth(token))

    collected = [r for r in _versions() if r["version"] == "eeee5555ffff"]
    assert len(collected) == 1

