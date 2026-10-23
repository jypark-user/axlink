"""통합 테스트 픽스처.

시험은 세 갈래다. 표식(pytest -m)으로 고른다.

- 표식 없음: DB·모델 없이 돈다. CI 기본 작업이다.
- `db`: 시험용 DB(이름이 _test 로 끝남)가 있어야 돈다. `@requires_db` 가 이 표식이다.
- `live`: 실모델·실원천을 부른다. AXLINK_LIVE=1 일 때만 돈다.

DB 는 보통 없으면 skip 한다. AXLINK_REQUIRE_DB=1 이면 연결·마이그레이션 문제를 skip 하지 않고
실패로 끝낸다. CI 의 DB 작업이 이 모드다. 띄우는 법은 docs/00-management/로컬-실행.md.

주의 — 이 스위트는 시드 사업(c0000000-…-0001)의 연결과 그 연결이 수집한 데이터를 지운다.
그래서 이름이 _test 로 끝나지 않는 DB 에는 어떤 모드에서도 붙지 않는다. live 시험도 같다.
"""

import os
import re
from functools import cache
from pathlib import Path
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
# 시험은 업로드 요청 안에서 처리를 끝낸다. 뒤에서 처리하는 길은 test_document_worker.py 가 본다
settings.document_processing = "inline"


def _is_test_db() -> bool:
    """데이터베이스 이름이 _test 로 끝날 때만 시험용으로 인정한다."""
    return urlparse(settings.database_url).path.rstrip("/").endswith("_test")


LIVE_ENABLED = os.environ.get("AXLINK_LIVE") == "1"
REQUIRE_DB = os.environ.get("AXLINK_REQUIRE_DB") == "1"

_MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migration"


def _latest_migration() -> int:
    versions = [
        int(m.group(1))
        for f in _MIGRATIONS.glob("V*__*.sql")
        if (m := re.match(r"V(\d+)__", f.name))
    ]
    return max(versions)


@cache
def db_problem() -> str | None:
    """DB 시험을 돌릴 수 없는 이유. 돌릴 수 있으면 None.

    여기서 보는 것은 셋뿐이다: 시험용 DB 인가, 붙는가, 성공한 마지막 마이그레이션 번호가
    db/migration 의 최신 번호와 같고 실패 기록이 없는가. 중간 번호 누락·체크섬 변조·파일과
    이력의 불일치는 보지 않는다. 그건 flyway migrate 가 적용 전에 하는 validate 의 몫이다
    (빈 DB 에 migrate 하는 CI·로컬 절차에서 그 검증이 먼저 돈다).
    """
    # 경고만으로는 두 번 못 막았다 — 08.31 과 09.08 두 번 개발 DB 의 수집분이 지워졌다.
    if not _is_test_db():
        return "시험용 DB 가 아니다 — AXLINK_DATABASE_URL 이 *_test 를 가리켜야 돈다 (로컬-실행.md)"
    try:
        conn = psycopg.connect(settings.database_url, connect_timeout=3)
    except Exception as exc:
        return f"시험용 DB 에 연결할 수 없다: {exc}"
    latest = _latest_migration()
    try:
        with conn:
            row = conn.execute(
                """
                select max(version::int) filter (where success),
                       count(*) filter (where not success)
                  from flyway_schema_history
                 where version is not null
                """
            ).fetchone()
    except psycopg.errors.UndefinedTable:
        return f"마이그레이션이 적용되지 않았다 — flyway migrate 로 V{latest} 까지 올려야 한다"
    applied, failed = row
    if failed:
        return f"실패한 마이그레이션 기록이 {failed}건 있다 — flyway repair 나 DB 재생성이 필요하다"
    if applied != latest:
        return f"스키마가 V{applied} 다 — db/migration 의 최신 V{latest} 와 다르다"
    return None


def pytest_sessionstart(session: pytest.Session) -> None:
    if REQUIRE_DB and (problem := db_problem()):
        pytest.exit(f"AXLINK_REQUIRE_DB=1 인데 DB 시험을 돌릴 수 없다: {problem}", returncode=1)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_live = pytest.mark.skip(reason="live 시험은 AXLINK_LIVE=1 일 때만 돈다")
    for item in items:
        if "live" in item.keywords and not LIVE_ENABLED:
            item.add_marker(skip_live)
        elif "db" in item.keywords and (problem := db_problem()):
            # REQUIRE_DB 면 sessionstart 에서 이미 끝났다. 여기 오는 건 DB 가 선택일 때뿐이다.
            item.add_marker(pytest.mark.skip(reason=problem))


requires_db = pytest.mark.db


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


# 이슈 라벨·제목으로 요구사항을 가르던 예전 규칙(ARC-030 전). 지금 수집은 요구사항을 만들지 않는다
_OLD_REQUIREMENT_LABEL = "유형: 요구사항"
_OLD_CODE_IN_TITLE = re.compile(r"^\[[A-Z]{2,5}(?:\.[A-Z]{2,5})+\.\d{3}\]")


def seed_issue_requirements(
    cur, project_id: str, connection_id: str, issues: list[tuple[str, dict]]
) -> dict[str, str]:
    """예전에 GitHub 이슈로 만들어 둔 요구사항을 흉내 낸다. 그런 요구사항이 있는 사업
    (5173 실제 사업처럼)을 시험할 때 쓴다. 이슈는 원본으로 따로 넣고 수집을 돌리면, 수집은
    이 요구사항의 열림·닫힘만 따라간다. 돌려주는 값은 {external_id: 요구사항 id}."""
    from app.standard import mapping

    made: dict[str, str] = {}
    for external_id, payload in issues:
        title = payload.get("title") or ""
        if _OLD_REQUIREMENT_LABEL not in mapping.labels(payload) and not (
            _OLD_CODE_IN_TITLE.match(title)
        ):
            continue
        cur.execute(
            "select id from requirement where tool_connection_id = %s and external_id = %s",
            (connection_id, external_id),
        )
        found = cur.fetchone()
        if found:  # 같은 이슈를 다시 넣는 시험(재수집). 이미 만든 것은 그대로 둔다
            made[external_id] = str(found["id"])
            continue
        rec = mapping.to_requirement(payload)
        cur.execute(
            """
            insert into requirement
              (project_id, code, title, body, priority, status, evidence_status, assignee,
               source_created_at, source_updated_at,
               tool_connection_id, external_id, external_url, source_kind)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
            returning id
            """,
            (
                project_id, rec["code"], rec["title"], rec["body"], rec["priority"],
                rec["status"], rec["status"], rec["assignee"], rec["source_created_at"],
                rec["source_updated_at"], connection_id, external_id, rec["external_url"],
            ),
        )
        made[external_id] = str(cur.fetchone()["id"])
    return made
