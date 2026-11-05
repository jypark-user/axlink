"""사업 등록에서 용역사 초대·접속까지 (SER.SEC.003, SWFR.WEB.003).

발주기관이 사업을 만들고 초대 링크를 건네면, 용역사가 직접 계정을 만들고 그 사업만 본다.
"""

import pytest

from app.db import tx
from tests.conftest import requires_db

SEED_PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _project_body(**over) -> dict:
    body = {
        "name": "시험 사업-설정",
        "startDate": "2026-09-01",
        "endDate": "2026-12-31",
        "description": "사업 등록 흐름 시험",
        "contractorName": "",
        "deletePassword": "delete-me-1234",
    }
    body.update(over)
    return body


@pytest.fixture
def cleanup():
    """시험이 남긴 사업·계정·조직을 지운다. 사업 삭제는 하위 행을 전부 끌고 간다."""
    yield
    with tx() as cur:
        cur.execute("delete from project where name like '시험 사업-%%'")
        cur.execute("delete from app_user where username like 'test-%%'")
        cur.execute(
            "delete from organization where name like '시험용역사-%%' "
            "and not exists (select 1 from app_user u where u.organization_id = organization.id)"
        )


@requires_db
def test_contractor_cannot_create_project(client, client_token):
    res = client.post("/api/projects", json=_project_body(), headers=_auth(client_token("r3")))
    assert res.status_code == 403


@requires_db
def test_create_project_seeds_dashboard_and_checklist(client, client_token, cleanup):
    """사업 하나에 기본 대시보드 하나와 산출물 22개 항목이 같이 생긴다 (ARC-005)."""
    token = client_token("r2")
    res = client.post("/api/projects", json=_project_body(), headers=_auth(token))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "시험 사업-설정"
    assert body["status"] == "PLANNING"
    assert body["defaultDashboardId"] is not None
    pid = body["id"]

    checklist = client.get(f"/api/projects/{pid}/work-products", headers=_auth(token)).json()
    assert checklist["totalCount"] == 22
    by_type = {i["type"]: i for i in checklist["items"]}
    assert by_type["PROJECT_PLAN"]["pmActivity"] == "PM_1"
    assert by_type["REQUIREMENTS_SPEC"]["siActivity"] == "SI_2"

    # 내 사업 목록에 바로 들어온다
    me = client.get("/api/auth/me", headers=_auth(token)).json()
    assert pid in me["allowedProjectIds"]


@requires_db
def test_same_name_in_same_org_is_rejected_not_500(client, client_token, cleanup):
    """같은 발주기관에 같은 이름은 409 와 사유다(AC-002-4, GH-204)."""
    token = client_token("r2")
    first = client.post(
        "/api/projects", json=_project_body(name="시험 사업-중복"), headers=_auth(token)
    )
    assert first.status_code == 201, first.text
    again = client.post(
        "/api/projects", json=_project_body(name="시험 사업-중복"), headers=_auth(token)
    )
    assert again.status_code == 409, again.text
    assert again.json()["code"] == "PROJECT_NAME_EXISTS"
    assert "이미" in again.json()["message"]
    # 거절 뒤에도 같은 세션으로 다른 이름은 바로 등록된다(트랜잭션이 깨지지 않았다)
    other = client.post(
        "/api/projects", json=_project_body(name="시험 사업-중복-2"), headers=_auth(token)
    )
    assert other.status_code == 201, other.text


