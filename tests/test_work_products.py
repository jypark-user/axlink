"""산출물 체크리스트. 22종 자리가 미리 있고 수집·업로드가 그 자리를 채운다."""

import base64

import pytest

from app.db import tx
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
    """수집이 채운 자리를 원래대로 비운다. 다음 시험이 빈 자리를 전제한다."""
    yield
    with tx() as cur:
        cur.execute(
            """
            update work_product
               set title = null, version = '0', file_uri = null, external_url = null,
                   tool_connection_id = null, external_id = null, source_kind = 'MANUAL',
                   status = 'NONE', submitted_at = null
             where project_id = %s and type = 'PROJECT_PLAN' and is_current
            """,
            (PID,),
        )


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
