"""원본(raw_artifact) → 표준 모델 승격 → 색인.

수집이 원본을 쌓아 두면 여기서 표준 모델로 올린다. 승격과 색인을 한 흐름에 두는 이유는
"색인은 됐는데 표준 모델에는 없다" 같은 어긋남을 만들지 않기 위해서다.

색인 대상은 사람이 쓴 문장이 있는 것뿐이다 — requirement 와 issue. code_change 는
커밋 메시지 한 줄이라 검색 근거로 쓸 게 없고, 데이터모델도 색인 대상에서 뺐다.
"""

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai.port import EmbeddingPort
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.config import settings
from app.db import fetch_all
from app.rag import indexing
from app.standard import mapping, mapping_redmine, repository, work_product_type
from app.standard.models import (
    RequirementResponse,
    SourceRef,
    WorkProductChecklistResponse,
    WorkProductResponse,
)


@dataclass
class PromoteResult:
    upserted: int = 0
    unmapped: int = 0
    raw_only: int = 0    # 원본 보존이 목적인 종류(버전·트래커). 실패가 아니다
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

    if connection["tool"] == "REDMINE":
        return _promote_redmine(cur, connection, port, result, sources)

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
        elif kind == "file":
            product_type = settings.collect_file_map.get(payload.get("path", ""))
            rec = mapping.to_work_product(payload, product_type) if product_type else None
            if rec is None:
                result.unmapped += 1
                continue
            _store_file(project_id, payload)
            repository.upsert_work_product(cur, project_id, connection_id, external_id, rec)
            target = "WORK_PRODUCT"
        else:
            rec = mapping.to_code_change(kind, payload)
            if rec is None:
                result.unmapped += 1
                continue
            repository.upsert_code_change(cur, project_id, connection_id, external_id, rec)
            target = "CODE_CHANGE"

        result.upserted += 1
        result.by_type[target] = result.by_type.get(target, 0) + 1

    return _finish_indexing(cur, port, result, sources)


def _promote_redmine(
    cur: Any,
    connection: dict[str, Any],
    port: EmbeddingPort,
    result: PromoteResult,
    sources: list[indexing.IndexSource],
) -> PromoteResult:
    """Redmine 원본을 표준 모델로 올린다.

    이슈만 승격한다 — 리스크 트래커는 risk 로, 나머지는 issue 로. 버전·트래커는 원본
    보존이 목적이라(마일스톤 지표는 SWFR.PIP.007 에서 쓴다) raw_only 로 센다.
    """
    project_id = str(connection["project_id"])
    connection_id = str(connection["id"])
    base_url = connection["base_url"]

    for raw in _raw_artifacts(cur, connection_id):
        payload, kind, external_id = raw["payload_jsonb"], raw["object_kind"], raw["external_id"]

        if kind != "issue":
            result.raw_only += 1
            continue

        if mapping_redmine.is_risk(payload):
            rec = mapping_redmine.to_risk(payload, base_url)
            repository.upsert_risk(cur, project_id, connection_id, external_id, rec)
            target = "RISK"
            # 리스크는 색인하지 않는다 — 색인 대상은 requirement 와 issue 다(모듈 머리말)
        else:
            rec = mapping_redmine.to_issue(payload, base_url)
            row_id = repository.upsert_issue(cur, project_id, connection_id, external_id, rec)
            target = "ISSUE"
            sources.append(
                indexing.IndexSource(
                    source_type="ISSUE",
                    source_id=row_id,
                    project_id=project_id,
                    title=rec["title"],
                    body=rec["body"],
                    uri=rec["external_url"],
                )
            )

        result.upserted += 1
        result.by_type[target] = result.by_type.get(target, 0) + 1

    return _finish_indexing(cur, port, result, sources)


def _finish_indexing(
    cur: Any,
    port: EmbeddingPort,
    result: PromoteResult,
    sources: list[indexing.IndexSource],
) -> PromoteResult:
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


def _store_file(project_id: str, payload: dict[str, Any]) -> None:
    """수집한 파일 본문을 업로드 문서와 같은 자리에 둔다.

    WBS 파서가 읽을 실체가 있어야 한다. 경로는 sha 로 잡아 같은 내용을 두 번 쓰지 않는다.
    """
    encoded = payload.get("content")
    sha = payload.get("sha")
    if not encoded or not sha:
        return
    suffix = Path(payload.get("path", "")).suffix
    target = Path(settings.document_root) / project_id / "repo" / f"{sha}{suffix}"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(encoded))


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def work_product_checklist(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> WorkProductChecklistResponse:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()

    rows = repository.list_work_products(cur, project_id)
    items = [
        WorkProductResponse(
            id=str(r["id"]),
            projectId=str(r["project_id"]),
            type=r["type"],
            displayName=work_product_type.display_name(r["type"]),
            title=r["title"],
            version=r["version"],
            status=r["status"],
            pmActivity=r["pm_activity"],
            siActivity=r["si_activity"],
            applicable=r["applicable"],
            dueDate=_iso(r["due_date"]),
            fileUri=r["file_uri"],
            externalUrl=r["external_url"],
            approvedBy=r["approved_by"],
            approvedAt=_iso(r["approved_at"]),
            updatedAt=r["updated_at"].isoformat(),
        )
        for r in rows
    ]
    return WorkProductChecklistResponse(
        projectId=project_id,
        approvedCount=sum(1 for i in items if i.status == "APPROVED"),
        totalCount=len(items),
        items=items,
    )
