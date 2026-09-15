"""하이브리드 검색. 벡터(코사인)와 어휘(tsvector + 트라이그램) 후보를 RRF 로 합친다.

한국어는 조사가 붙어 단어 경계가 흐리다. tsvector 'simple' 은 공백 단위라
"이행률은" 과 "이행률" 이 다른 토큰이고, 그래서 트라이그램(word_similarity)을 어휘 쪽의
본체로 둔다. tsvector 는 SWFR.RAG.001 같은 코드·영문 정확 일치를 위해 남긴다.

근거 게이트(SWFR.RAG.007)는 RRF 점수가 아니라 코사인 유사도로 판단한다. RRF 는
순위만 남기고 "얼마나 가까운가" 를 버리기 때문에 문턱을 세울 수 없다.
"""

from dataclasses import dataclass
from typing import Any

from app.ai.port import EmbeddingPort
from app.config import settings
from app.db import fetch_all
from app.rag import vector


@dataclass
class RetrievedChunk:
    id: str
    project_id: str
    project_name: str
    source_type: str
    source_id: str
    source_title: str
    source_uri: str | None
    chunk_index: int
    content: str
    heading_path: list[str]
    page_no: int | None
    similarity: float  # 질문 벡터와의 코사인 유사도
    score: float = 0.0  # RRF 융합 점수. 순위 결정에만 쓴다


@dataclass
class SearchResult:
    chunks: list[RetrievedChunk]  # 프롬프트에 들어갈 상위 청크, 융합 점수 내림차순
    max_similarity: float  # 후보 전체에서 가장 높은 코사인 유사도. 게이트가 본다
    candidate_count: int

    def passes_gate(self, threshold: float | None = None) -> bool:
        limit = settings.rag_min_similarity if threshold is None else threshold
        return bool(self.chunks) and self.max_similarity >= limit


_SELECT = """
select c.id::text as id, c.project_id::text as project_id, p.name as project_name,
       c.source_type, c.source_id::text as source_id, c.source_title, c.source_uri,
       c.chunk_index, c.content, c.meta_json,
       1 - (c.embedding <=> %(q)s::vector) as similarity
  from doc_chunk c
  join project p on p.id = c.project_id
 where c.project_id = any(%(projects)s::uuid[])
"""


def vector_candidates(
    cur: Any, query_vec: list[float], project_ids: list[str], n: int
) -> list[dict]:
    return fetch_all(
        cur,
        _SELECT + " order by c.embedding <=> %(q)s::vector limit %(n)s",
        {"q": vector.to_literal(query_vec), "projects": project_ids, "n": n},
    )


def lexical_candidates(
    cur: Any, query_vec: list[float], text: str, project_ids: list[str], n: int
) -> list[dict]:
    """tsvector 일치 또는 트라이그램 부분 유사(<%%). 둘 다 V1 의 GIN 인덱스를 탄다."""
    return fetch_all(
        cur,
        _SELECT
        + """
   and (c.content_tsv @@ websearch_to_tsquery('simple', %(text)s)
        or %(text)s <%% c.content)
 order by greatest(ts_rank(c.content_tsv, websearch_to_tsquery('simple', %(text)s)),
                   word_similarity(%(text)s, c.content)) desc
 limit %(n)s
""",
        {"q": vector.to_literal(query_vec), "text": text, "projects": project_ids, "n": n},
    )


def rrf(ranked_lists: list[list[str]], k: int) -> dict[str, float]:
    """Reciprocal Rank Fusion. 각 목록의 순위만 보고 1/(k+rank) 를 더한다."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


def search(
    cur: Any,
    port: EmbeddingPort,
    question: str,
    project_ids: list[str],
    top_k: int | None = None,
) -> SearchResult:
    if not project_ids or not question.strip():
        return SearchResult(chunks=[], max_similarity=0.0, candidate_count=0)
    query_vec = port.embed([question])[0]
    return search_with_vector(cur, query_vec, question, project_ids, top_k)


def search_with_vector(
    cur: Any,
    query_vec: list[float],
    question: str,
    project_ids: list[str],
    top_k: int | None = None,
) -> SearchResult:
    n = settings.rag_candidates
    by_vector = vector_candidates(cur, query_vec, project_ids, n)
    by_lexical = lexical_candidates(cur, query_vec, question, project_ids, n)

    rows: dict[str, dict] = {}
    for row in [*by_vector, *by_lexical]:
        rows.setdefault(row["id"], row)
    if not rows:
        return SearchResult(chunks=[], max_similarity=0.0, candidate_count=0)

    scores = rrf(
        [[r["id"] for r in by_vector], [r["id"] for r in by_lexical]], settings.rag_rrf_k
    )
    chunks = [_chunk(rows[key], score) for key, score in scores.items()]
    chunks.sort(key=lambda c: (-c.score, -c.similarity))
    limit = settings.rag_top_k if top_k is None else top_k
    # RRF 는 두 목록에 다 있는 것을 무조건 위로 올린다. 09.14 실측에서 벡터 1순위(0.663)가
    # 어휘 목록에도 걸린 0.604 짜리에 밀려 4위로 갔다. 그래서 RRF 로는 후보(2배)만 고르고,
    # 근거 번호 순서는 코사인 유사도로 매긴다. 어휘로만 걸린 정확 일치도 후보에는 남는다.
    pool = sorted(chunks[: limit * 2], key=lambda c: -c.similarity)
    return SearchResult(
        chunks=pool[:limit],
        max_similarity=max(c.similarity for c in chunks),
        candidate_count=len(chunks),
    )


def _chunk(row: dict, score: float) -> RetrievedChunk:
    meta = row.get("meta_json") or {}
    heading = meta.get("headingPath") or []
    page = meta.get("page")
    return RetrievedChunk(
        id=row["id"],
        project_id=row["project_id"],
        project_name=row["project_name"],
        source_type=row["source_type"],
        source_id=row["source_id"],
        source_title=row["source_title"],
        source_uri=row.get("source_uri"),
        chunk_index=int(row["chunk_index"]),
        content=row["content"],
        heading_path=[str(h) for h in heading if h],
        page_no=int(page) if isinstance(page, int) else None,
        similarity=float(row["similarity"]),
        score=score,
    )
