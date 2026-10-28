"""스냅샷 기록 권한과 날짜 (SWFR.PIP.005, 점검 SNAP-01).

- 손으로 찍는 것은 발주기관 담당자(CLIENT)와 관리자(SUPER_ADMIN)만. 화면과 같은 규칙을 서버가 건다.
- 날짜는 사업 기준 오늘(Asia/Seoul)만. 과거 날짜에 지금 값을 덮어쓰지 못한다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common import clock
from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
# 한국 10-27 00:30 = UTC 10-26 15:30. 서버가 UTC 면 date.today() 는 10-26 을 낸다
KST_AFTER_MIDNIGHT = datetime(2026, 10, 26, 15, 30, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- 시험 DB


@pytest.fixture
def clean():
    with tx() as cur:
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))
    yield
    with tx() as cur:
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))


def _count() -> int:
    with tx() as cur:
        return fetch_one(cur, "select count(*) as n from progress_snapshot where project_id = %s",
                         (PID,))["n"]


@requires_db
def test_용역사는_스냅샷을_기록하지_못한다(client, client_token, clean):
    res = client.post(f"/api/projects/{PID}/snapshots", headers=_auth(client_token("r3")))
    assert res.status_code == 403
    assert _count() == 0
    # 읽기는 된다
    assert client.get(f"/api/projects/{PID}/snapshots",
                      headers=_auth(client_token("r3"))).status_code == 200


@requires_db
@pytest.mark.parametrize("user", ["r1", "r2"])
def test_발주기관과_관리자는_오늘_스냅샷을_기록한다(client, client_token, clean, user):
    res = client.post(f"/api/projects/{PID}/snapshots", headers=_auth(client_token(user)))
    assert res.status_code == 200, res.text
    assert res.json()["snapshotDate"] == clock.today().isoformat()


@requires_db
@pytest.mark.parametrize("days", [-1, -30, 1])
def test_다른_날짜로는_기록하지_못하고_과거_행도_그대로다(client, client_token, clean, days):
    from app.dashboard import snapshot

    past = clock.today() - timedelta(days=1)
    with tx() as cur:
        snapshot.take_unchecked(cur, PID, past)
        before = fetch_one(cur, "select * from progress_snapshot where project_id = %s "
                                "and snapshot_date = %s", (PID, past))
    target = (clock.today() + timedelta(days=days)).isoformat()
    res = client.post(f"/api/projects/{PID}/snapshots?at={target}",
                      headers=_auth(client_token("r2")))
    assert res.status_code == 400
    with tx() as cur:
        after = fetch_one(cur, "select * from progress_snapshot where project_id = %s "
                               "and snapshot_date = %s", (PID, past))
    assert after == before
    assert _count() == 1


@requires_db
def test_한국_자정_뒤에는_한국_날짜로_찍는다(client, client_token, clean, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: KST_AFTER_MIDNIGHT)
    token = client_token("r2")
    res = client.post(f"/api/projects/{PID}/snapshots", headers=_auth(token))
    assert res.status_code == 200, res.text
    assert res.json()["snapshotDate"] == "2026-10-27"
    # 오늘 날짜를 명시해도 같다
    res = client.post(f"/api/projects/{PID}/snapshots?at=2026-10-27", headers=_auth(token))
    assert res.status_code == 200
    assert client.post(f"/api/projects/{PID}/snapshots?at=2026-10-26",
                       headers=_auth(token)).status_code == 400
