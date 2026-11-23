"""원본(raw_artifact) → 표준 모델 승격 → 색인.

수집이 원본을 쌓아 두면 여기서 표준 모델로 올린다. 승격과 색인을 한 흐름에 두는 이유는
"색인은 됐는데 표준 모델에는 없다" 같은 어긋남을 만들지 않기 위해서다.

색인 대상은 사람이 쓴 문장이 있는 것뿐이다 — requirement 와 issue. code_change 는
커밋 메시지 한 줄이라 검색 근거로 쓸 게 없고, 데이터모델도 색인 대상에서 뺐다.
"""

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai.port import EmbeddingPort
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.config import settings
from app.db import fetch_all, fetch_one
from app.document import extractor
from app.rag import indexing
from app.standard import (
    mapping,
    mapping_redmine,
    repository,
    requirement_decision,
    requirement_index,
    work_product_type,
)
from app.standard.mapping_rules import MappingRules
from app.standard.models import (
    IssueCodeChange,
    IssueKindCounts,
    IssueMilestone,
    IssueRelation,
    IssueRequirement,
    IssueResponse,
    IssueSourceCount,
    IssueSummaryResponse,
    RequirementResponse,
    SourceRef,
    WorkProductChecklistResponse,
    WorkProductResponse,
    WorkProductVersionResponse,
)


@dataclass
class PromoteResult:
    upserted: int = 0
    unmapped: int = 0
    raw_only: int = 0    # 원본 보존이 목적인 종류(마일스톤·버전·트래커). 실패가 아니다
    indexed: int = 0
    unchanged: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    index_error: str | None = None


def promote_connection(cur: Any, connection: dict[str, Any], port: EmbeddingPort) -> PromoteResult:
    """한 연결이 수집한 원본 전부를 표준 모델로 올리고 색인한다."""
    project_id = str(connection["project_id"])
    connection_id = str(connection["id"])
    rules = MappingRules.from_json(connection.get("mapping_rules_json"))
    result = PromoteResult()
    sources: list[indexing.IndexSource] = []

    if connection["tool"] == "REDMINE":
        return _promote_redmine(cur, connection, rules, port, result, sources)

    # 원본은 종류 이름 순서로 읽혀 이슈가 마일스톤보다 먼저 온다. 잇기는 다 읽은 뒤에 한다
    milestone_links: list[tuple[str, int | None]] = []
    for raw in _raw_artifacts(cur, connection_id):
        payload, kind, external_id = raw["payload_jsonb"], raw["object_kind"], raw["external_id"]

        if kind == "issue":
            # 이슈는 모두 일반 이슈다. 요구사항은 명세서(기준선)로만 만든다(ARC-030).
            # 예전에 이슈로 만든 요구사항이 있으면 그 이슈는 그 요구사항의 열림·닫힘만 바꾼다
            own = repository.find_requirement_by_source(cur, connection_id, external_id)
            if own is not None:
                # 요구사항 색인은 이슈 글이 아니라 요구사항 정의로 만든다(_finish_indexing)
                rec = mapping.to_requirement(payload)
                repository.update_requirement_evidence(
                    cur, str(own["id"]), connection_id, external_id, rec
                )
                target = "REQUIREMENT"
            else:
                rec = mapping.to_issue(payload, rules)
                row_id = repository.upsert_issue(cur, project_id, connection_id, external_id, rec)
                milestone_links.append((row_id, mapping.milestone_number(payload)))
                target = "ISSUE"
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
        elif kind == "milestone":
            # 이름·기한·상태를 일반 이슈 화면에 보인다(ARC-023). 일정 준수율은 SWFR.PIP.007 몫이다
            rec = mapping.to_milestone(payload)
            repository.upsert_milestone(cur, project_id, connection_id, external_id, rec)
            target = "MILESTONE"
        elif kind in ("tree", "design_doc"):
            # 원본 보존이 목적이다. 산출물 판정(ARC-016)이 여기서 읽는다.
            # 저장소 설계 문서는 산출물로 올리지 않는다. 원본이 곧 설계 근거의 출발점이다(ARC-024)
            result.raw_only += 1
            continue
        elif kind == "file":
            product_type = rules.file_map.get(payload.get("path", ""))
            rec = mapping.to_work_product(payload, product_type) if product_type else None
            if rec is None:
                result.unmapped += 1
                continue
            _store_file(project_id, payload)
            row_id = repository.upsert_work_product(
                cur, project_id, connection_id, external_id, rec
            )
            found = _file_source(cur, project_id, row_id, rec, payload)
            if found is not None:
                sources.append(found)
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

    repository.link_issue_milestones(cur, connection_id, milestone_links)
    return _finish_indexing(cur, port, result, sources, project_id)


