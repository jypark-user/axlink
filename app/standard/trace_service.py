"""추적관계 생성과 조회 (SWFR.PIP.003 · SWFR.PIP.004 · SWFR.WEB.002).

생성은 사업 단위로 돈다. 커밋(GitHub)이 Redmine 이슈를 가리키고 Redmine 이슈가 GitHub
요구사항을 가리키므로, 연결 하나만 보고는 양 끝을 못 찾는다. 승격이 끝난 뒤 사업 전체의
원본을 다시 훑어 링크를 만들고, 이번에 근거가 다시 확인되지 않은 자동 링크는 끊긴 것으로
표시한다. 몇 번을 돌려도 결과는 같다.

링크의 방향은 "무엇이 요구사항을 어떻게 하는가" 다. 이슈·커밋·산출물이 출발점이고
요구사항이 도착점이다. 요구사항 목록의 traceComplete 와 사업 지표의 추적 커버리지가
같은 방향으로 읽는다.
"""

from dataclasses import dataclass, field
from typing import Any

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.standard import repository, requirement_decision, trace_rules
from app.standard.mapping_rules import MappingRules
from app.standard.models import (
    EntityHistoryResponse,
    RequirementBaselineSource,
    RequirementDetailResponse,
    RequirementSummaryResponse,
    SourceRef,
    SourceStateSummary,
    StatusCount,
    TraceabilityRowResponse,
    TraceCell,
    TraceLinkResponse,
)
from app.standard.trace_rules import Evidence, Exclusion

_TOOL_PREFIX = {"GITHUB": "GH", "REDMINE": "RM"}


@dataclass
class BuildResult:
    active: int = 0     # 이번에 근거가 확인된 링크(신규 + 유지)
    broken: int = 0     # 원천 근거가 사라져 끊긴 것으로 표시한 링크
    superseded: int = 0  # 분류 정정으로 다른 링크에 대체됐거나 제외된 링크(ARC-024 2-5)
    unresolved: int = 0  # 근거는 있으나 가리킨 대상이 표준 모델에 없어 만들지 않은 것
    ambiguous: int = 0  # 다른 도구 GH-n·RM-n 중 그 도구 연결이 여럿이라 고르지 않은 참조
    by_evidence: dict[str, int] = field(default_factory=dict)
    unknown_codes: int = 0  # 사업에 없는 요구사항 코드를 가리킨 근거의 코드 수(GH-139)


class _AnyCode(frozenset):
    """근거 규칙에 넘기는 코드 집합. 꼴만 맞으면 다 받는다. 사업에 있는지는 resolve 가 본다."""

    def __contains__(self, item: object) -> bool:
        return isinstance(item, str)


@dataclass(frozen=True)
class _Edge:
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    link_kind: str