@requires_db
def test_update_validates_dates_and_phase(client, client_token, cleanup):
    token = client_token("r2")
    pid = client.post("/api/projects", json=_project_body(), headers=_auth(token)).json()["id"]

    ok = client.patch(
        f"/api/projects/{pid}",
        json={"name": "시험 사업-이름변경", "currentSiPhase": "SI_3"},
        headers=_auth(token),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["name"] == "시험 사업-이름변경"
    assert ok.json()["currentSiPhase"] == "SI_3"

    bad = client.patch(f"/api/projects/{pid}", json={"endDate": "2026-01-01"}, headers=_auth(token))
    assert bad.status_code == 400
    bad_phase = client.patch(
        f"/api/projects/{pid}", json={"currentSiPhase": "SI_9"}, headers=_auth(token)
    )
    assert bad_phase.status_code == 400


@requires_db
def test_invite_accept_assign_revoke_delete(client, client_token, cleanup):
    """S2-1 전체 흐름. 초대 → 미리보기 → 가입 → 자기 사업만 보임 → 해제 → 재할당 → 삭제."""
    client_tok = client_token("r2")
    pid = client.post("/api/projects", json=_project_body(), headers=_auth(client_tok)).json()["id"]

    invite = client.post(f"/api/projects/{pid}/invites", json={}, headers=_auth(client_tok))
    assert invite.status_code == 201, invite.text
    token = invite.json()["token"]
    assert token

    preview = client.get(f"/api/auth/invitations/{token}")
    assert preview.status_code == 200, preview.text
    assert preview.json()["kind"] == "PROJECT"
    assert preview.json()["projectName"] == "시험 사업-설정"
    assert client.get("/api/auth/invitations/not-a-real-token").status_code == 404

    accepted = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": token,
            "contractorOrgName": "시험용역사-A",
            "username": "test-pm-a",
            "name": "시험 PM",
            "password": "passw0rd1",
        },
    )
    assert accepted.status_code == 200, accepted.text
    login = accepted.json()
    assert login["user"]["role"] == "CONTRACTOR"
    assert login["user"]["organizationName"] == "시험용역사-A"
    assert login["user"]["allowedProjectIds"] == [pid]
    contractor_tok = login["accessToken"]

    # 같은 아이디로는 두 번 못 만든다. 링크 자체는 다른 사람이 또 쓸 수 있다.
    dup = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": token,
            "contractorOrgName": "시험용역사-A",
            "username": "test-pm-a",
            "name": "중복",
            "password": "passw0rd1",
        },
    )
    assert dup.status_code == 400

    # 용역사는 자기 사업은 보고, 남의 사업은 못 본다
    assert client.get(f"/api/projects/{pid}", headers=_auth(contractor_tok)).status_code == 200
    assert client.get(f"/api/projects/{SEED_PID}", headers=_auth(contractor_tok)).status_code == 403

    # 발주기관 화면의 할당 목록과 용역사 계정 목록
    assignments = client.get(f"/api/projects/{pid}/assignments", headers=_auth(client_tok)).json()
    assert len(assignments) == 1
    assert assignments[0]["userName"] == "시험 PM"
    assert assignments[0]["userEmail"] == "test-pm-a"
    assert assignments[0]["contractorOrgName"] == "시험용역사-A"
    assignment_id = assignments[0]["id"]
    org_id, user_id = assignments[0]["contractorOrgId"], assignments[0]["userId"]

    users = client.get(
        "/api/users?role=CONTRACTOR&status=ACTIVE&size=100", headers=_auth(client_tok)
    ).json()
    assert any(
        u["username"] == "test-pm-a" and u["organizationName"] == "시험용역사-A"
        for u in users["content"]
    )
    assert client.get("/api/users", headers=_auth(contractor_tok)).status_code == 403

    # 해제하면 접근이 끊기고, 다시 할당하면 살아난다 (같은 줄을 되살린다)
    gone = client.delete(
        f"/api/projects/{pid}/assignments/{assignment_id}", headers=_auth(client_tok)
    )
    assert gone.status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=_auth(contractor_tok)).status_code == 403

    back = client.post(
        f"/api/projects/{pid}/assignments",
        json={"contractorOrgId": org_id, "userIds": [user_id]},
        headers=_auth(client_tok),
    )
    assert back.status_code == 201, back.text
    assert [a["id"] for a in back.json()] == [assignment_id]
    assert client.get(f"/api/projects/{pid}", headers=_auth(contractor_tok)).status_code == 200

    # 삭제는 비밀번호를 맞춰야 한다
    wrong = client.request(
        "DELETE", f"/api/projects/{pid}", json={"password": "nope"}, headers=_auth(client_tok)
    )
    assert wrong.status_code == 403
    right = client.request(
        "DELETE",
        f"/api/projects/{pid}",
        json={"password": "delete-me-1234"},
        headers=_auth(client_tok),
    )
    assert right.status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=_auth(client_tok)).status_code == 403