def _promote_redmine(
    cur: Any,
    connection: dict[str, Any],
    rules: MappingRules,
    port: EmbeddingPort,
    result: PromoteResult,
    sources: list[indexing.IndexSource],
) -> PromoteResult:
    """Redmine 원본을 표준 모델로 올린다.

    이슈는 리스크 트래커면 risk 로, 나머지는 issue 로. 버전은 마일스톤으로 올리고 이슈의
    fixed_version 으로 잇는다(일정 준수율 자료, GH-214). 트래커는 원본 보존만 한다.
    """
    project_id = str(connection["project_id"])
    connection_id = str(connection["id"])
    base_url = connection["base_url"]
    # 원본은 종류 이름 순서로 읽혀 issue 가 version 보다 먼저 온다. 잇기는 다 읽은 뒤에 한다
    milestone_links: list[tuple[str, int | None]] = []

    for raw in _raw_artifacts(cur, connection_id):
        payload, kind, external_id = raw["payload_jsonb"], raw["object_kind"], raw["external_id"]

        if kind == "version":
            rec = mapping_redmine.to_milestone(payload, base_url)
            repository.upsert_milestone(cur, project_id, connection_id, external_id, rec)
            result.upserted += 1
            result.by_type["MILESTONE"] = result.by_type.get("MILESTONE", 0) + 1
            continue
        if kind != "issue":
            result.raw_only += 1
            continue

        if mapping_redmine.is_risk(payload, rules):
            rec = mapping_redmine.to_risk(payload, base_url)
            repository.upsert_risk(cur, project_id, connection_id, external_id, rec)
            target = "RISK"
            # 리스크는 색인하지 않는다 — 색인 대상은 requirement 와 issue 다(모듈 머리말)
        else:
            rec = mapping_redmine.to_issue(payload, base_url, rules)
            row_id = repository.upsert_issue(cur, project_id, connection_id, external_id, rec)
            milestone_links.append((row_id, mapping_redmine.version_number(payload)))
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

    repository.link_issue_milestones(cur, connection_id, milestone_links)
    return _finish_indexing(cur, port, result, sources, project_id)


def _finish_indexing(
    cur: Any,
    port: EmbeddingPort,
    result: PromoteResult,
    sources: list[indexing.IndexSource],
    project_id: str,
) -> PromoteResult:
    # 사업의 요구사항 색인을 정의대로 맞춘다. 바뀐 것만 임베딩한다. 기준선 확정 때 색인을
    # 못 했어도 여기서 채워진다(점검 DATA-02)
    sources = [*sources, *requirement_index.sources(cur, project_id)]
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
        connectionName=row.get("connection_name"),
        target=row.get("target_resource"),
        number=_source_number(row["external_id"]),
    )


_REQ_CODE_RE = re.compile(r"\b([A-Z]{2,5}(?:\.[A-Z]{2,5})+\.\d{3})\b")


def _source_details(row: dict[str, Any]) -> dict[str, Any]:
    """원시본에서 트래커·요구사항 ID 커스텀 필드·이슈관계를 읽는다(AC-043-2, GH-224).

    표준 모델에 열을 더하지 않고 보관된 원본을 그대로 보인다. 원본이 곧 근거다."""
    payload = row.get("raw_payload") or {}
    if row.get("tool_name") != "REDMINE" or not isinstance(payload, dict):
        return {"tracker": None, "requirementRefs": [], "relations": []}
    tracker = ((payload.get("tracker") or {}).get("name") or "").strip() or None
    refs: list[str] = []
    for custom in payload.get("custom_fields") or []:
        value = custom.get("value")
        values = value if isinstance(value, list) else [value]
        for v in values:
            for code in _REQ_CODE_RE.findall(str(v or "")):
                if code not in refs:
                    refs.append(code)
    own = str(payload.get("id") or "")
    relations = [
        IssueRelation(
            type=str(rel.get("relation_type") or "relates"),
            issueKey=f"RM-{rel['issue_to_id']}",
        )
        for rel in payload.get("relations") or []
        if str(rel.get("issue_id") or "") == own and rel.get("issue_to_id")
    ]
    return {"tracker": tracker, "requirementRefs": refs, "relations": relations}