def build_project_links(cur: Any, project_id: str) -> BuildResult:
    """사업의 원본 전부에서 추적관계를 다시 만든다. 재실행해도 중복이 생기지 않는다."""
    codes = repository.requirement_codes(cur, project_id)
    known_codes = set(codes)
    # 요구사항 코드 꼴이면 일단 근거로 읽는다. 사업에 없는 코드는 잇지 않고 미해결로 남긴다.
    # 전에는 규칙 단계에서 오타로 보고 버려서 화면에 안 보였다(GH-139)
    candidate_codes = _AnyCode()
    products = repository.current_work_product_paths(cur, project_id)
    known_paths = set(products)
    index = repository.tool_entity_index(cur, project_id)
    connections = repository.project_connections(cur, project_id)
    # GH-n / RM-n 은 도구만 말하고 연결은 말하지 않는다(GH-140). 같은 도구의 연결이 둘이면
    # 번호가 겹칠 수 있다. 근거가 나온 연결이 그 도구면 그 연결에서 찾고, 다른 도구를 가리키면
    # 그 도구의 연결이 하나일 때만 잇는다. 둘 이상이면 고르지 않고 미해결로 센다.
    by_prefix: dict[str, list[str]] = {}
    for c in connections:
        if c["tool"] in _TOOL_PREFIX:
            by_prefix.setdefault(_TOOL_PREFIX[c["tool"]], []).append(str(c["id"]))

    result = BuildResult()
    planned: dict[_Edge, tuple[Evidence, str | None]] = {}
    excluded: dict[tuple[str, str, str, str], str] = {}
    deleted_docs: set[str] = set()
    ambiguous: set[tuple[str, str]] = set()
    unknown_refs: dict[tuple[str, str, str], tuple[str, str | None]] = {}
    # (출발 유형, 출발 id, GH·RM, 번호) → 이번에 그 참조로 이은 링크 id. 대상을 못 정했으면 None.
    # 같은 참조가 예전에 다른 연결의 대상에 이어져 있었으면 끊김이 아니라 정정이다(ARC-027 3절)
    rerouted: dict[tuple[str, str, str, str], str | None] = {}

    def resolve(target: tuple[str, str], origin: dict[str, Any]) -> tuple[str, str] | None:
        ref, value = target
        if ref == "REQ":
            return ("REQUIREMENT", codes[value]) if value in known_codes else None
        if ref == "FILE":
            return ("WORK_PRODUCT", products[value][0]) if value in products else None
        if _TOOL_PREFIX.get(origin["tool"]) == ref:
            connection_id = str(origin["id"])
        else:
            candidates = by_prefix.get(ref, [])
            if len(candidates) != 1:
                if len(candidates) > 1:
                    ambiguous.add(target)
                return None
            connection_id = candidates[0]
        external_id = f"issue:{value}" if ref == "GH" else value
        return index.get((connection_id, external_id))

    for connection in connections:
        rules = MappingRules.from_json(connection.get("mapping_rules_json"))
        raws = repository.raw_artifacts_with_entities(cur, str(connection["id"]))
        pr_refs = _pull_request_refs(raws, rules, candidate_codes, known_paths)
        for raw in raws:
            if raw["object_kind"] == "design_doc" and (raw["payload_jsonb"] or {}).get("deleted"):
                deleted_docs.add(str(raw["raw_id"]))
            found, dropped = _evidence_of(
                connection["tool"], raw, rules, candidate_codes, known_paths, pr_refs,
                design_codes=known_codes,
            )
            for source, ex in dropped:
                target = resolve(ex.target, connection)
                if target is not None:
                    excluded[(source[0], source[1], target[0], target[1])] = ex.reason
            for source, evidence in found:
                target = resolve(evidence.target, connection)
                if target is None:
                    result.unresolved += 1
                    if evidence.target[0] == "REQ":
                        unknown_refs.setdefault(
                            (evidence.target[1], *source),
                            (evidence.text, evidence.url or raw["external_url"]),
                        )
                    if evidence.target in ambiguous:
                        rerouted.setdefault((*source, *evidence.target), None)
                    continue
                edge = _edge(source, target, evidence, products)
                if edge is None:
                    continue
                # 같은 변에 근거가 여럿이면 먼저 찾은 것을 남긴다. 원본 순서가 곧 우선순위다.
                planned.setdefault(edge, (evidence, evidence.url or raw["external_url"]))

    kept: list[str] = []
    replaced: dict[tuple[str, str, str, str], list[tuple[str, str]]] = {}
    for edge, (evidence, url) in planned.items():
        link_id = repository.upsert_auto_trace_link(
            cur, project_id, edge.from_type, edge.from_id, edge.to_type, edge.to_id,
            edge.link_kind, evidence.kind, evidence.text, url, evidence.meta,
        )
        if link_id is None:
            continue  # 같은 변을 사람이 만들어 두었다. 자동 근거로 덮지 않는다.
        kept.append(link_id)
        if evidence.target[0] in _TOOL_PREFIX.values():
            key = (edge.from_type, edge.from_id, *evidence.target)
            if rerouted.get(key) is None:
                rerouted[key] = link_id
        replaced.setdefault(
            (edge.from_type, edge.from_id, edge.to_type, edge.to_id), []
        ).append((link_id, edge.link_kind))
        result.active += 1
        result.by_evidence[evidence.kind] = result.by_evidence.get(evidence.kind, 0) + 1

    result.ambiguous = len(ambiguous)
    result.unknown_codes = len({code for code, _, _ in unknown_refs})
    repository.replace_unresolved_refs(cur, project_id, unknown_refs)
    result.broken, result.superseded = repository.close_stale_auto_links(
        cur, project_id, kept, replaced, excluded, deleted_docs, rerouted
    )
    return result


