"""문서 처리 작업자가 DB 장애를 견디는가 (SWFR.CON.007, 점검 RES-01).

기동 직후 첫 정리(recover)에서 DB 가 잠깐 안 되면 작업자 고리가 죽어, API 는 살아 있는데
문서가 대기 상태로 남았다. 첫 정리도 간격을 늘려 가며 다시 하고, 그동안은 새 작업을 가져가지
않는다(나중의 첫 정리가 처리 중인 작업을 다시 넣어 두 번 처리하게 된다).
작업자 상태는 API 헬스와 따로 /api/health/documents 로 본다.

DB 장애는 recover 가 psycopg.OperationalError 를 내도록 바꿔서 흉내 낸다. 실제 DB 를 끊지 않는다.
"""

import asyncio
import logging

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.document import service, worker
from app.main import app
from tests.conftest import requires_db


@pytest.fixture
def bare():
    """기동 절차(DB 연결) 없이 라우트만 부르는 클라이언트."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(worker, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "RECOVER_BACKOFF", (0.01, 0.05))
    monkeypatch.setattr(worker, "FAILING_AFTER", 3)


def _flaky(fail_times: int, calls: list[str]):
    def recover(all_running: bool) -> tuple[int, int]:
        calls.append("recover-all" if all_running else "recover-stale")
        if all_running and calls.count("recover-all") <= fail_times:
            raise psycopg.OperationalError("connection refused")
        return 0, 0
    return recover


async def _run_until(cond, seconds: float = 5.0) -> None:
    task, stop = worker.start()
    try:
        for _ in range(int(seconds / 0.01)):
            await asyncio.sleep(0.01)
            if cond():
                break
            assert not task.done(), "작업자 고리가 끝났다"
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)


def test_첫_정리에서_DB_오류가_나도_작업자는_살아서_다시_시도한다(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(service, "recover", _flaky(2, calls))

    def process_next() -> bool:
        calls.append("process")
        return False
    monkeypatch.setattr(service, "process_next", process_next)

    asyncio.run(_run_until(lambda: "process" in calls))
    assert calls[:3] == ["recover-all"] * 3
    # 첫 정리가 성공하기 전에는 작업을 가져가지 않는다
    assert "process" in calls and calls.index("process") > 2
    assert worker.status()["state"] == "stopped"
    assert worker.status()["recovered"] is True


def test_계속_실패하면_상태와_로그에_남고_빠르게_반복하지_않는다(monkeypatch, caplog, bare):
    calls: list[str] = []
    monkeypatch.setattr(service, "recover", _flaky(10_000, calls))
    monkeypatch.setattr(service, "process_next", lambda: calls.append("process") or False)
    seen: dict = {}

    def failing() -> bool:
        st = worker.status()
        if st["state"] == "failing":
            seen.update(st)
            seen["http"] = bare.get("/api/health/documents")
            return True
        return False

    with caplog.at_level(logging.WARNING, logger="app.document.worker"):
        asyncio.run(_run_until(failing))
    assert seen["consecutiveFailures"] >= 3
    assert seen["lastError"] == "OperationalError"  # 메시지(접속 정보가 들 수 있다)는 내지 않는다
    assert seen["http"].status_code == 503
    assert seen["http"].json()["state"] == "failing"
    assert "process" not in calls
    assert any(r.levelno == logging.ERROR and "계속 실패" in r.getMessage() for r in caplog.records)
    # 대기 시간이 늘어나 상한에서 멈춘다 — 실패 횟수만큼 바로바로 다시 하지 않는다
    assert worker._backoff(1) < worker._backoff(3) <= worker.RECOVER_BACKOFF[1]
    assert worker._backoff(50) == worker.RECOVER_BACKOFF[1]


def test_API_헬스는_작업자_상태와_따로_간다(bare, monkeypatch):
    monkeypatch.setattr(worker, "_STATUS", {**worker._STATUS, "state": "failing"})
    assert bare.get("/api/health").json()["status"] == "UP"
    assert bare.get("/api/health/documents").status_code == 503


def test_작업자를_켜지_않았으면_꺼짐으로_보인다(bare, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(worker, "_STATUS", worker._initial())
    monkeypatch.setattr(settings, "document_processing", "inline")
    assert bare.get("/api/health/documents").json()["state"] == "inline"
    monkeypatch.setattr(settings, "document_processing", "background")
    res = bare.get("/api/health/documents")
    assert res.status_code == 200 and res.json()["state"] == "off"


def test_고리가_예상_밖으로_끝나면_죽음으로_남긴다(monkeypatch, caplog):
    async def boom(stop):
        raise RuntimeError("뜻밖의 오류")
    monkeypatch.setattr(worker, "loop", boom)

    async def run():
        task, _ = worker.start()
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)  # 완료 콜백

    with caplog.at_level(logging.ERROR, logger="app.document.worker"):
        asyncio.run(run())
    assert worker.status()["state"] == "dead"
    assert any("멈췄다" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- 시험 DB


@requires_db
def test_DB가_돌아오면_대기_문서를_한_번씩만_처리한다(client, client_token, monkeypatch):
    from app.config import settings
    from tests.test_document_worker import _doc
    from tests.test_documents import _purge, _upload, _xlsx_bytes

    monkeypatch.setattr(settings, "document_processing", "background")
    token = client_token("r3")
    _purge(client, token)
    try:
        ids = [_upload(client, token, f"복구{i}.xlsx", _xlsx_bytes(f"복구 {i}")).json()["id"]
               for i in range(2)]
        real = service.recover
        fails = {"n": 0}

        def recover(all_running: bool) -> tuple[int, int]:
            if all_running and fails["n"] < 2:
                fails["n"] += 1
                raise psycopg.OperationalError("connection refused")
            return real(all_running)
        monkeypatch.setattr(service, "recover", recover)

        asyncio.run(_run_until(
            lambda: all(_doc(i)["processing_state"] == "DONE" for i in ids), seconds=60))
        docs = [_doc(i) for i in ids]
        assert all(d["processing_state"] == "DONE" for d in docs)
        assert all(d["processing_attempts"] == 1 for d in docs)  # 두 번 처리하지 않았다
        assert fails["n"] == 2
    finally:
        _purge(client, token)