def _source_number(external_id: str | None) -> str | None:
    """GitHub 은 'issue:12', Redmine 일감은 '12' 로 들어온다. 화면에는 번호만 낸다."""
    if not external_id:
        return None
    return external_id.rsplit(":", 1)[-1]


def list_requirements(
    cur: Any, principal: AuthPrincipal, project_id: str, q: str | None, page: PageQuery
) -> PageResponse[RequirementResponse]:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()

    f = repository.RequirementFilter(q=q)
    total = repository.count_requirements(cur, project_id, f)
    rows = repository.search_requirements(cur, project_id, f, page)
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
            statusBasis=requirement_decision.status_basis(r),
            evidenceStatus=r["evidence_status"],
            decision=requirement_decision.decision_of(r),
            inBaseline=r["baseline_id"] is not None,
        )
        for r in rows
    ]
    return PageResponse.of(content, page, total)


def _check_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def _issue_kind(kind: str | None) -> str:
    kind = (kind or "GENERAL").upper()
    if kind not in repository.ISSUE_KINDS:
        raise errors.validation_failed("kind 는 GENERAL·DEFECT·ALL 중 하나여야 합니다.")
    return kind


def _kind_counts(cur: Any, project_id: str, connection_id: str | None) -> IssueKindCounts:
    from app.dashboard import repository as dashboard_repo  # 순환 import 를 피한다

    n = repository.issue_kind_counts(cur, project_id, connection_id)
    mapped = dashboard_repo.defect_mapped(cur, project_id)
    if not mapped:
        rate, note = None, (
            "산출 불가: 연결 설정에 결함 트래커(Redmine)·결함 라벨(GitHub)이 없어 결함을 가를 수 "
            "없습니다. 수집한 이슈 전부를 일반 이슈로 셉니다"
        )
    elif not n["defect_total"]:
        rate, note = None, "산출 불가: 결함으로 분류된 이슈가 없습니다"
    else:
        rate = round(n["defect_closed"] / n["defect_total"], 4)
        note = "결함 처리율 = 해결·종료 결함 ÷ 전체 결함"
    return IssueKindCounts(
        allTotal=n["all_total"],
        generalTotal=n["general_total"],
        defectTotal=n["defect_total"],
        defectOpen=n["defect_open"],
        defectClosed=n["defect_closed"],
        defectMapped=mapped,
        defectRate=rate,
        defectNote=note,
    )


def issue_summary(
    cur: Any, principal: AuthPrincipal, project_id: str, connection_id: str | None = None,
    kind: str | None = None,
) -> IssueSummaryResponse:
    """이슈 화면 카드. 목록(list_issues)과 같은 권한 검사, 같은 사업 범위다."""
    _check_project(cur, principal, project_id)
    kind = _issue_kind(kind)
    n = repository.issue_summary(cur, project_id, connection_id, kind)
    return IssueSummaryResponse(
        total=n["total"],
        open=n["open"],
        closed=n["closed"],
        heavyOpen=n["heavy_open"],
        unassignedOpen=n["unassigned_open"],
        unspecifiedOpen=n["unspecified_open"],
        sources=[
            IssueSourceCount(
                connectionId=str(r["connection_id"]) if r["connection_id"] else None,
                tool=r["tool"],
                name=r["name"],
                target=r["target_resource"],
                count=int(r["n"]),
            )
            for r in repository.issue_sources(cur, project_id, kind)
        ],
        kind=kind,
        kinds=_kind_counts(cur, project_id, connection_id),
    )


