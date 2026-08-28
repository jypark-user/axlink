"""인증 슬라이스. 시드 계정(V4/V5)의 r1~r3 · 비밀번호 admin 을 쓴다."""

from tests.conftest import requires_db


@requires_db
def test_login_returns_session_and_profile(client):
    res = client.post("/api/auth/login", json={"email": "r2@admin.com", "password": "admin"})
    assert res.status_code == 200
    body = res.json()
    assert body["accessToken"]
    assert body["refreshToken"]
    assert body["expiresIn"] == 1800
    user = body["user"]
    assert user["email"] == "r2@admin.com"
    assert user["role"] == "CLIENT"
    assert user["organizationName"] == "한국디지털공사"


@requires_db
def test_login_rejects_wrong_password(client):
    res = client.post("/api/auth/login", json={"email": "r2@admin.com", "password": "nope"})
    assert res.status_code == 401
    assert res.json()["code"] == "CREDENTIALS_INVALID"


@requires_db
def test_me_requires_bearer(client):
    assert client.get("/api/auth/me").status_code == 401


@requires_db
def test_me_returns_caller(client, client_token):
    token = client_token("r2@admin.com")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "r2@admin.com"


@requires_db
def test_refresh_rotates_token(client):
    login = client.post(
        "/api/auth/login", json={"email": "r2@admin.com", "password": "admin"}
    ).json()
    rt = login["refreshToken"]
    first = client.post("/api/auth/refresh", json={"refreshToken": rt})
    assert first.status_code == 200
    # 회전됐으므로 옛 토큰은 더 못 쓴다.
    reuse = client.post("/api/auth/refresh", json={"refreshToken": rt})
    assert reuse.status_code == 401
