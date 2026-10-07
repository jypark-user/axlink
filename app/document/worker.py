"""문서 처리 작업자 (GH-121). API 와 함께 뜨고 진다.

대기열(document_upload.processing_state = QUEUED)에서 문서를 가져와 추출·색인·초안을 한다.
처리는 스레드에서 돌아 요청 처리(이벤트 루프)를 막지 않는다. 동시에 처리하는 문서 수는
settings.document_workers 로 묶는다. 임베딩이 CPU 를 다 쓰므로 기본 1 이다.

기동할 때 처리 중으로 남은 작업은 재시작으로 끊긴 것이다(이 API 하나만 처리한다). 다시 대기열에
넣고, 같은 작업이 여러 번 끊겼으면 실패로 남긴다. 돌아가는 동안에도 처리 중 신호가 오래 없는
작업을 같은 규칙으로 정리한다.
"""

import asyncio
import contextlib
import logging

from app.config import settings
from app.document import service

log = logging.getLogger(__name__)

POLL_SECONDS = 2.0
SWEEP_SECONDS = 60.0


async def loop(stop: asyncio.Event) -> None:
    requeued, failed = await asyncio.to_thread(service.recover, True)
    if requeued or failed:
        log.info("문서 처리 기동 정리: 다시 넣음 %d, 실패로 둠 %d", requeued, failed)
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
        except Exception:  # noqa: BLE001 — 한 회차가 실패해도 작업자는 계속 돈다
            log.exception("문서 처리 회차 실패")
        if running:
            done, running = await asyncio.wait(running, timeout=POLL_SECONDS)
            for task in done:
                with contextlib.suppress(Exception):
                    task.result()
        else:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)


def start() -> tuple[asyncio.Task[None], asyncio.Event]:
    stop = asyncio.Event()
    task = asyncio.create_task(loop(stop), name="axlink-document-worker")
    return task, stop
