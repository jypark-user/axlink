"""색인. 소스 단위 delete + insert 전량 교체.

증분 갱신을 하지 않는 이유: 청크 경계는 본문이 조금만 바뀌어도 통째로 밀린다.
chunk_index 를 맞춰 부분 갱신하려 들면 uq_doc_chunk__source 와 싸우게 된다.

임베딩을 먼저 만들고 그다음에 지운다 — 모델이 죽어 있으면 기존 색인이 남는 편이
반쯤 지워진 색인보다 낫다.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from app.ai import embedding_guard
from app.ai.port import EmbeddingPort
from app.common import errors
from app.rag import chunking, repository, vector


@dataclass
class IndexSource:
    """색인 대상 하나. 표준 모델의 어느 테이블에서 왔는지는 source_type 이 말한다."""

    source_type: str
    source_id: str
    project_id: str
    title: str
    body: str | None = None
    uri: str | None = None


def verify_dimension(cur: Any, port: EmbeddingPort) -> None:
    """모델 차원과 컬럼 차원이 어긋나면 기동을 막는다.

    어긋난 채로 돌면 색인은 되는데 검색 결과가 조용히 엉망이 된다 — 가장 나쁜 실패다.
    """
    column = repository.column_dimension(cur)
    if column != port.dimension():
        raise errors.ApiError(
            500,
            "AI_DIMENSION_MISMATCH",
            f"임베딩 차원 불일치 — 모델 {port.dimension()}, doc_chunk.embedding {column}",
        )


@dataclass
class IndexResult:
    chunks: int = 0
    sources: int = 0
    unchanged: int = 0


def reindex(cur: Any, port: EmbeddingPort, sources: list[IndexSource]) -> IndexResult:
    """대상들을 다시 색인한다. 본문이 그대로면 임베딩을 다시 만들지 않는다.

    청킹은 DB·모델 없이 도는 순수 계산이라, 청크 해시를 먼저 만들어 기존 것과 비교하면
    반복 수집에서 모델 호출을 통째로 건너뛸 수 있다.
    """
    result = IndexResult()
    plan: list[tuple[IndexSource, list[chunking.ChunkDraft]]] = []
    for source in sources:
        drafts = chunking.chunk(source.source_type, source.title, source.body)
        if drafts:
            plan.append((source, drafts))
    if not plan:
        return result

    plan = _drop_unchanged(cur, plan, result, port.model_name())
    if not plan:
        return result
    # 다른 모델의 벡터가 이미 있으면 섞지 않는다(ARC-022)
    embedding_guard.require_match(
        cur, port.model_name(), [f"{s.source_type}:{s.source_id}" for s, _ in plan]
    )

    texts = [draft.content for _, drafts in plan for draft in drafts]
    vectors = port.embed(texts)
    if len(vectors) != len(texts):
        raise errors.ApiError(
            503,
            "AI_UNAVAILABLE",
            f"임베딩 개수 불일치 — {len(texts)}건 요청, {len(vectors)}건 응답",
        )

    rows: list[dict[str, Any]] = []
    cursor = 0
    for source, drafts in plan:
        repository.delete_by_source(cur, source.source_type, source.source_id)
        for draft in drafts:
            rows.append(
                {
                    "project_id": source.project_id,
                    "source_type": source.source_type,
                    "source_id": source.source_id,
                    "chunk_index": draft.chunk_index,
                    "content": draft.content,
                    "embedding": vector.to_literal(vectors[cursor]),
                    "embedding_model": port.model_name(),
                    "token_count": draft.token_count,
                    "source_title": source.title[:500],
                    "source_uri": source.uri,
                    "content_hash": _hash(draft.content),
                    "meta": draft.meta,
                }
            )
            cursor += 1

    result.chunks = repository.insert_chunks(cur, rows)
    result.sources = len(plan)
    return result


def _drop_unchanged(
    cur: Any,
    plan: list[tuple[IndexSource, list[chunking.ChunkDraft]]],
    result: IndexResult,
    model: str,
) -> list[tuple[IndexSource, list[chunking.ChunkDraft]]]:
    by_type: dict[str, list[str]] = {}
    for source, _ in plan:
        by_type.setdefault(source.source_type, []).append(source.source_id)
    existing = {
        (source_type, source_id): hashes
        for source_type, ids in by_type.items()
        for source_id, hashes in repository.hashes_by_source(cur, source_type, ids).items()
    }

    keep: list[tuple[IndexSource, list[chunking.ChunkDraft]]] = []
    for source, drafts in plan:
        fresh = [(_hash(d.content), model) for d in drafts]
        if existing.get((source.source_type, source.source_id)) == fresh:
            result.unchanged += 1
            continue
        keep.append((source, drafts))
    return keep


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