def _pull_request_refs(
    raws: list[dict[str, Any]], rules: MappingRules, known_codes: set[str], known_paths: set[str]
) -> dict[str, set[tuple[tuple[str, str], str]]]:
    """PR 번호 → 그 PR 이 가진 (참조, 관계). 병합 커밋이 PR 과 실제로 겹치는지 보려고 쓴다."""
    out: dict[str, set[tuple[tuple[str, str], str]]] = {}
    for raw in raws:
        if raw["object_kind"] != "pull_request" or not raw["code_change_id"]:
            continue
        payload = raw["payload_jsonb"] or {}
        found, _ = trace_rules.pull_request_evidence_with_exclusions(
            payload, known_codes, known_paths, rules.design_globs
        )
        out[str(payload.get("number"))] = {(e.target, e.link_kind) for e in found}
    return out


def _evidence_of(
    tool: str, raw: dict[str, Any], rules: MappingRules,
    known_codes: set[str], known_paths: set[str],
    pr_refs: dict[str, set[tuple[tuple[str, str], str]]] | None = None,
    design_codes: set[str] | None = None,
) -> tuple[list[tuple[tuple[str, str], Evidence]], list[tuple[tuple[str, str], Exclusion]]]:
    """원본 하나에서 (출발점, 근거) 쌍과 분류가 일부러 뺀 근거를 뽑는다.

    승격되지 않은 원본은 출발점이 없다. 저장소 설계 문서는 승격하지 않고 원본 자체가 출발점이다.
    """
    payload, kind = raw["payload_jsonb"], raw["object_kind"]
    dropped: list[Exclusion] = []

    if tool == "GITHUB":
        if kind == "design_doc":
            source = ("REPO_DOCUMENT", str(raw["raw_id"]))
            # 설계 문서 판별은 사업의 실제 코드 목록이 필요하다(ARC-024 오탐 방지)
            found = trace_rules.design_doc_evidence(
                payload, known_codes if design_codes is None else design_codes
            )
        elif kind == "commit" and raw["code_change_id"]:
            source = ("CODE_CHANGE", str(raw["code_change_id"]))
            found, dropped = trace_rules.commit_evidence_with_exclusions(
                payload, known_codes, known_paths, rules.design_globs
            )
            pr = trace_rules.merged_pr_number(payload)
            if pr is not None and pr in (pr_refs or {}):
                # 같은 PR 이 같은 참조·관계를 이미 가진 것만 뺀다. PR 에 없는 근거는 남긴다
                same = pr_refs[pr]
                dropped += [
                    Exclusion(e.target, e.link_kind, f"병합 커밋: PR #{pr} 와 같은 근거")
                    for e in found if (e.target, e.link_kind) in same
                ]
                found = [e for e in found if (e.target, e.link_kind) not in same]
        elif kind == "pull_request" and raw["code_change_id"]:
            source = ("CODE_CHANGE", str(raw["code_change_id"]))
            found, dropped = trace_rules.pull_request_evidence_with_exclusions(
                payload, known_codes, known_paths, rules.design_globs
            )
        elif kind == "issue" and raw["requirement_id"]:
            source = ("REQUIREMENT", str(raw["requirement_id"]))
            found = trace_rules.requirement_issue_evidence(payload, known_paths)
        elif kind == "issue" and raw["issue_id"]:
            source = ("ISSUE", str(raw["issue_id"]))
            found = trace_rules.github_issue_evidence(payload, known_codes, known_paths)
        else:
            return [], []
    elif tool == "REDMINE" and kind == "issue":
        if raw["issue_id"]:
            source = ("ISSUE", str(raw["issue_id"]))
        elif raw["risk_id"]:
            source = ("RISK", str(raw["risk_id"]))
        else:
            return [], []
        found = trace_rules.redmine_issue_evidence(payload, rules, known_codes, known_paths)
    else:
        return [], []
    return [(source, e) for e in found], [(source, x) for x in dropped]


def _edge(
    source: tuple[str, str], target: tuple[str, str], evidence: Evidence,
    products: dict[str, tuple[str, str]],
) -> _Edge | None:
    """출발점·도착점·근거로 변 하나를 정한다. 요구사항은 언제나 도착점이다."""
    if source == target:
        return None

    if source[0] == "REQUIREMENT" and target[0] == "WORK_PRODUCT":
        # 요구사항 이슈 본문이 산출물을 가리켰다. 산출물이 요구사항에 이어진 것으로 뒤집는다.
        product_type = next(t for i, t in products.values() if i == target[1])
        return _Edge("WORK_PRODUCT", target[1], "REQUIREMENT", source[1],
                     trace_rules.product_link_kind(product_type))
    if source[0] == "REQUIREMENT":
        return None  # 요구사항이 출발점인 다른 변은 없다. 요구사항끼리도 잇지 않는다
    return _Edge(source[0], source[1], target[0], target[1], evidence.link_kind)


