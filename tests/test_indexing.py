"""색인 통합 — 실제 doc_chunk 에 넣고 다시 색인한다. DB 가 있어야 돈다.

임베딩은 Fake 를 쓴다. 여기서 보려는 건 벡터 품질이 아니라 전량 교체가 유니크 제약을
깨지 않는지, 그리고 본문이 그대로일 때 모델을 다시 부르지 않는지다.
"""

import uuid

import pytest

from app.ai.embedding import FakeEmbedding
from app.db import tx
from app.rag import indexing, repository
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업

_LONG_BODY = "이 문서는 청킹을 여러 번 하도록 충분히 긴 한국어 본문을 담고 있다. " * 200


class CountingEmbedding(FakeEmbedding):
    """모델을 몇 번 불렀는지 센다 — 재색인 생략을 확인하려면 호출 수를 봐야 한다."""

    def __init__(self) -> None:
        super().__init__(1024)
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        return super().embed(texts)


@pytest.fixture
def source_id():
    sid = str(uuid.uuid4())
    yield sid
    with tx() as cur:
        cur.execute("delete from doc_chunk where source_id = %s", (sid,))


def _source(sid: str, body: str, source_type: str = "DOCUMENT_UPLOAD"):
    return indexing.IndexSource(
        source_type=source_type,
        source_id=sid,
        project_id=PID,
        title="색인 테스트 문서",
        body=body,
        uri="https://example.invalid/doc",
    )


@requires_db
def test_column_dimension_matches_port():
    with tx() as cur:
        indexing.verify_dimension(cur, FakeEmbedding(1024))
        assert repository.column_dimension(cur) == 1024


@requires_db
def test_index_then_reindex_replaces_without_conflict(source_id):
    port = CountingEmbedding()

    with tx() as cur:
        first = indexing.reindex(cur, port, [_source(source_id, _LONG_BODY)])
    assert first.chunks > 1
    assert first.sources == 1

    # 같은 본문 — 모델을 다시 부르지 않는다.
    before = port.calls
    with tx() as cur:
        again = indexing.reindex(cur, port, [_source(source_id, _LONG_BODY)])
    assert again.unchanged == 1
    assert again.chunks == 0
    assert port.calls == before

    # 본문이 바뀌면 전량 교체. uq_doc_chunk__source 를 깨지 않아야 한다.
    with tx() as cur:
        changed = indexing.reindex(cur, port, [_source(source_id, "짧아진 본문이다.")])
        rows = cur.execute(
            "select chunk_index from doc_chunk where source_id = %s order by chunk_index",
            (source_id,),
        ).fetchall()
    assert changed.chunks == 1
    assert [r["chunk_index"] for r in rows] == [0]


@requires_db
def test_indexed_chunk_carries_source_location(source_id):
    with tx() as cur:
        indexing.reindex(
            cur,
            FakeEmbedding(1024),
            [_source(source_id, "# 1장 개요\n개요 문단이다.", "DOCUMENT_UPLOAD")],
        )
        row = cur.execute(
            """
            select source_title, source_uri, meta_json, embedding_model, token_count
              from doc_chunk where source_id = %s
            """,
            (source_id,),
        ).fetchone()

    # SWFR.RAG.003 — 청크마다 원문 위치가 남아야 한다.
    assert row["source_title"] == "색인 테스트 문서"
    assert row["source_uri"] == "https://example.invalid/doc"
    assert row["meta_json"]["headingPath"] == ["1장 개요"]
    assert row["token_count"] > 0
    # 어떤 모델이 만든 벡터인지는 포트가 말한 대로 남는다. 가짜는 가짜라고 적힌다.
    assert row["embedding_model"] == "fake"


class NamedEmbedding(FakeEmbedding):
    def __init__(self, name: str) -> None:
        super().__init__(1024)
        self._name = name

    def model_name(self) -> str:
        return self._name


@requires_db
def test_reindex_refreshes_when_embedding_model_differs(source_id):
    """본문이 같아도 다른 모델이 만든 벡터는 버리고 다시 만든다.
    가짜 벡터가 실제 모델 이름을 달고 들어간 뒤 재수집으로도 안 지워졌던 사고의 재발 방지다."""
    with tx() as cur:
        indexing.reindex(cur, NamedEmbedding("fake"), [_source(source_id, _LONG_BODY)])

    port = NamedEmbedding("bge-m3")
    with tx() as cur:
        again = indexing.reindex(cur, port, [_source(source_id, _LONG_BODY)])
        models = cur.execute(
            "select distinct embedding_model from doc_chunk where source_id = %s", (source_id,)
        ).fetchall()
    assert again.unchanged == 0
    assert again.chunks > 1
    assert [m["embedding_model"] for m in models] == ["bge-m3"]

    # 같은 모델로 한 번 더 — 이제는 건너뛴다.
    with tx() as cur:
        third = indexing.reindex(cur, port, [_source(source_id, _LONG_BODY)])
    assert third.unchanged == 1


@requires_db
def test_requirement_indexes_as_one_chunk(source_id):
    with tx() as cur:
        result = indexing.reindex(
            cur,
            FakeEmbedding(1024),
            [_source(source_id, "요구사항 본문이다.", "REQUIREMENT")],
        )
    assert result.chunks == 1
