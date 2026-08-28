"""통합 테스트 픽스처. 실제 DB(docker compose)가 떠 있어야 돈다.

    docker compose -f infra/docker-compose.yml up -d postgres
    docker compose -f infra/docker-compose.yml run --rm flyway

DB 가 없으면 해당 테스트는 skip 된다 — CI 환경별로 갈리지 않게 한다.
"""

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


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
    def _login(email: str, password: str = "admin") -> str:
        res = client.post("/api/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.text
        return res.json()["accessToken"]

    return _login
