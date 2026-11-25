"""같은 연결의 수집은 한 번에 하나만 돈다 (IM-002 AC-011-8, UC-011-S06, SWFR.CON.005).

수집 회차는 요청 하나의 트랜잭션 안에서 끝까지 돈다. 그래서 진행 중인 잡 행(RUNNING)은
다른 요청에 보이지 않는다. 연결마다 트랜잭션 잠금을 잡아, 진행 중이면 수동 수집은 「이미
수집 중」으로 거절하고 예약 수집은 건너뛴다.
"""

import uuid

import pytest

from app import scheduler
from app.common import crypto, errors
from app.db import fetch_one, pool, tx
from app.integration import repository as integ_repo
from app.integration import sync
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


@pytest.fixture
def connection():
    with tx() as cur:
        org = str(fetch_one(cur, "select organization_id from app_user "
                                 "where username = 'r3'")["organization_id"])
        row = integ_repo.insert(cur, PID, org, "GITHUB", "동시 실행 시험", "https://api.github.com",
                                f"o/lock-{uuid.uuid4().hex[:6]}", crypto.encrypt("k"), "k***", {})
    yield row
    with tx() as cur:
        cur.execute("delete from sync_job where tool_connection_id = %s", (str(row["id"]),))
        cur.execute("delete from tool_connection where id = %s", (str(row["id"]),))


def _jobs(cid: str) -> int:
    with tx() as cur:
        row = fetch_one(
            cur, "select count(*) as n from sync_job where tool_connection_id = %s", (cid,)
        )
    return int(row["n"])


@requires_db
def test_진행_중인_수집이_있으면_수동_수집은_이미_수집_중으로_거절된다(connection):
    cid = str(connection["id"])
    with pool().connection() as holder, holder.cursor() as cur:
        assert integ_repo.try_lock_sync(cur, cid)  # 다른 요청이 수집 중인 상태
        with pytest.raises(errors.ApiError) as caught, tx() as other:
            sync.run_sync(other, connection)
        holder.rollback()
    assert caught.value.status == 409 and caught.value.code == "SYNC_RUNNING"
    assert "이미 수집 중" in caught.value.message
    assert _jobs(cid) == 0  # 둘째 회차의 잡이 남지 않는다


@requires_db
def test_진행_중인_수집이_있으면_예약_수집은_건너뛴다(connection):
    cid = str(connection["id"])
    with pool().connection() as holder, holder.cursor() as cur:
        assert integ_repo.try_lock_sync(cur, cid)
        outcome = scheduler.sync_connection(connection)
        holder.rollback()
    assert outcome == "skipped"
    assert _jobs(cid) == 0


@requires_db
def test_잠금은_회차가_끝나면_풀린다(connection):
    cid = str(connection["id"])
    with tx() as cur:
        assert integ_repo.try_lock_sync(cur, cid)
    with tx() as cur:
        assert integ_repo.try_lock_sync(cur, cid)
