"""통합 테스트 픽스처. 실제 DB(docker compose)가 떠 있어야 돈다.

    docker compose -f infra/docker-compose.yml up -d postgres
    docker compose -f infra/docker-compose.yml run --rm flyway

DB 가 없으면 해당 테스트는 skip 된다 — CI 환경별로 갈리지 않게 한다.

주의 — 이 스위트는 시드 사업(c0000000-…-0001)의 연결과 그 연결이 수집한 데이터를 지운다.
실제로 붙여 둔 연결이 있는 DB 에 그대로 돌리면 수집분이 사라진다. 손으로 만든 데이터가
들어 있는 DB 라면 AXLINK_DATABASE_URL 로 시험용 DB 를 가리키고 돌린다.
"""

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

# 테스트는 모델 없이 돈다. 실제 bge-m3 검증은 tests/test_embedding_live.py 가 따로 한다.
settings.embedding_provider = "fake"


def _db_reachable() -> bool:
    try:
        psycopg.connect(settings.database_url, connect_timeout=3).close()
        return True
    except Exception:
        return False


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
