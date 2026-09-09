"""커넥터 등록·테스트·상태 전이. 파일럿 ToolConnectionService 의 동작을 옮겼다.

박PM 시나리오 S2-2 의 흐름 — 도구 선택 → 인증정보 → 대상 저장소 → 연결 테스트 → 저장.
연결은 용역사(CONTRACTOR)가 자기 사업에 붙인다. 접근 범위는 사업 단위로 막는다.
"""

from datetime import UTC, datetime
from typing import Any

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import crypto, errors
from app.common.paging import PageQuery, PageResponse
from app.integration import port, repository, sync
from app.integration.models import (
    TOOLS,
    SyncJobResponse,
    SyncJobStats,
    ToolConnectionCreateRequest,
    ToolConnectionResponse,
    ToolConnectionTestResponse,
)


def _require_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


def _require_https(base_url: str) -> None:
    # api.github.com·온프레미스 GitHub 모두 https 다. 평문 토큰이 http 로 나가지 않게 막는다.
    if not base_url.startswith("https://"):
        raise errors.validation_failed("baseUrl 은 https 로 시작해야 합니다.")


def _require_tool(tool: str) -> None:
    if tool not in TOOLS:
        raise errors.validation_failed(f"지원하지 않는 도구입니다: {tool}")


def _probe(tool: str, base_url: str, target: str, token: str) -> port.ProbeResult:
    _require_tool(tool)
    # 등록 안 된 도구는 여기서 501 로 알린다 — 조용히 실패하지 않는다.
    return port.get_connector(tool).verify(base_url, target, token)


def _to_test_response(probe: port.ProbeResult) -> ToolConnectionTestResponse:
    return ToolConnectionTestResponse(
        reachable=True,
        resourceName=probe.name,
        detectedItemTypes=probe.readable,
        deniedItemTypes=probe.denied,
        checkedAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def test_unsaved(
    cur: Any, principal: AuthPrincipal, tool: str, base_url: str, target: str, token: str
) -> ToolConnectionTestResponse:
    _require_https(base_url)
    return _to_test_response(_probe(tool, base_url, target, token))


def test_saved(
    cur: Any, principal: AuthPrincipal, connection_id: str
) -> ToolConnectionTestResponse:
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    _require_project(cur, principal, str(conn["project_id"]))
    token = crypto.decrypt(conn["auth_encrypted"])
    probe = _probe(conn["tool"], conn["base_url"], conn["target_resource"], token)
    # 저장소에 닿았으면 검증됨으로 올린다. 일부 항목 권한이 빠져도 연결 자체는 유효하다.
    repository.mark_verified(cur, connection_id, datetime.now(UTC))
    return _to_test_response(probe)


def create(
    cur: Any, principal: AuthPrincipal, project_id: str, req: ToolConnectionCreateRequest
) -> ToolConnectionResponse:
    _require_project(cur, principal, project_id)
    _require_tool(req.tool)
    _require_https(req.baseUrl)
    token = req.credential.accessToken
    encrypted = crypto.encrypt(token)
    hint = crypto.hint(token)
    row = repository.insert(
        cur, project_id, principal.org_id, req.tool, req.name, req.baseUrl,
        req.targetResource, encrypted, hint,
    )
    return _to_response(cur, row)


def list_for_project(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> list[ToolConnectionResponse]:
    _require_project(cur, principal, project_id)
    return [_to_response(cur, r) for r in repository.find_by_project(cur, project_id)]


def change_status(
    cur: Any, principal: AuthPrincipal, connection_id: str, target: str
) -> ToolConnectionResponse:
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    _require_project(cur, principal, str(conn["project_id"]))
    current = conn["status"]
    if target == "ACTIVE" and current not in ("VERIFIED", "PAUSED"):
        raise errors.validation_failed(f"{current} → {target} 전이는 허용되지 않습니다.")
    if target == "PAUSED" and current != "ACTIVE":
        raise errors.validation_failed(f"{current} → {target} 전이는 허용되지 않습니다.")
    if target not in ("ACTIVE", "PAUSED"):
        raise errors.validation_failed(f"허용되지 않는 상태입니다: {target}")
    repository.update_status(cur, connection_id, target, datetime.now(UTC))
    return _to_response(cur, repository.find_by_id(cur, connection_id))


def delete(cur: Any, principal: AuthPrincipal, connection_id: str) -> None:
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    _require_project(cur, principal, str(conn["project_id"]))
    repository.delete(cur, connection_id)


def trigger_sync(cur: Any, principal: AuthPrincipal, connection_id: str) -> SyncJobResponse:
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    _require_project(cur, principal, str(conn["project_id"]))
    if conn["status"] not in ("VERIFIED", "ACTIVE", "PAUSED", "FAILED"):
        raise errors.validation_failed("먼저 연결 테스트로 검증한 뒤 수집할 수 있습니다.")
    job_id = sync.run_backfill(cur, conn)
    job = repository.find_sync_job(cur, job_id)
    return _to_job_response(job, conn)


def list_jobs(
    cur: Any, principal: AuthPrincipal, project_id: str, page: PageQuery
) -> PageResponse[SyncJobResponse]:
    _require_project(cur, principal, project_id)
    total = repository.count_sync_jobs(cur, project_id)
    rows = repository.list_sync_jobs(cur, project_id, page.size, page.offset)
    content = [_to_job_response(r, r) for r in rows]
    return PageResponse.of(content, page, total)


def _to_job_response(job: dict[str, Any], conn: dict[str, Any]) -> SyncJobResponse:
    stats = job.get("stats_json") or {}
    return SyncJobResponse(
        id=str(job["id"]),
        connectionId=str(job["tool_connection_id"]),
        connectionName=conn.get("connection_name") or conn.get("name") or "",
        projectId=str(conn["project_id"]),
        tool=conn["tool"],
        kind=job["kind"],
        status=job["status"],
        startedAt=_iso(job.get("started_at")),
        finishedAt=_iso(job.get("finished_at")),
        stats=SyncJobStats(**stats),
        error=job.get("error"),
        retryable=job["status"] == "FAILED",
    )


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _to_response(cur: Any, row: dict[str, Any]) -> ToolConnectionResponse:
    cid = str(row["id"])
    return ToolConnectionResponse(
        id=cid,
        projectId=str(row["project_id"]),
        tool=row["tool"],
        name=row["name"],
        baseUrl=row["base_url"],
        targetResource=row["target_resource"],
        credentialMasked=row["auth_hint"],
        status=row["status"],
        lastSyncedAt=_iso(row["last_synced_at"]),
        lastSyncStatus=repository.last_sync_status(cur, cid),
        lastSyncError=row["last_error"],
        ingestedCount=repository.ingested_count(cur, cid),
        mappingRuleCount=repository.mapping_rule_count(row["mapping_rules_json"]),
        createdAt=_iso(row["created_at"]),
    )
