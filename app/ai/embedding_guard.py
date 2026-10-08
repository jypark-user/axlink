"""검색 모델(임베딩)과 색인이 맞는지 (ARC-022).

벡터는 만든 모델끼리만 비교할 수 있다. 차원이 같아도 다른 모델의 벡터를 섞으면 검색이 조용히
틀린다. 설정된 임베딩 모델과 다른 모델로 만든 청크가 하나라도 있으면 검색과 색인을 멈춘다.

API 전체를 띄우지 않는 쪽도 견줬다. 그러면 관리자가 화면에서 원인을 볼 길이 없고, 로그인·진척·이슈
처럼 검색과 무관한 기능까지 멈춘다. 그래서 검색·색인만 멈추고 이유를 돌려준다. 설정 화면의 검색
모델 영역이 같은 판정을 보여 준다. 차원이 컬럼과 다르면 저장 자체가 안 되므로 그때는 기동을 막는다
(indexing.verify_dimension).
"""

from typing import Any

from app.common import errors
from app.db import fetch_all, fetch_one

MISMATCH = "AI_EMBEDDING_MISMATCH"


def index_models(cur: Any) -> list[dict[str, Any]]:
    """색인에 쓰인 임베딩 모델과 청크 수. 많은 것부터."""
    return fetch_all(
        cur,
        """
        select embedding_model as model, count(*) as chunks
          from doc_chunk group by embedding_model order by count(*) desc
        """,
    )


def mismatch(cur: Any, configured: str) -> str | None:
    """설정과 다른 모델로 만든 색인이 있으면 그 이유 문장. 맞으면 None."""
    others = [r for r in index_models(cur) if r["model"] != configured]
    if not others:
        return None
    found = ", ".join(f"{r['model']} {r['chunks']}조각" for r in others)
    return (
        f"검색 모델이 색인과 다릅니다. 설정은 {configured} 인데 색인에 {found}이 있습니다. "
        "벡터를 섞지 않으려고 문서 검색과 색인을 멈췄습니다. 관리자가 검색 모델 설정을 색인에 "
        "맞추면 다시 됩니다."
    )


def require_match(cur: Any, configured: str, replacing: list[str] | None = None) -> None:
    """검색·색인마다 부른다. 다른 모델 청크가 하나라도 있는지만 먼저 보고, 있을 때만 집계한다.

    replacing 은 이번 색인이 지우고 새로 쓰는 소스('유형:ID')다. 그 소스의 낡은 벡터는 곧
    지워지므로 섞임으로 보지 않는다. 같은 본문의 다른 모델 벡터를 갈아 끼우는 복구 경로다.
    그 밖에 다른 모델 청크가 남아 있으면 새로 쓰지 않는다.
    """
    other = fetch_one(
        cur,
        """
        select 1 from doc_chunk
         where embedding_model <> %s
           and source_type || ':' || source_id::text <> all(%s::text[])
         limit 1
        """,
        (configured, replacing or []),
    )
    if other is None:
        return
    raise errors.ApiError(503, MISMATCH, mismatch(cur, configured) or "")
