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


def test_password_check_is_deterministic():
    """bcrypt 5.0.0 은 맞는 비밀번호를 1% 가량 거부했다. 버전이 바뀌어도 다시 겪지 않게 고정한다."""
    import bcrypt

    from app.auth.service import _verify_password

    stored = bcrypt.hashpw(b"admin", bcrypt.gensalt(rounds=4)).decode()
    assert all(_verify_password("admin", stored) for _ in range(200))
    assert not any(_verify_password("nope", stored) for _ in range(200))


def test_password_check_survives_flaky_bcrypt():
    """09.17 실측: Windows · Python 3.13 에서 bcrypt 4.x 가 cost 10 해시를 같은 입력에 다르게
    낸다(500번 중 최대 80번). 시드 계정과 같은 cost 10 해시로 실제 조건을 재현한다.
    틀린 비밀번호는 한 번도 통과한 적이 없으므로 거부됐을 때만 다시 확인하면 된다."""
    import bcrypt

    from app.auth.service import _verify_password

    stored = bcrypt.hashpw(b"admin", bcrypt.gensalt(rounds=10)).decode()
    assert all(_verify_password("admin", stored) for _ in range(60))
    assert not any(_verify_password("nope", stored) for _ in range(20))


def test_연속_실패가_문턱을_넘으면_잠그고_시간이_지나면_푼다():
    from app.auth import throttle

    for i in range(throttle.MAX_FAILURES - 1):
        throttle.fail("Lock-Test", now=100.0 + i)
    assert throttle.locked_for("lock-test", now=120.0) == 0
    throttle.fail("lock-test", now=120.0)
    assert throttle.locked_for("LOCK-TEST", now=121.0) > 0
    assert throttle.locked_for("lock-test", now=120.0 + throttle.LOCK_SECONDS + 1) == 0
    # 창 밖의 실패는 세지 않는다
    for i in range(throttle.MAX_FAILURES - 1):
        throttle.fail("slow", now=float(i * throttle.WINDOW_SECONDS))
    later = float(throttle.MAX_FAILURES * throttle.WINDOW_SECONDS)
    assert throttle.locked_for("slow", now=later) == 0


@requires_db
def test_로그인을_연속으로_틀리면_맞는_비밀번호도_잠시_받지_않는다(client):
    from app.auth import throttle

    for _ in range(throttle.MAX_FAILURES):
        res = client.post("/api/auth/login", json={"username": "r2", "password": "nope"})
        assert res.status_code == 401
    res = client.post("/api/auth/login", json={"username": "r2", "password": "admin"})
    assert res.status_code == 429 and res.json()["code"] == "LOGIN_LOCKED"
    assert "분 뒤에" in res.json()["message"]
    # 다른 아이디는 막히지 않는다
    res = client.post("/api/auth/login", json={"username": "r3", "password": "admin"})
    assert res.status_code == 200