# --- 조회 ---------------------------------------------------------------


def _check_access(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def requirement_summary(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> RequirementSummaryResponse:
    """요구사항 화면 요약. 추적표 목록과 같은 권한 검사, 같은 사업 범위다."""
    _check_access(cur, principal, project_id)
    n = repository.requirement_summary(cur, project_id)
    total, verified = n["total"], n["verified"]
    rate_total, rate_verified = n["rate_total"], n["rate_verified"]
    return RequirementSummaryResponse(
        total=total,
        verified=verified,
        notVerified=total - verified,
        implementedFromSourceClosed=n["implemented_from_source_closed"],
        # 이행률은 확정 목록 기준(DEC-11). 명세서에 없는 기존 요구사항은 분모에서 뺀다
        verifiedRate=rate_verified / rate_total if rate_total else None,
        rateTotal=rate_total,
        rateVerified=rate_verified,
        outsideBaseline=total - rate_total,
        decided=n["decided"],
        byStatus=[
            StatusCount(status=s, count=n["by_status"].get(s, 0))
            for s in repository.REQUIREMENT_STATUSES
        ],
        sources=[_source_summary(s) for s in n["sources"]],
    )


def _source_summary(row: dict[str, Any]) -> SourceStateSummary:
    if row["connection_id"] is None:
        tool, label = "NONE", "출처 이슈 없음(명세서·직접 입력)"
    else:
        tool = row["tool"]
        label = f"{_TOOL_NAME.get(tool, tool)} {row['target_resource']}"
    return SourceStateSummary(
        connectionId=str(row["connection_id"]) if row["connection_id"] else None,
        tool=tool,
        label=label,
        total=int(row["total"]),
        open=int(row["open"]),
        closed=int(row["closed"]),
        unknown=int(row["unknown"]),
    )


_TOOL_NAME = {"GITHUB": "GitHub", "REDMINE": "Redmine"}


def traceability_rows(
    cur: Any,
    principal: AuthPrincipal,
    project_id: str,
    page: PageQuery,
    f: repository.RequirementFilter | None = None,
) -> PageResponse[TraceabilityRowResponse]:
    """요구사항 한 줄에 설계·구현·시험 칸. 메뉴와 AI 질의가 같은 함수를 쓴다."""
    _check_access(cur, principal, project_id)

    f = f or repository.RequirementFilter()
    total = repository.count_requirements(cur, project_id, f)
    reqs = repository.search_requirements(cur, project_id, f, page)
    links = repository.links_to_requirements(cur, [str(r["id"]) for r in reqs])
    labels = repository.entity_labels(
        cur, {(lk["from_type"], str(lk["from_id"])) for lk in links}
    )

    cells: dict[str, dict[str, list[TraceCell]]] = {}
    broken: dict[str, list[str]] = {}
    for lk in links:
        if lk["status"] == "SUPERSEDED":
            # 분류 정정으로 대체·제외된 링크는 칸에서 뺀다. 상세 목록에는 사유와 함께 남는다
            continue
        rid = str(lk["to_id"])
        label, url = labels.get((lk["from_type"], str(lk["from_id"])), ("?", None))
        meta = lk.get("evidence_meta") or {}
        if lk["from_type"] == "REPO_DOCUMENT":
            label = meta.get("docId") or label
            url = lk["evidence_url"] or url  # 그 커밋의 그 줄
        cells.setdefault(rid, {}).setdefault(lk["link_kind"], []).append(
            TraceCell(
                targetId=str(lk["from_id"]), label=label, externalUrl=url,
                sourceType=lk["from_type"], docStatus=meta.get("docStatus"),
                section=meta.get("section"), qualifier=meta.get("qualifier"),
            )
        )
        if lk["status"] == "BROKEN" and lk["link_kind"] not in broken.setdefault(rid, []):
            broken[rid].append(lk["link_kind"])

    content = [
        TraceabilityRowResponse(
            requirementId=str(r["id"]),
            requirementCode=r["code"] or "—",
            requirementTitle=r["title"],
            requirementStatus=r["status"],
            requirementStatusBasis=requirement_decision.status_basis(r),
            requirementEvidenceStatus=r["evidence_status"],
            requirementDecision=requirement_decision.decision_of(r),
            sourceState=r["source_state"],
            designs=cells.get(str(r["id"]), {}).get("DESIGNS", []),
            implementsList=cells.get(str(r["id"]), {}).get("IMPLEMENTS", []),
            tests=cells.get(str(r["id"]), {}).get("TESTS", []),
            brokenAt=broken.get(str(r["id"]), []),
        )
        for r in reqs
    ]
    return PageResponse.of(content, page, total)


def requirement_detail(
    cur: Any, principal: AuthPrincipal, project_id: str, requirement_id: str
) -> RequirementDetailResponse:
    """요구사항 하나와 거기 걸린 링크 전부. 링크마다 근거 원문과 위치가 붙는다."""
    _check_access(cur, principal, project_id)
    row = repository.get_requirement(cur, project_id, requirement_id)
    if row is None:
        raise errors.ApiError(404, "NOT_FOUND", "요구사항이 없습니다.")

    links = repository.links_touching(cur, "REQUIREMENT", requirement_id)
    refs = {(lk["from_type"], str(lk["from_id"])) for lk in links}
    refs |= {(lk["to_type"], str(lk["to_id"])) for lk in links}
    labels = repository.entity_labels(cur, refs)

    def label_of(entity_type: str, entity_id: str) -> str:
        return labels.get((entity_type, entity_id), ("?", None))[0]

    tool = row["tool_name"] or ("UPLOAD" if row["source_kind"] == "DOCUMENT" else "MANUAL")
    return RequirementDetailResponse(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        code=row["code"] or "—",
        title=row["title"],
        priority=row["priority"],
        status=row["status"],
        assignee=row["assignee"],
        source=SourceRef(
            tool=tool,
            connectionId=str(row["tool_connection_id"]) if row["tool_connection_id"] else None,
            externalId=row["external_id"],
            externalUrl=row["external_url"],
            connectionName=row.get("connection_name"),
            target=row.get("target_resource"),
            number=row["external_id"].rsplit(":", 1)[-1] if row["external_id"] else None,
        ),
        traceComplete=row["trace_complete"],
        updatedAt=row["updated_at"].isoformat(),
        statusBasis=requirement_decision.status_basis(row),
        evidenceStatus=row["evidence_status"],
        decision=requirement_decision.decision_of(row),
        inBaseline=row["baseline_id"] is not None,
        body=row["body"] or "",
        traceLinks=[
            TraceLinkResponse(
                id=str(lk["id"]),
                projectId=str(lk["project_id"]),
                fromType=lk["from_type"],
                fromId=str(lk["from_id"]),
                fromLabel=label_of(lk["from_type"], str(lk["from_id"])),
                toType=lk["to_type"],
                toId=str(lk["to_id"]),
                toLabel=label_of(lk["to_type"], str(lk["to_id"])),
                linkKind=lk["link_kind"],
                origin=lk["origin"],
                status=lk["status"],
                evidenceKind=lk["evidence_kind"],
                evidenceText=lk["evidence_text"],
                externalUrl=lk["evidence_url"],
                createdAt=lk["created_at"].isoformat(),
                evidenceMeta=lk.get("evidence_meta"),
                statusReason=lk.get("status_reason"),
                statusChangedAt=(
                    lk["status_changed_at"].isoformat() if lk.get("status_changed_at") else None
                ),
                supersededBy=str(lk["superseded_by"]) if lk.get("superseded_by") else None,
            )
            for lk in links
        ],
        history=[
            EntityHistoryResponse(
                id=str(h["id"]),
                entityType=h["entity_type"],
                entityId=str(h["entity_id"]),
                field=h["field"],
                fromValue=h["from_value"],
                toValue=h["to_value"],
                actor=h["actor"],
                actorName=None,
                changedAt=h["changed_at"].isoformat(),
            )
            for h in repository.entity_history(cur, "REQUIREMENT", requirement_id)
        ],
        baselineSource=_baseline_source(cur, requirement_id),
    )


def _baseline_source(cur: Any, requirement_id: str) -> RequirementBaselineSource | None:
    src = repository.requirement_baseline_source(cur, requirement_id)
    if src is None:
        return None
    return RequirementBaselineSource(
        baselineId=str(src["baseline_id"]),
        version=src["version"],
        status=src["status"],
        confirmedAt=src["confirmed_at"].isoformat() if src["confirmed_at"] else None,
        confirmedBy=src["confirmed_by_name"],
        documentId=str(src["document_upload_id"]) if src["document_upload_id"] else None,
        sourceFilename=src["source_filename"],
        sourceDocVersion=src["source_doc_version"],
        location=src["source_location"],
        match=src["match_result"],
    )
