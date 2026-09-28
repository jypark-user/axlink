"""서버 안 스케줄러 (SWFR.PIP.005 · SWFR.CON.005).

판단은 시계를 주입해 모델·DB 없이 보고, 한 회차는 시험 DB 로 돈다. "일별" 과 "수집 주기"
는 스스로 돌아야 한다는 뜻이므로 자동으로 생기는지를 여기서 증명한다.
"""

from datetime import UTC, date, datetime, time, timedelta

from app import scheduler
from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
KST = scheduler.LOCAL_TZ


def _at(h: int, m: int = 0, day: int = 28) -> datetime:
    return datetime(2026, 9, day, h, m, tzinfo=KST).astimezone(UTC)


# ── 수집 판단


def test_주기가_지났을_때만_수집하고_0_이면_안_한다():
    now = _at(10, 0)
    assert scheduler.sync_due(None, 30, now) is True  # 한 번도 안 했으면 지금
    assert scheduler.sync_due(now - timedelta(minutes=29), 30, now) is False
    assert scheduler.sync_due(now - timedelta(minutes=30), 30, now) is True
    assert scheduler.sync_due(None, 0, now) is False  # 수동만
    assert scheduler.sync_due(now - timedelta(days=3), 0, now) is False


def test_하루_한_번_수집은_정한_시각_규칙이다():
    at = time(6, 0)
    yesterday = _at(6, 5, day=27)
    assert scheduler.sync_due(yesterday, 1440, _at(5, 59), at) is False  # 시각 전
    assert scheduler.sync_due(yesterday, 1440, _at(6, 0), at) is True
    assert scheduler.sync_due(_at(6, 1), 1440, _at(23, 0), at) is False  # 오늘 이미 했다
    assert scheduler.sync_due(None, 1440, _at(3, 0), at) is True  # 처음이면 지금


def test_빈도가_하루보다_잦으면_마지막_뒤_그_시간이_지났을_때_다시_찍는다():
    now = _at(15, 0)
    # 하루 한 번(24)은 정한 시각 규칙만 쓴다
    assert scheduler.refresh_due(now - timedelta(hours=5), 24, now) is False
    assert scheduler.refresh_due(now - timedelta(hours=5), 6, now) is False
    assert scheduler.refresh_due(now - timedelta(hours=6), 6, now) is True
    assert scheduler.refresh_due(None, 6, now) is False  # 처음 것은 기동·정한 시각 규칙이 찍는다


# ── 스냅샷 판단


def test_기동_직후에는_오늘_것이_없으면_시각과_무관하게_찍는다():
    early = _at(7, 0)  # 정해진 시각(00:10)은 지났지만 기동 케이스로 본다
    assert scheduler.snapshot_due(None, time(23, 0), early, just_started=True) is True
    assert scheduler.snapshot_due(date(2026, 9, 27), time(23, 0), early, just_started=True) is True
    # 오늘 것이 이미 있으면 기동 때도 안 찍는다
    assert scheduler.snapshot_due(date(2026, 9, 28), time(23, 0), early, just_started=True) is False


def test_평소에는_정해진_시각을_지난_뒤에_오늘_것이_없을_때_찍는다():
    at = time(0, 10)
    assert scheduler.snapshot_due(date(2026, 9, 27), at, _at(0, 5), just_started=False) is False
    assert scheduler.snapshot_due(date(2026, 9, 27), at, _at(0, 10), just_started=False) is True
    assert scheduler.snapshot_due(date(2026, 9, 28), at, _at(0, 11), just_started=False) is False
    # 날이 바뀌면 다시 찍는다 (자정 지나 00:10)
    later = _at(0, 10, day=29)
    assert scheduler.snapshot_due(date(2026, 9, 28), at, later, just_started=False) is True


def test_시간대는_사업_시간대_기준이다():
    # UTC 15:00 = KST 00:00 다음날. 정해진 시각 00:10 은 아직이다
    now = datetime(2026, 9, 28, 15, 0, tzinfo=UTC)
    assert scheduler.snapshot_due(date(2026, 9, 28), time(0, 10), now, just_started=False) is False
    assert scheduler.snapshot_due(date(2026, 9, 28), time(0, 10), now + timedelta(minutes=10),
                                  just_started=False) is True


# ── 한 회차 (시험 DB)


