"""IM-007 예제 시나리오 실행 공통 설비.

시나리오 시험은 이름에 시나리오 ID 를 넣는다(`test_UC_001_S01_...`). 실행 뒤
`scripts/verification_records.py record-junit` 가 junit 에서 ID 를 읽어 runs.jsonl 에 옮긴다.

실행 대상은 둘이다.
- 기본: FastAPI TestClient + CI 시험용 DB. 기록 모드 `auto`.
- `AXLINK_TARGET_URL` 이 있으면 그 서버(5174 등)에 HTTP 로 보낸다. 기록 모드 `api`.
  투입 스크립트의 DB 작업은 `AXLINK_DATABASE_URL` 이 그 서버와 같은 전용 시험 DB 를 가리켜야 한다.

같은 모듈의 시나리오는 하나의 S0 위에서 돈다. 상태를 바꾸는 시나리오는 끝에 되돌리거나,
되돌릴 수 없으면 뒤 시나리오가 그 변화에 기대지 않게 쓴다.
"""

from __future__ import annotations

import os

import httpx
import pytest

from tests.conftest import requires_db
from tests.fixtures.im009.seed import Seeder

TARGET_URL = os.environ.get("AXLINK_TARGET_URL")

pytestmark = requires_db


@pytest.fixture(scope="module")
def target(client):
    """TestClient 또는 실제 서버 클라이언트. 둘 다 `.get/.post/...` 와 `/api/...` 경로를 쓴다."""
    if TARGET_URL:
        with httpx.Client(base_url=TARGET_URL.rstrip("/"), timeout=60) as c:
            yield c
    else:
        yield client


@pytest.fixture(scope="module")
def s0(target):
    """상태 S0. 모듈이 끝나면 지운다."""
    s = Seeder(target)
    try:
        s.s0()
        yield s
    finally:
        s.cleanup()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
