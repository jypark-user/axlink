"""요구사항 검색 색인의 재료 (SWFR.PIP.003, 점검 DATA-02).

요구사항 색인은 늘 요구사항 행(코드·명칭·본문)으로 만든다. 출처 이슈의 제목·본문으로 만들면
기준선이 정의를 지킨 뒤에도 AI 검색 근거는 이슈 글을 보여 줘, 화면의 요구사항과 답의 근거가
달라진다(ARC-030). 이슈 글은 일반 이슈 색인이 맡는다.

기준선 확정과 수집 회차가 이것을 부른다. 본문이 그대로면 색인은 임베딩을 다시 만들지 않으므로
수집 회차마다 사업의 요구사항 전부를 넘겨도 된다. 확정 때 모델이 안 돼 색인을 못 했으면 다음
수집 회차가 채운다. 연결이 없는 사업은 채울 회차가 없다(확정을 다시 하지 않는 한).
"""

from typing import Any

from app.db import fetch_all
from app.rag import indexing


def sources(cur: Any, project_id: str, ids: list[str] | None = None) -> list[indexing.IndexSource]:
    """사업의 요구사항(ids 를 주면 그것만)을 색인 재료로."""
    sql = "select id, code, title, body, external_url from requirement where project_id = %s"
    params: list[Any] = [project_id]
    if ids is not None:
        sql += " and id = any(%s::uuid[])"
        params.append(ids)
    return [
        indexing.IndexSource(
            source_type="REQUIREMENT",
            source_id=str(r["id"]),
            project_id=project_id,
            title=f"{r['code']} {r['title']}" if r["code"] else r["title"],
            body=r["body"] or "",
            uri=r["external_url"],
        )
        for r in fetch_all(cur, sql + " order by code nulls last, id", tuple(params))
    ]