@requires_db
def test_한_회차가_오늘_스냅샷을_만들고_같은_날_다시_돌면_안_만든다(monkeypatch):
    from app.integration import sync

    calls = {"sync": 0}
    def fake_sync(cur, conn, retry_of=None):
        calls["sync"] += 1

    monkeypatch.setattr(sync, "run_sync", fake_sync)
    with tx() as cur:
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))
        cur.execute("delete from project_schedule where project_id = %s", (PID,))

    now = _at(9, 0)
    taken: set[str] = set()
    first = scheduler.run_once(now, just_started=True, taken_at_scheduled=taken)
    assert first["snapshots"] >= 1 and first["errors"] == 0
    with tx() as cur:
        row = fetch_one(
            cur, "select snapshot_date from progress_snapshot where project_id = %s", (PID,)
        )
    assert row["snapshot_date"] == date(2026, 9, 28)

    # 정해진 시각(00:10) 이 지난 뒤 기동했으니 기동 때 찍은 것이 오늘 몫이다. 같은 날 다시 안 찍는다
    assert PID in taken
    second = scheduler.run_once(
        now + timedelta(minutes=1), just_started=False, taken_at_scheduled=taken
    )
    assert second["snapshots"] == 0
    # 정해진 시각 전에 기동한 경우: 기동 때 찍고, 정해진 시각에 그날 수집을 반영해 한 번 더
    taken.clear()
    early = _at(0, 5, day=29)
    with tx() as cur:
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))
    assert scheduler.run_once(early, just_started=True, taken_at_scheduled=taken)["snapshots"] == 1
    assert PID not in taken
    at_time = scheduler.run_once(_at(0, 10, day=29), just_started=False, taken_at_scheduled=taken)
    assert at_time["snapshots"] == 1 and PID in taken
    later = scheduler.run_once(_at(0, 11, day=29), just_started=False, taken_at_scheduled=taken)
    assert later["snapshots"] == 0

    with tx() as cur:
        n = fetch_one(
            cur, "select count(*) as n from progress_snapshot where project_id = %s", (PID,)
        )
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))
    assert n["n"] == 1  # 같은 날 두 번 찍어도 한 줄이다


@requires_db
def test_설정_API_는_선택지만_받고_발주기관만_바꾼다(client, client_token):
    with tx() as cur:
        cur.execute("delete from project_schedule where project_id = %s", (PID,))
    r2, r3 = client_token("r2"), client_token("r3")
    auth = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

    got = client.get(f"/api/projects/{PID}/schedule", headers=auth(r3))
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["syncIntervalMinutes"] == 30 and body["snapshotTime"] == "00:10"
    assert body["minIntervalMinutes"] == 15 and body["editable"] is False
    assert [o["minutes"] for o in body["options"]] == [0, 15, 30, 60, 180, 360, 720, 1440]
    assert body["syncTime"] == "06:00"
    assert body["snapshotIntervalHours"] == 24
    assert [o["hours"] for o in body["snapshotOptions"]] == [24, 12, 6, 3, 1]

    # 용역사는 못 바꾼다
    denied = client.put(
        f"/api/projects/{PID}/schedule",
        json={"syncIntervalMinutes": 60, "snapshotTime": "06:00"}, headers=auth(r3),
    )
    assert denied.status_code == 403

    # 선택지 밖은 거절
    bad = client.put(
        f"/api/projects/{PID}/schedule",
        json={"syncIntervalMinutes": 5, "snapshotTime": "06:00"}, headers=auth(r2),
    )
    assert bad.status_code == 400

    ok = client.put(
        f"/api/projects/{PID}/schedule",
        json={
            "syncIntervalMinutes": 1440, "syncTime": "07:30",
            "snapshotTime": "06:30", "snapshotIntervalHours": 6,
        },
        headers=auth(r2),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["syncIntervalMinutes"] == 1440 and ok.json()["syncTime"] == "07:30"
    assert ok.json()["snapshotTime"] == "06:30"
    assert ok.json()["snapshotIntervalHours"] == 6
    odd = client.put(
        f"/api/projects/{PID}/schedule",
        json={"syncIntervalMinutes": 60, "snapshotTime": "06:30", "snapshotIntervalHours": 5},
        headers=auth(r2),
    )
    assert odd.status_code == 400
    assert ok.json()["editable"] is True
    with tx() as cur:
        cur.execute("delete from project_schedule where project_id = %s", (PID,))
