"""통합 테스트 픽스처. 실제 DB(docker compose)가 떠 있어야 돈다.

    docker compose -f infra/docker-compose.yml up -d postgres
    docker compose -f infra/docker-compose.yml run --rm flyway

DB 가 없으면 해당 테스트는 skip 된다 — CI 환경별로 갈리지 않게 한다.

주의 — 이 스위트는 시드 사업(c0000000-…-0001)의 연결과 그 연결이 수집한 데이터를 지운다.
실제로 붙여 둔 연결이 있는 DB 에 그대로 돌리면 수집분이 사라진다. 손으로 만든 데이터가
들어 있는 DB 라면 AXLINK_DATABASE_URL 로 시험용 DB 를 가리키고 돌린다.
"""

from urllib.parse import urlparse

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

# 테스트는 모델 없이 돈다. 실제 모델 검증은 tests/test_*_live.py 가 따로 한다.
settings.embedding_provider = "fake"
settings.llm_provider = "fake"
# 서버 안 스케줄러는 시험에서 끈다. 회차는 test_scheduler 가 시계를 주입해 직접 돌린다.
settings.scheduler_enabled = False


def _is_test_db() -> bool:
    """데이터베이스 이름이 _test 로 끝날 때만 시험용으로 인정한다."""
    return urlparse(settings.database_url).path.rstrip("/").endswith("_test")


def _db_reachable() -> bool:
    try:
        psycopg.connect(settings.database_url, connect_timeout=3).close()
        return True
    except Exception:
        return False


# 경고만으로는 두 번 못 막았다 — 08.31 과 09.08 두 번 개발 DB 의 수집분이 지워졌다.
# 이름이 _test 로 끝나지 않는 DB 에는 아예 붙지 않는다.
if not _is_test_db():
    requires_db = pytest.mark.skip(
        reason="시험용 DB 가 아니다 — AXLINK_DATABASE_URL 이 *_test 를 가리켜야 돈다 (로컬-실행.md)"
    )
else:
    requires_db = pytest.mark.skipif(not _db_reachable(), reason="DB(docker compose)가 필요하다")


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_token(client: TestClient):
    def _login(username: str, password: str = "admin") -> str:
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200, res.text
        return res.json()["accessToken"]

    return _login
