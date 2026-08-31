"""인증 슬라이스. 시드 계정(V4·V20)의 r1~r3 · 비밀번호 admin 을 쓴다."""

from tests.conftest import requires_db


@requires_db
def test_login_returns_session_and_profile(client):
    res = client.post("/api/auth/login", json={"username": "r2", "password": "admin"})
    assert res.status_code == 200
    body = res.json()
    assert body["accessToken"]
    assert body["refreshToken"]
    assert body["expiresIn"] == 1800
    user = body["user"]
    assert user["username"] == "r2"
    assert user["role"] == "CLIENT"
    assert user["organizationName"] == "한국디지털공사"


@requires_db
def test_login_rejects_wrong_password(client):
    res = client.post("/api/auth/login", json={"username": "r2", "password": "nope"})
    assert res.status_code == 401
    assert res.json()["code"] == "CREDENTIALS_INVALID"


@requires_db
def test_login_id_is_not_validated_as_email(client):
    """아이디에 형식을 강요하지 않는다. 없는 계정은 401 이지 400 이 아니다."""
    res = client.post("/api/auth/login", json={"username": "박PM", "password": "admin"})
    assert res.status_code == 401
    assert res.json()["code"] == "CREDENTIALS_INVALID"

    # 이메일 주소를 아이디로 쓰는 것도 계속 된다 — 조회까지 간다.
    res = client.post("/api/auth/login", json={"username": "a@b.co.kr", "password": "admin"})
    assert res.status_code == 401


@requires_db
def test_login_rejects_empty_id(client):
    res = client.post("/api/auth/login", json={"username": "", "password": "admin"})
    assert res.status_code == 400
    assert res.json()["code"] == "VALIDATION_FAILED"


@requires_db
def test_me_requires_bearer(client):
    assert client.get("/api/auth/me").status_code == 401


@requires_db
def test_me_returns_caller(client, client_token):
    token = client_token("r2")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["username"] == "r2"


@requires_db
def test_refresh_rotates_token(client):
    login = client.post(
        "/api/auth/login", json={"username": "r2", "password": "admin"}
    ).json()
    rt = login["refreshToken"]
    first = client.post("/api/auth/refresh", json={"refreshToken": rt})
    assert first.status_code == 200
    # 회전됐으므로 옛 토큰은 더 못 쓴다.
    reuse = client.post("/api/auth/refresh", json={"refreshToken": rt})
    assert reuse.status_code == 401
