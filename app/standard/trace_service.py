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
    RequirementDetailResponse,
    RequirementSummaryResponse,
    SourceRef,
    SourceStateSummary,
    StatusCount,
    TraceabilityRowResponse,
    TraceCell,
    TraceLinkResponse,
)
from app.standard.trace_rules import Evidence

_TOOL_PREFIX = {"GITHUB": "GH", "REDMINE": "RM"}


@dataclass
class BuildResult:
    active: int = 0     # 이번에 근거가 확인된 링크(신규 + 유지)
    broken: int = 0     # 근거가 사라져 끊긴 것으로 표시한 링크
    unresolved: int = 0  # 근거는 있으나 가리킨 대상이 표준 모델에 없어 만들지 않은 것
    by_evidence: dict[str, int] = field(default_factory=dict)


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
    products = repository.current_work_product_paths(cur, project_id)
    known_paths = set(products)
    index = repository.tool_entity_index(cur, project_id)
    connections = repository.project_connections(cur, project_id)
    by_prefix = {
        _TOOL_PREFIX[c["tool"]]: str(c["id"])
        for c in connections if c["tool"] in _TOOL_PREFIX
    }

    result = BuildResult()
    planned: dict[_Edge, tuple[Evidence, str | None]] = {}

    def resolve(target: tuple[str, str]) -> tuple[str, str] | None:
        ref, value = target
        if ref == "REQ":
            return ("REQUIREMENT", codes[value]) if value in known_codes else None
        if ref == "FILE":
            return ("WORK_PRODUCT", products[value][0]) if value in products else None
        connection_id = by_prefix.get(ref)
        if connection_id is None:
            return None
        external_id = f"issue:{value}" if ref == "GH" else value
        return index.get((connection_id, external_id))

    for connection in connections:
        rules = MappingRules.from_json(connection.get("mapping_rules_json"))
        for raw in repository.raw_artifacts_with_entities(cur, str(connection["id"])):
            for source, evidence in _evidence_of(
                connection["tool"], raw, rules, known_codes, known_paths
            ):
                target = resolve(evidence.target)
                if target is None:
                    result.unresolved += 1
                    continue
                edge = _edge(source, target, evidence, products)
                if edge is None:
                    continue
                # 같은 변에 근거가 여럿이면 먼저 찾은 것을 남긴다. 원본 순서가 곧 우선순위다.
                planned.setdefault(edge, (evidence, raw["external_url"]))

    kept: list[str] = []
    for edge, (evidence, url) in planned.items():
        link_id = repository.upsert_auto_trace_link(
            cur, project_id, edge.from_type, edge.from_id, edge.to_type, edge.to_id,
            edge.link_kind, evidence.kind, evidence.text, url,
        )
        if link_id is None:
            continue  # 같은 변을 사람이 만들어 두었다. 자동 근거로 덮지 않는다.
        kept.append(link_id)
        result.active += 1
        result.by_evidence[evidence.kind] = result.by_evidence.get(evidence.kind, 0) + 1

    result.broken = repository.break_stale_auto_links(cur, project_id, kept)
    return result


def _evidence_of(
    tool: str, raw: dict[str, Any], rules: MappingRules,
    known_codes: set[str], known_paths: set[str],
) -> list[tuple[tuple[str, str], Evidence]]:
    """원본 하나에서 (출발점, 근거) 쌍을 뽑는다. 승격되지 않은 원본은 출발점이 없다."""
    payload, kind = raw["payload_jsonb"], raw["object_kind"]

    if tool == "GITHUB":
        if kind == "commit" and raw["code_change_id"]:
            source = ("CODE_CHANGE", str(raw["code_change_id"]))
            found = trace_rules.commit_evidence(payload, known_codes, known_paths)
        elif kind == "pull_request" and raw["code_change_id"]:
            source = ("CODE_CHANGE", str(raw["code_change_id"]))
            found = trace_rules.pull_request_evidence(payload, known_codes, known_paths)
        elif kind == "issue" and raw["requirement_id"]:
            source = ("REQUIREMENT", str(raw["requirement_id"]))
            found = trace_rules.requirement_issue_evidence(payload, known_paths)
        elif kind == "issue" and raw["issue_id"]:
            source = ("ISSUE", str(raw["issue_id"]))
            found = trace_rules.github_issue_evidence(payload, known_codes, known_paths)
        else:
            return []
    elif tool == "REDMINE" and kind == "issue":
        if raw["issue_id"]:
            source = ("ISSUE", str(raw["issue_id"]))
        elif raw["risk_id"]:
            source = ("RISK", str(raw["risk_id"]))
        else:
            return []
        found = trace_rules.redmine_issue_evidence(payload, rules, known_codes, known_paths)
    else:
        return []
    return [(source, e) for e in found]


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
    return RequirementSummaryResponse(
        total=total,
        verified=verified,
        notVerified=total - verified,
        implementedFromSourceClosed=n["implemented_from_source_closed"],
        verifiedRate=verified / total if total else None,
        decided=n["decided"],
        byStatus=[
            StatusCount(status=s, count=n["by_status"].get(s, 0))
            for s in repository.REQUIREMENT_STATUSES
        ],
        sources=[_source_summary(s) for s in n["sources"]],
    )


def _source_summary(row: dict[str, Any]) -> SourceStateSummary:
    if row["connection_id"] is None:
        tool, label = "NONE", "원천 연결 없음(문서·수기)"
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
        rid = str(lk["to_id"])
        label, url = labels.get((lk["from_type"], str(lk["from_id"])), ("?", None))
        cells.setdefault(rid, {}).setdefault(lk["link_kind"], []).append(
            TraceCell(targetId=str(lk["from_id"]), label=label, externalUrl=url)
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
        ),
        traceComplete=row["trace_complete"],
        updatedAt=row["updated_at"].isoformat(),
        statusBasis=requirement_decision.status_basis(row),
        evidenceStatus=row["evidence_status"],
        decision=requirement_decision.decision_of(row),
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
    )
