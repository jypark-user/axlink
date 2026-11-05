"""발주기관 조직·계정 발급 (GH-187, SER.SEC.003).

최고관리자만 발주기관 조직과 담당자 계정을 만든다. 첫 비밀번호는 응답에 한 번만 나오고,
받은 사람이 로그인해 바꾼다. 계정은 지우지 않고 중지한다. 중지하면 로그인과 토큰 갱신이 막힌다.
"""

import uuid

import pytest

from app.db import fetch_all, fetch_one, tx
from tests.conftest import requires_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def made():
    """시험이 만든 조직·계정. 끝나면 이력까지 지운다."""
    ids: dict[str, list[str]] = {"orgs": [], "users": []}
    yield ids
    with tx() as cur:
        every = ids["users"] + ids["orgs"]
        cur.execute("delete from entity_history where entity_id::text = any(%s)", (every,))
        cur.execute("delete from refresh_token where app_user_id::text = any(%s)", (ids["users"],))
        cur.execute("delete from app_user where id::text = any(%s)", (ids["users"],))
        cur.execute("delete from organization where id::text = any(%s)", (ids["orgs"],))


def _org(client, admin: str, made, name: str | None = None) -> dict:
    res = client.post(
        "/api/admin/organizations",
        json={"name": name or f"시험 발주기관 {uuid.uuid4().hex[:6]}"},
        headers=_auth(admin),
    )
    assert res.status_code == 201, res.text
    made["orgs"].append(res.json()["id"])
    return res.json()


def _user(client, admin: str, made, org_id: str, username: str | None = None) -> dict:
    res = client.post(
        "/api/admin/users",
        json={
            "organizationId": org_id,
            "username": username or f"c-{uuid.uuid4().hex[:8]}",
            "name": "시험 담당",
        },
        headers=_auth(admin),
    )
    assert res.status_code == 201, res.text
    made["users"].append(res.json()["id"])
    return res.json()


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@requires_db
def test_최고관리자가_아니면_조직도_계정도_못_만든다(client, client_token, made):
    admin = client_token("r1")
    org = _org(client, admin, made)
    for who in ("r2", "r3"):  # 발주기관, 용역사
        token = client_token(who)
        assert client.get("/api/admin/organizations", headers=_auth(token)).status_code == 403
        assert (
            client.post(
                "/api/admin/organizations", json={"name": "x"}, headers=_auth(token)
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/admin/users",
                json={"organizationId": org["id"], "username": "nobody-x", "name": "x"},
                headers=_auth(token),
            ).status_code
            == 403
        )


@requires_db
def test_발주기관을_만들고_담당자에게_첫_비밀번호를_한_번만_준다(client, client_token, made):
    admin = client_token("r1")
    org = _org(client, admin, made)
    assert org["type"] == "CLIENT" and org["userCount"] == 0
    dup = client.post("/api/admin/organizations", json={"name": org["name"]}, headers=_auth(admin))
    assert dup.status_code == 409 and dup.json()["code"] == "ORGANIZATION_EXISTS"

    user = _user(client, admin, made, org["id"])
    temporary = user["temporaryPassword"]
    assert user["role"] == "CLIENT" and len(temporary) >= 12

    # 저장은 해시뿐이다. 이력·응답 목록 어디에도 원문이 없다
    with tx() as cur:
        row = fetch_one(
            cur,
            "select password_hash, organization_id, role, status from app_user where id = %s",
            (user["id"],),
        )
        history = fetch_all(
            cur,
            "select field, to_value, actor from entity_history where entity_id::text = any(%s)",
            ([org["id"], user["id"]],),
        )
    assert row["password_hash"] != temporary and row["password_hash"].startswith("$2")
    assert str(row["organization_id"]) == org["id"] and row["status"] == "ACTIVE"
    assert {h["field"] for h in history} == {"created"}
    assert all(temporary not in (h["to_value"] or "") for h in history)
    listed = client.get(f"/api/users?organizationId={org['id']}", headers=_auth(admin)).json()
    assert temporary not in str(listed)

    # 받은 사람이 로그인하면 그 기관 소속 발주기관 계정이다
    logged = _login(client, user["username"], temporary)
    assert logged.status_code == 200, logged.text
    me = client.get("/api/auth/me", headers=_auth(logged.json()["accessToken"])).json()
    assert me["role"] == "CLIENT"

    # 같은 아이디는 다시 못 만든다(대소문자 무시)
    again = client.post(
        "/api/admin/users",
        json={"organizationId": org["id"], "username": user["username"].upper(), "name": "x"},
        headers=_auth(admin),
    )
    assert again.status_code == 409 and again.json()["code"] == "USERNAME_EXISTS"