def list_issues(
    cur: Any,
    principal: AuthPrincipal,
    project_id: str,
    q: str | None,
    status: str | None,
    page: PageQuery,
    connection_id: str | None = None,
    kind: str | None = None,
) -> PageResponse[IssueResponse]:
    _check_project(cur, principal, project_id)
    kind = _issue_kind(kind)

    total = repository.count_issues(cur, project_id, q, status, connection_id, kind)
    rows = repository.search_issues(cur, project_id, q, status, page, connection_id, kind)
    linked: dict[str, list[IssueRequirement]] = {}
    for link in repository.issue_requirements(cur, [str(r["id"]) for r in rows]):
        linked.setdefault(str(link["issue_id"]), []).append(
            IssueRequirement(id=str(link["id"]), code=link["code"], title=link["title"])
        )
    changes: dict[str, list[IssueCodeChange]] = {}
    for c in repository.issue_code_changes(cur, [str(r["id"]) for r in rows]):
        changes.setdefault(str(c["issue_id"]), []).append(
            IssueCodeChange(
                id=str(c["id"]), kind=c["kind"], title=c["title"], refName=c["ref_name"],
                state=c["state"], author=c["author"], occurredAt=c["occurred_at"].isoformat(),
                url=c["external_url"],
            )
        )
    content = [
        IssueResponse(
            id=str(r["id"]),
            projectId=str(r["project_id"]),
            key=r["issue_key"] or "",
            title=r["title"],
            status=r["status"],
            severity=r["severity"],
            sourcePriority=r["source_priority"],
            assignee=r["assignee"],
            resolvedAt=r["resolved_at"].isoformat() if r["resolved_at"] else None,
            source=_source_ref(r),
            updatedAt=(r["source_updated_at"] or r["updated_at"]).isoformat(),
            milestone=_milestone(r),
            kind=r["issue_kind"],
            requirements=linked.get(str(r["id"]), []),
            codeChanges=changes.get(str(r["id"]), []),
            **_source_details(r),
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


def _file_source(
    cur: Any, project_id: str, row_id: str | None, rec: dict[str, Any], payload: dict[str, Any]
) -> indexing.IndexSource | None:
    """수집한 파일도 업로드 문서처럼 읽어 색인한다(DEF-V031, SWFR.RAG.003).

    산출물 행 하나는 파일 한 판(sha)이라 내용이 바뀌지 않는다. 이미 색인한 행은 다시 읽지 않는다.
    새 판이 현행이 되면 같은 항목의 지난 판 조각은 지운다. 검색이 낡은 내용을 출처로 내면 안 된다.
    XLSX 는 시트를 표제로, 엑셀 행 번호를 첫 열로 남겨 출처에 「시트 · 행」이 붙는다.
    """
    path = payload.get("path", "")
    if row_id is None or not extractor.is_supported(path) or not payload.get("sha"):
        return None
    cur.execute(
        """
        delete from doc_chunk c
         using work_product w
         where c.source_type = 'WORK_PRODUCT' and c.source_id = w.id
           and w.project_id = %s and w.type = %s and w.id <> %s
        """,
        (project_id, rec["type"], row_id),
    )
    if fetch_one(
        cur,
        "select 1 from doc_chunk where source_type = 'WORK_PRODUCT' and source_id = %s limit 1",
        (row_id,),
    ):
        return None
    stored = (
        Path(settings.document_root) / project_id / "repo"
        / f"{payload['sha']}{Path(path).suffix}"
    )
    if not stored.exists():
        return None
    try:
        ext = extractor.ext_of(path)
        text = extractor.extract(stored, ext).text
    except Exception:  # noqa: BLE001 — 파일 하나를 못 읽어도 승격은 이어간다
        return None
    if not text.strip():
        return None
    return indexing.IndexSource(
        source_type="WORK_PRODUCT", source_id=row_id, project_id=project_id,
        title=rec["title"], body=text, uri=rec["external_url"],
        block_positions=ext in extractor.BLOCK_POSITION_EXTS,
    )


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
    history: dict[str, list[WorkProductVersionResponse]] = {}
    for p in repository.list_past_work_products(cur, project_id):
        decided = p["decided_kind"] is not None
        history.setdefault(p["type"], []).append(WorkProductVersionResponse(
            id=str(p["id"]),
            version=p["version"],
            title=p["title"],
            status=p["status"],
            submittedAt=_iso(p["submitted_at"]),
            rejectReason=p["reject_reason"],
            decidedBy=p["decided_by"] if decided else p["approved_by"],
            decidedAt=_iso(p["decided_at"] if decided else p["approved_at"]),
        ))
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
            previousVersions=history.get(r["type"], []),
        )
        for r in rows
    ]
    return WorkProductChecklistResponse(
        projectId=project_id,
        approvedCount=sum(1 for i in items if i.status == "APPROVED"),
        totalCount=len(items),
        items=items,
    )


def _milestone(r: dict[str, Any]) -> IssueMilestone | None:
    if r.get("milestone_title") is None:
        return None
    due = r.get("milestone_due_on")
    return IssueMilestone(
        title=r["milestone_title"],
        dueOn=due.isoformat() if due else None,
        state=r["milestone_state"],
        url=r.get("milestone_url"),
    )
