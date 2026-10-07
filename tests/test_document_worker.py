"""문서 처리 대기열 (GH-121). 업로드는 접수만 하고 추출·색인·초안은 작업자가 뒤에서 한다.

다른 시험은 document_processing=inline 으로 요청 안에서 처리한다(conftest). 여기서는 background 로
바꿔 접수·처리·실패·재시작 정리·중복·삭제를 본다.
"""

import asyncio

import pytest

from app.common import errors
from app.config import settings
from app.db import pool, tx
from app.document import repository, service, worker
from tests.conftest import requires_db
from tests.test_documents import _auth, _purge, _upload, _xlsx_bytes


@pytest.fixture
def background(client, client_token, monkeypatch):
    monkeypatch.setattr(settings, "document_processing", "background")
    token = client_token("r3")
    _purge(client, token)
    yield token
    _purge(client, token)


def _doc(document_id: str) -> dict:
    with tx() as cur:
        return cur.execute(
            "select status, processing_state, processing_error, processing_attempts, "
            "processing_steps, (select count(*) from doc_chunk where source_id = d.id) as chunks "
            "from document_upload d where id = %s",
            (document_id,),
        ).fetchone()


def _drain() -> int:
    n = 0
    while service.process_next():
        n += 1
    return n


@requires_db
def test_업로드는_접수만_하고_작업자가_처리한다(client, background):
    res = _upload(client, background, "wbs.xlsx", _xlsx_bytes("접수 시험"))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["processingState"] == "QUEUED"
    doc = _doc(body["id"])
    assert doc["chunks"] == 0 and doc["status"] == "UPLOADED"

    assert _drain() == 1
    doc = _doc(body["id"])
    assert doc["processing_state"] == "DONE" and doc["status"] in ("EXTRACTED", "STRUCTURED")
    assert doc["chunks"] > 0
    steps = doc["processing_steps"]
    assert {"extract_s", "index_s", "draft_s", "chunks"} <= set(steps)
    detail = client.get(f"/api/documents/{body['id']}", headers=_auth(background)).json()
    assert detail["processingState"] == "DONE"
    assert detail["processingSteps"]["chunks"] == steps["chunks"]


@requires_db
def test_읽지_못한_파일은_실패와_이유를_남긴다(client, background):
    body = _upload(client, background, "broken.xlsx", b"not a zip").json()
    _drain()
    doc = _doc(body["id"])
    assert doc["processing_state"] == "FAILED" and doc["status"] == "FAILED"
    assert doc["processing_error"].startswith("본문 읽기 실패")


@requires_db
def test_색인_모델이_안되면_실패로_남고_다시_올리면_다시_처리한다(client, background, monkeypatch):
    class Down:
        def model_name(self):
            return "down"

        def embed(self, texts):
            raise errors.ApiError(503, "AI_UNAVAILABLE", "임베딩 서버에 닿지 않음")

    monkeypatch.setattr(service, "embedding_port", lambda: Down())
    data = _xlsx_bytes("색인 실패 시험")
    body = _upload(client, background, "wbs.xlsx", data).json()
    _drain()
    doc = _doc(body["id"])
    assert doc["processing_state"] == "FAILED" and "색인 실패" in doc["processing_error"]
    assert doc["status"] == "EXTRACTED" and doc["chunks"] == 0

    monkeypatch.undo()
    monkeypatch.setattr(settings, "document_processing", "background")
    again = _upload(client, background, "wbs.xlsx", data).json()
    assert again["id"] == body["id"] and again["processingState"] == "QUEUED"
    _drain()
    assert _doc(body["id"])["processing_state"] == "DONE"


@requires_db
def test_같은_파일은_한_문서이고_색인도_겹치지_않는다(client, background):
    data = _xlsx_bytes("중복 시험")
    first = _upload(client, background, "a.xlsx", data).json()
    second = _upload(client, background, "b.xlsx", data).json()
    assert first["id"] == second["id"]
    assert _drain() == 1
    chunks = _doc(first["id"])["chunks"]
    # 다시 처리해도(같은 본문) 청크 수가 늘지 않는다
    with tx() as cur:
        cur.execute(
            "update document_upload set processing_state = 'QUEUED' where id = %s", (first["id"],)
        )
    _drain()
    assert _doc(first["id"])["chunks"] == chunks


