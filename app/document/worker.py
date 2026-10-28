"""문서 처리 작업자 (GH-121). API 와 함께 뜨고 진다.

대기열(document_upload.processing_state = QUEUED)에서 문서를 가져와 추출·색인·초안을 한다.
처리는 스레드에서 돌아 요청 처리(이벤트 루프)를 막지 않는다. 동시에 처리하는 문서 수는
settings.document_workers 로 묶는다. 임베딩이 CPU 를 다 쓰므로 기본 1 이다.

기동할 때 처리 중으로 남은 작업은 재시작으로 끊긴 것이다(이 API 하나만 처리한다). 다시 대기열에
넣고, 같은 작업이 여러 번 끊겼으면 실패로 남긴다. 돌아가는 동안에도 처리 중 신호가 오래 없는
작업을 같은 규칙으로 정리한다.

기동 정리(recover)도 DB 가 잠깐 안 되면 실패한다. 이때 고리가 죽으면 API 는 살아 있는데
문서가 대기 상태로 남는다(점검 RES-01). 그래서 첫 정리도 고리 안에서 간격을 늘려 가며 다시
하고, 성공하기 전에는 새 작업을 가져가지 않는다. 먼저 가져가면 뒤늦은 첫 정리가 처리 중인
그 작업까지 다시 넣어 두 번 처리한다. 계속 실패하면 상태를 failing 으로 두고 ERROR 로그를
남긴 뒤 상한 간격으로 계속 시도한다. 상태는 /api/health/documents 가 낸다(API 헬스와 따로).
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.document import service

log = logging.getLogger(__name__)

POLL_SECONDS = 2.0
SWEEP_SECONDS = 60.0
RECOVER_BACKOFF = (2.0, 60.0)  # 첫 대기, 상한(초)
FAILING_AFTER = 5  # 이만큼 잇달아 실패하면 failing


def _initial() -> dict[str, Any]:
    return {"state": "off", "recovered": False, "startedAt": None, "lastOkAt": None,
            "consecutiveFailures": 0, "lastError": None, "lastErrorAt": None}


_STATUS: dict[str, Any] = _initial()


def status() -> dict[str, Any]:
    return dict(_STATUS)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ok() -> None:
    _STATUS.update(state="running", lastOkAt=_now(), consecutiveFailures=0)


def _failed(exc: BaseException) -> int:
    # 오류 메시지에는 접속 정보가 들 수 있어 종류 이름만 남긴다
    n = _STATUS["consecutiveFailures"] + 1
    _STATUS.update(consecutiveFailures=n, lastError=type(exc).__name__, lastErrorAt=_now(),
                   state="failing" if n >= FAILING_AFTER else "retrying")
    return n


def _backoff(failures: int) -> float:
    first, cap = RECOVER_BACKOFF
    return min(cap, first * 2 ** max(0, failures - 1))


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _first_recover(stop: asyncio.Event) -> bool:
    """기동 정리. 성공하면 True, 그 전에 멈추라는 신호가 오면 False."""
    while not stop.is_set():
        try:
            requeued, failed = await asyncio.to_thread(service.recover, True)
        except Exception as exc:  # noqa: BLE001 — DB 가 돌아올 때까지 간격을 늘려 다시 한다
            n = _failed(exc)
            delay = _backoff(n)
            if n == FAILING_AFTER:
                log.error("문서 처리 기동 정리가 계속 실패한다(%d회, %s). %.0f초마다 다시 시도한다",
                          n, type(exc).__name__, RECOVER_BACKOFF[1])
            else:
                log.warning("문서 처리 기동 정리 실패(%d회, %s). %.1f초 뒤 다시 시도",
                            n, type(exc).__name__, delay)
            await _wait(stop, delay)
            continue
        if requeued or failed:
            log.info("문서 처리 기동 정리: 다시 넣음 %d, 실패로 둠 %d", requeued, failed)
        _STATUS["recovered"] = True
        _ok()
        return True
    return False


async def loop(stop: asyncio.Event) -> None:
    if not await _first_recover(stop):
        return
    workers = max(1, settings.document_workers)
    running: set[asyncio.Task[bool]] = set()
    last_sweep = asyncio.get_running_loop().time()
    while not stop.is_set():
        try:
            while len(running) < workers:
                task = asyncio.create_task(asyncio.to_thread(service.process_next))
                running.add(task)
                done, _ = await asyncio.wait({task}, timeout=0.5)
                if task in done:
                    running.discard(task)
                    if not task.result():
                        break  # 대기열이 비었다
            now = asyncio.get_running_loop().time()
            if now - last_sweep >= SWEEP_SECONDS:
                last_sweep = now
                requeued, failed = await asyncio.to_thread(service.recover, False)
                if requeued or failed:
                    log.warning("멈춘 문서 처리 정리: 다시 넣음 %d, 실패로 둠 %d", requeued, failed)
            _ok()
        except Exception as exc:  # noqa: BLE001 — 한 회차가 실패해도 작업자는 계속 돈다
            n = _failed(exc)
            log.exception("문서 처리 회차 실패(잇달아 %d회)", n)
            await _wait(stop, _backoff(n))  # DB 가 안 될 때 2초마다 오류를 쌓지 않는다
        if running:
            done, running = await asyncio.wait(running, timeout=POLL_SECONDS)
            for task in done:
                with contextlib.suppress(Exception):
                    task.result()
        else:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)


def _finished(task: asyncio.Task[None]) -> None:
    if task.cancelled() or task.exception() is None:
        _STATUS["state"] = "stopped"
        return
    exc = task.exception()
    _STATUS.update(state="dead", lastError=type(exc).__name__, lastErrorAt=_now())
    log.error("문서 처리 작업자가 멈췄다(%s). API 를 다시 띄우기 전까지 문서가 처리되지 않는다",
              type(exc).__name__, exc_info=exc)


def start() -> tuple[asyncio.Task[None], asyncio.Event]:
    _STATUS.clear()
    _STATUS.update(_initial(), state="starting", startedAt=_now())
    stop = asyncio.Event()
    task = asyncio.create_task(loop(stop), name="axlink-document-worker")
    task.add_done_callback(_finished)
    return task, stop
