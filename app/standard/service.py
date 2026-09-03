"""원본(raw_artifact) → 표준 모델 승격 → 색인.

수집이 원본을 쌓아 두면 여기서 표준 모델로 올린다. 승격과 색인을 한 흐름에 두는 이유는
"색인은 됐는데 표준 모델에는 없다" 같은 어긋남을 만들지 않기 위해서다.

색인 대상은 사람이 쓴 문장이 있는 것뿐이다 — requirement 와 issue. code_change 는
커밋 메시지 한 줄이라 검색 근거로 쓸 게 없고, 데이터모델도 색인 대상에서 뺐다.
"""

from dataclasses import dataclass, field
from typing import Any

from app.ai.port import EmbeddingPort
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.db import fetch_all
from app.rag import indexing
from app.standard import mapping, repository
from app.standard.models import RequirementResponse, SourceRef


@dataclass
class PromoteResult:
    upserted: int = 0
    unmapped: int = 0
    indexed: int = 0
    unchanged: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    index_error: str | None = None


def promote_connection(cur: Any, connection: dict[str, Any], port: EmbeddingPort) -> PromoteResult:
    """한 연결이 수집한 원본 전부를 표준 모델로 올리고 색인한다."""
    project_id = str(connection["project_id"])
    connection_id = str(connection["id"])
    result = PromoteResult()
    sources: list[indexing.IndexSource] = []

    for raw in _raw_artifacts(cur, connection_id):
        payload, kind, external_id = raw["payload_jsonb"], raw["object_kind"], raw["external_id"]

        if kind == "issue":
            target = mapping.classify_issue(payload)
            if target == "REQUIREMENT":
                rec = mapping.to_requirement(payload)
                row_id = repository.upsert_requirement(
                    cur, project_id, connection_id, external_id, rec
                )
            else:
                rec = mapping.to_issue(payload)
                row_id = repository.upsert_issue(cur, project_id, connection_id, external_id, rec)
            sources.append(
                indexing.IndexSource(
                    source_type=target,
                    source_id=row_id,
                    project_id=project_id,
                    title=rec["title"],
                    body=rec["body"],
                    uri=rec["external_url"],
                )
            )
        else:
            rec = mapping.to_code_change(kind, payload)
            if rec is None:
                result.unmapped += 1
                continue
            repository.upsert_code_change(cur, project_id, connection_id, external_id, rec)
            target = "CODE_CHANGE"

        result.upserted += 1
        result.by_type[target] = result.by_type.get(target, 0) + 1

    # 모델이 죽어 있다고 승격까지 되돌리지 않는다. 표준 모델은 남기고 색인만 못 했다고 적는다.
    try:
        indexed = indexing.reindex(cur, port, sources)
    except errors.ApiError as exc:
        if not exc.code.startswith("AI_"):
            raise
        result.index_error = exc.message
        return result

    result.indexed = indexed.chunks
    result.unchanged = indexed.unchanged
    return result


def _raw_artifacts(cur: Any, connection_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select external_id, object_kind, payload_jsonb
          from raw_artifact
         where tool_connection_id = %s
         order by object_kind, external_id
        """,
        (connection_id,),
    )


# --- 조회 ---------------------------------------------------------------


def _source_ref(row: dict[str, Any]) -> SourceRef:
    """원천 표기. 도구에서 온 것이면 도구 이름을, 아니면 업로드·수기로 구분한다."""
    tool = row["tool_name"] or ("UPLOAD" if row["source_kind"] == "DOCUMENT" else "MANUAL")
    return SourceRef(
        tool=tool,
        connectionId=str(row["tool_connection_id"]) if row["tool_connection_id"] else None,
        externalId=row["external_id"],
        externalUrl=row["external_url"],
    )


def list_requirements(
    cur: Any, principal: AuthPrincipal, project_id: str, q: str | None, page: PageQuery
) -> PageResponse[RequirementResponse]:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()

    total = repository.count_requirements(cur, project_id, q)
    rows = repository.search_requirements(cur, project_id, q, page)
    content = [
        RequirementResponse(
            id=str(r["id"]),
            projectId=str(r["project_id"]),
            # 코드가 없는 요구사항도 있다. 화면이 빈 칸을 못 그리므로 하이픈으로 채운다.
            code=r["code"] or "—",
            title=r["title"],
            priority=r["priority"],
            status=r["status"],
            assignee=r["assignee"],
            source=_source_ref(r),
            traceComplete=r["trace_complete"],
            updatedAt=r["updated_at"].isoformat(),
        )
        for r in rows
    ]
    return PageResponse.of(content, page, total)