@requires_db
def test_두_작업자가_같은_문서를_가져가지_않는다(client, background):
    ids = {_upload(client, background, f"{i}.xlsx", _xlsx_bytes(f"동시 {i}")).json()["id"]
           for i in range(2)}
    with pool().connection() as c1, pool().connection() as c2:
        with c1.cursor() as a, c2.cursor() as b:
            ja = repository.claim_next(a)
            jb = repository.claim_next(b)  # a 가 아직 커밋 전이라 잠긴 행은 건너뛴다
            assert ja and jb and ja["id"] != jb["id"] and {ja["id"], jb["id"]} == ids
        c1.rollback()
        c2.rollback()


@requires_db
def test_재시작으로_끊긴_작업은_다시_넣고_반복되면_실패로_남긴다(client, background):
    body = _upload(client, background, "wbs.xlsx", _xlsx_bytes("재시작 시험")).json()
    with tx() as cur:
        assert repository.claim_next(cur)["id"] == body["id"]  # 처리 중에 프로세스가 죽었다
    # 돌아가는 동안의 정리는 신호가 오래 없는 것만 본다. 방금 시작한 것은 그대로다
    assert service.recover(all_running=False) == (0, 0)
    assert _doc(body["id"])["processing_state"] == "RUNNING"
    # 기동 때 정리는 처리 중인 것 전부를 다시 넣는다
    assert service.recover(all_running=True) == (1, 0)
    assert _doc(body["id"])["processing_state"] == "QUEUED"
    # 한도만큼 끊기면 실패로 남긴다. 영구히 처리 중으로 남지 않는다
    # 첫 시도는 위에서 끊겼다. 중간 시도도 끊기면 다시 넣고, 마지막 시도가 끊기면 실패다
    for _ in range(settings.document_max_attempts - 2):
        with tx() as cur:
            repository.claim_next(cur)
        service.recover(all_running=True)
    with tx() as cur:
        repository.claim_next(cur)
    assert service.recover(all_running=True) == (0, 1)
    doc = _doc(body["id"])
    assert doc["processing_state"] == "FAILED" and "중단되어 멈췄습니다" in doc["processing_error"]


@requires_db
def test_신호가_오래_없는_작업도_정리한다(client, background):
    body = _upload(client, background, "wbs.xlsx", _xlsx_bytes("시간 초과 시험")).json()
    with tx() as cur:
        repository.claim_next(cur)
        cur.execute(
            "update document_upload set processing_heartbeat_at = now() - interval '1 hour' "
            "where id = %s",
            (body["id"],),
        )
    assert service.recover(all_running=False) == (1, 0)


@requires_db
def test_처리_중에_지운_문서는_색인을_남기지_않는다(client, background, monkeypatch):
    body = _upload(client, background, "wbs.xlsx", _xlsx_bytes("삭제 시험")).json()
    real_prepare = service.indexing.prepare

    def prepare_then_delete(cur, port, sources):
        prepared = real_prepare(cur, port, sources)
        res = client.delete(f"/api/documents/{body['id']}", headers=_auth(background))
        assert res.status_code == 204
        return prepared

    monkeypatch.setattr(service.indexing, "prepare", prepare_then_delete)
    _drain()
    with tx() as cur:
        n = cur.execute(
            "select count(*) as n from doc_chunk where source_id = %s", (body["id"],)
        ).fetchone()["n"]
    assert n == 0


@requires_db
def test_작업자_고리가_대기열을_비운다(client, background):
    ids = [_upload(client, background, f"{i}.xlsx", _xlsx_bytes(f"고리 {i}")).json()["id"]
           for i in range(2)]

    async def run():
        task, stop = worker.start()
        for _ in range(60):
            await asyncio.sleep(0.5)
            if all(_doc(i)["processing_state"] == "DONE" for i in ids):
                break
        stop.set()
        await asyncio.wait_for(task, timeout=10)

    asyncio.run(run())
    assert all(_doc(i)["processing_state"] == "DONE" for i in ids)