@requires_db
def test_받은_사람이_비밀번호를_바꾼다(client, client_token, made):
    admin = client_token("r1")
    user = _user(client, admin, made, _org(client, admin, made)["id"])
    token = _login(client, user["username"], user["temporaryPassword"]).json()["accessToken"]

    wrong = client.post(
        "/api/auth/password",
        json={"currentPassword": "틀림", "newPassword": "새비밀번호-1234"},
        headers=_auth(token),
    )
    assert wrong.status_code == 400 and wrong.json()["code"] == "PASSWORD_MISMATCH"
    short = client.post(
        "/api/auth/password",
        json={"currentPassword": user["temporaryPassword"], "newPassword": "짧음"},
        headers=_auth(token),
    )
    assert short.status_code in (400, 422)

    ok = client.post(
        "/api/auth/password",
        json={"currentPassword": user["temporaryPassword"], "newPassword": "새비밀번호-1234"},
        headers=_auth(token),
    )
    assert ok.status_code == 204, ok.text
    assert _login(client, user["username"], user["temporaryPassword"]).status_code == 401
    assert _login(client, user["username"], "새비밀번호-1234").status_code == 200


@requires_db
def test_관리자가_비밀번호를_재설정하면_옛_비밀번호와_세션이_무효가_된다(
    client, client_token, made
):
    """AC-001-5·AC-001-2 (GH-206). 새 비밀번호는 응답에 한 번만."""
    admin = client_token("r1")
    user = _user(client, admin, made, _org(client, admin, made)["id"])
    old_pw = user["temporaryPassword"]
    session = _login(client, user["username"], old_pw).json()

    denied = client.post(
        f"/api/admin/users/{user['id']}/password-reset", headers=_auth(client_token("r2"))
    )
    assert denied.status_code == 403

    res = client.post(f"/api/admin/users/{user['id']}/password-reset", headers=_auth(admin))
    assert res.status_code == 200, res.text
    new_pw = res.json()["temporaryPassword"]
    assert new_pw and new_pw != old_pw
    assert _login(client, user["username"], old_pw).status_code == 401
    assert _login(client, user["username"], new_pw).status_code == 200
    refreshed = client.post("/api/auth/refresh", json={"refreshToken": session["refreshToken"]})
    assert refreshed.status_code == 401
    # 이력 어디에도 새 비밀번호가 없다
    with tx() as cur:
        rows = fetch_all(cur, "select * from entity_history where entity_id = %s", (user["id"],))
    assert rows and all(new_pw not in str(r) for r in rows)
    # 관리자 자기 자신은 거절
    me = client.get("/api/auth/me", headers=_auth(admin)).json()["userId"]
    assert (
        client.post(f"/api/admin/users/{me}/password-reset", headers=_auth(admin)).status_code
        == 409
    )


@requires_db
def test_중지한_계정은_로그인도_토큰_갱신도_막힌다(client, client_token, made):
    admin = client_token("r1")
    user = _user(client, admin, made, _org(client, admin, made)["id"])
    session = _login(client, user["username"], user["temporaryPassword"]).json()

    url = f"/api/admin/users/{user['id']}/status"
    assert client.patch(url, json={"status": "DISABLED"}, headers=_auth(admin)).status_code == 204
    assert _login(client, user["username"], user["temporaryPassword"]).status_code == 401
    refreshed = client.post("/api/auth/refresh", json={"refreshToken": session["refreshToken"]})
    assert refreshed.status_code == 401

    assert client.patch(url, json={"status": "ACTIVE"}, headers=_auth(admin)).status_code == 204
    assert _login(client, user["username"], user["temporaryPassword"]).status_code == 200
    with tx() as cur:
        changes = fetch_all(
            cur,
            "select from_value, to_value from entity_history"
            " where entity_id = %s and field = 'status'"
            " order by changed_at",
            (user["id"],),
        )
    assert [(c["from_value"], c["to_value"]) for c in changes] == [
        ("ACTIVE", "DISABLED"),
        ("DISABLED", "ACTIVE"),
    ]

    # 자기 계정·관리자 계정·이상한 값은 받지 않는다
    with tx() as cur:
        r1 = str(fetch_one(cur, "select id from app_user where username = 'r1'")["id"])
    me = client.patch(
        f"/api/admin/users/{r1}/status", json={"status": "DISABLED"}, headers=_auth(admin)
    )
    assert me.status_code == 409
    assert client.patch(url, json={"status": "DELETED"}, headers=_auth(admin)).status_code == 400


@requires_db
def test_용역사_조직에는_여기서_계정을_만들지_않는다(client, client_token, made):
    admin = client_token("r1")
    with tx() as cur:
        org = fetch_one(cur, "select organization_id from app_user where username = 'r3'")
    res = client.post(
        "/api/admin/users",
        json={
            "organizationId": str(org["organization_id"]),
            "username": f"c-{uuid.uuid4().hex[:8]}",
            "name": "x",
        },
        headers=_auth(admin),
    )
    assert res.status_code == 409 and res.json()["code"] == "NOT_CLIENT_ORG"
    listed = client.get("/api/admin/organizations?type=CONTRACTOR", headers=_auth(admin)).json()
    assert listed and {o["type"] for o in listed} == {"CONTRACTOR"}
