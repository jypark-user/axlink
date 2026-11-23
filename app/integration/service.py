"""커넥터 등록·테스트·상태 전이. 파일럿 ToolConnectionService 의 동작을 옮겼다.

박PM 시나리오 S2-2 의 흐름 — 도구 선택 → 인증정보 → 대상 저장소 → 연결 테스트 → 저장.
연결은 용역사(CONTRACTOR)가 자기 사업에 붙인다. 접근 범위는 사업 단위로 막는다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import psycopg

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import crypto, errors
from app.common.paging import PageQuery, PageResponse
from app.integration import port, repository, sync
from app.integration.models import (
    TOOLS,
    ConnectionOwnerRequest,
    MappingRulesUpdateRequest,
    SyncJobResponse,
    SyncJobStats,
    ToolConnectionCreateRequest,
    ToolConnectionResponse,
    ToolConnectionTestResponse,
    ToolConnectionUpdateRequest,
)
from app.project import participants
from app.standard.mapping_rules import MappingRules


def _require_project(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()


@contextmanager
def _unique_target(cur: Any) -> Iterator[None]:
    """같은 사업·도구·서버·대상의 연결은 하나다(V57). 서버가 다르면 대상 식별자가 같아도 된다."""
    try:
        with cur.connection.transaction():
            yield
    except psycopg.errors.UniqueViolation as exc:
        raise errors.ApiError(
            409, "CONNECTION_DUPLICATE",
            "이 사업에 같은 서버의 같은 대상이 이미 연결돼 있습니다. 기존 연결을 고쳐 쓰세요.",
        ) from exc


# http 를 받는 같은 기계 주소. 문자열 앞부분이 아니라 실제 호스트로 비교한다
# ("http://localhost.attacker.invalid", "http://localhost@attacker.invalid" 를 막는다)
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _require_https(base_url: str) -> None:
    """평문 자격증명이 기계 밖 http 로 나가지 않게 막는다(SER.SEC.001).

    https 는 호스트를 가리지 않는다. 사내 Redmine·GitHub Enterprise 의 사설 주소도 된다.
    http 는 같은 기계 주소만 받는다(로컬 검증용 Redmine). 주소에 사용자 정보(user@)는
    받지 않는다. 토큰은 따로 받고, user@ 는 실제 호스트를 숨기는 데 쓰인다.
    """
    try:
        parts = urlsplit((base_url or "").strip())
        port = parts.port  # 숫자가 아니면 ValueError
    except ValueError:
        port = -1
    host = (parts.hostname or "").lower()
    if not host or port == -1:
        raise errors.validation_failed("baseUrl 이 올바른 주소가 아닙니다.")
    if "@" in parts.netloc:
        raise errors.validation_failed("baseUrl 에 사용자 정보(@)를 넣을 수 없습니다.")
    scheme = parts.scheme.lower()
    if scheme == "https":
        return
    if scheme == "http" and host in _LOOPBACK_HOSTS:
        return
    raise errors.validation_failed(
        "baseUrl 은 https 로 시작해야 합니다. http 는 같은 기계 주소(localhost·127.0.0.1)만 됩니다."
    )


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
    participants.require_connection_manager(cur, principal, conn)
    token = crypto.decrypt(conn["auth_encrypted"])
    probe = _probe(conn["tool"], conn["base_url"], conn["target_resource"], token)
    # 저장소에 닿았으면 검증됨으로 올린다. 일부 항목 권한이 빠져도 연결 자체는 유효하다.
    repository.mark_verified(cur, connection_id, datetime.now(UTC))
    return _to_test_response(probe)


def create(
    cur: Any, principal: AuthPrincipal, project_id: str, req: ToolConnectionCreateRequest
) -> ToolConnectionResponse:
    _require_project(cur, principal, project_id)
    if principal.role == "CONTRACTOR" and participants.active_participant(
        cur, project_id, principal.org_id
    ) is None:
        raise errors.ApiError(
            403, "NOT_PARTICIPANT", "이 사업의 참여 업체로 등록된 업체만 연결을 만들 수 있습니다."
        )
    _require_tool(req.tool)
    _require_https(req.baseUrl)
    token = req.credential.accessToken
    encrypted = crypto.encrypt(token)
    hint = crypto.hint(token)
    # 저장 전에 규칙 형식을 검증한다 — 오타 난 키가 조용히 저장되면 못 찾는다.
    rules = MappingRules.from_json(req.mappingRules) if req.mappingRules else None
    with _unique_target(cur):
        row = repository.insert(
            cur, project_id, principal.org_id, req.tool, req.name, req.baseUrl,
            req.targetResource, encrypted, hint,
            rules.to_json() if rules else None,
        )
    return _to_response(cur, principal, row)


def list_for_project(
    cur: Any, principal: AuthPrincipal, project_id: str
) -> list[ToolConnectionResponse]:
    _require_project(cur, principal, project_id)
    return [_to_response(cur, principal, r) for r in repository.find_by_project(cur, project_id)]


def change_status(
    cur: Any, principal: AuthPrincipal, connection_id: str, target: str
) -> ToolConnectionResponse:
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    participants.require_connection_manager(cur, principal, conn)
    current = conn["status"]
    if target == "ACTIVE" and current not in ("VERIFIED", "PAUSED"):
        raise errors.validation_failed(f"{current} → {target} 전이는 허용되지 않습니다.")
    if target == "PAUSED" and current != "ACTIVE":
        raise errors.validation_failed(f"{current} → {target} 전이는 허용되지 않습니다.")
    if target not in ("ACTIVE", "PAUSED"):
        raise errors.validation_failed(f"허용되지 않는 상태입니다: {target}")
    repository.update_status(cur, connection_id, target, datetime.now(UTC))
    return _to_response(cur, principal, repository.find_by_id(cur, connection_id))


def update_mapping(
    cur: Any, principal: AuthPrincipal, connection_id: str, req: MappingRulesUpdateRequest
) -> ToolConnectionResponse:
    """매핑 규칙 변경. 기존 수집분에는 다음 수집(재승격) 때 적용된다 — 코드 수정 없이."""
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    participants.require_connection_manager(cur, principal, conn)
    rules = MappingRules.from_json(req.mappingRules)
    repository.update_mapping_rules(cur, connection_id, rules.to_json(), datetime.now(UTC))
    return _to_response(cur, principal, repository.find_by_id(cur, connection_id))


def update(
    cur: Any, principal: AuthPrincipal, connection_id: str, req: ToolConnectionUpdateRequest
) -> ToolConnectionResponse:
    """이름은 그냥 바꾼다. 주소·대상·인증정보가 바뀌면 검증이 무효라 DRAFT 로 돌린다.

    다시 연결 테스트를 받아야 활성화된다. 검증된 채로 두면 엉뚱한 저장소를 읽는다.
    """
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    participants.require_connection_manager(cur, principal, conn)
    if req.name is not None and not req.name.strip():
        raise errors.validation_failed("이름은 비울 수 없습니다.")
    if req.baseUrl is not None:
        if not req.baseUrl.strip():
            raise errors.validation_failed("baseUrl 은 비울 수 없습니다.")
        _require_https(req.baseUrl)
    if req.targetResource is not None and not req.targetResource.strip():
        raise errors.validation_failed("targetResource 는 비울 수 없습니다.")

    encrypted = hint = None
    if req.credential is not None:
        encrypted = crypto.encrypt(req.credential.accessToken)
        hint = crypto.hint(req.credential.accessToken)

    changed_target = any(
        value is not None and value != conn[column]
        for value, column in ((req.baseUrl, "base_url"), (req.targetResource, "target_resource"))
    )
    with _unique_target(cur):
        repository.update_connection(
            cur, connection_id, datetime.now(UTC),
            name=req.name, base_url=req.baseUrl, target_resource=req.targetResource,
            auth_encrypted=encrypted, auth_hint=hint,
            reset_status=changed_target or req.credential is not None,
        )
    return _to_response(cur, principal, repository.find_by_id(cur, connection_id))


def delete(cur: Any, principal: AuthPrincipal, connection_id: str) -> None:
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    participants.require_connection_manager(cur, principal, conn)
    repository.delete(cur, connection_id)


def trigger_sync(
    cur: Any, principal: AuthPrincipal, connection_id: str, full: bool = False
) -> SyncJobResponse:
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    _require_project(cur, principal, str(conn["project_id"]))
    if conn["status"] not in ("VERIFIED", "ACTIVE", "PAUSED", "FAILED"):
        raise errors.validation_failed("먼저 연결 테스트로 검증한 뒤 수집할 수 있습니다.")
    job_id = sync.run_sync(cur, conn, full=full)
    job = repository.find_sync_job(cur, job_id)
    return _to_job_response(job, conn)


def retry_job(cur: Any, principal: AuthPrincipal, job_id: str) -> SyncJobResponse:
    """실패한 잡만 다시 돈다. 성공한 잡을 또 돌리는 건 그냥 새 수집이다."""
    job = repository.find_sync_job(cur, job_id)
    if job is None:
        raise errors.not_found("sync job", job_id)
    conn = repository.find_by_id(cur, str(job["tool_connection_id"]))
    if conn is None:
        raise errors.not_found("connection", str(job["tool_connection_id"]))
    _require_project(cur, principal, str(conn["project_id"]))
    if job["status"] != "FAILED":
        raise errors.validation_failed("실패한 수집만 다시 시도할 수 있습니다.")
    new_id = sync.run_sync(cur, conn, retry_of=job_id)
    return _to_job_response(repository.find_sync_job(cur, new_id), conn)


def list_jobs(
    cur: Any, principal: AuthPrincipal, project_id: str, page: PageQuery, **filters: Any
) -> PageResponse[SyncJobResponse]:
    """filters: connection_id, status, started_from, started_to (repository._job_filter)."""
    _require_project(cur, principal, project_id)
    total = repository.count_sync_jobs(cur, project_id, **filters)
    rows = repository.list_sync_jobs(cur, project_id, page.size, page.offset, **filters)
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


def _to_response(
    cur: Any, principal: AuthPrincipal, row: dict[str, Any]
) -> ToolConnectionResponse:
    """인증정보 힌트는 바꿀 수 있는 사람에게만 준다. 공유 조회에는 넣지 않는다(SER.SEC.001)."""
    cid = str(row["id"])
    state, owner_name = participants.owner_state(cur, row)
    manage = participants.can_manage_connection(cur, principal, row)
    return ToolConnectionResponse(
        id=cid,
        projectId=str(row["project_id"]),
        tool=row["tool"],
        name=row["name"],
        baseUrl=row["base_url"],
        targetResource=row["target_resource"],
        credentialMasked=row["auth_hint"] if manage else None,
        status=row["status"],
        lastSyncedAt=_iso(row["last_synced_at"]),
        lastSyncStatus=repository.last_sync_status(cur, cid),
        lastSyncError=row["last_error"],
        ingestedCount=repository.ingested_count(cur, cid),
        mappingRuleCount=repository.mapping_rule_count(row["mapping_rules_json"]),
        createdAt=_iso(row["created_at"]),
        ownerOrgId=str(row["contractor_org_id"]),
        ownerOrgName=owner_name,
        ownerState=state,
        canManage=manage,
    )


def change_owner(
    cur: Any, principal: AuthPrincipal, connection_id: str, req: ConnectionOwnerRequest
) -> ToolConnectionResponse:
    """소유 업체를 바꾼다. 발주기관·관리자만, 이 사업의 참여 용역 업체로만(GH-138).

    소유가 불명확한 연결을 정리하거나 참여를 끝낸 업체의 연결을 넘길 때 쓴다. 인증정보는
    그대로라 새 소유 업체가 토큰을 다시 등록하는 것을 권한다.
    """
    conn = repository.find_by_id(cur, connection_id)
    if conn is None:
        raise errors.not_found("connection", connection_id)
    project_id = str(conn["project_id"])
    participants.require_manager(cur, principal, project_id)
    part = participants.active_participant(cur, project_id, req.organizationId)
    if part is None or part["type"] != "CONTRACTOR":
        raise errors.validation_failed("이 사업의 참여 용역 업체로만 넘길 수 있습니다.")
    before = str(conn["contractor_org_id"])
    cur.execute(
        "update tool_connection set contractor_org_id = %s, updated_at = now() where id = %s",
        (req.organizationId, connection_id),
    )
    actor = auth_repo.find_user_by_id(cur, principal.user_id) or {}
    cur.execute(
        """
        insert into entity_history (entity_type, entity_id, project_id, field, from_value,
                                    to_value, actor)
        values ('TOOL_CONNECTION', %s, %s, 'owner_org', %s, %s, %s)
        """,
        (connection_id, project_id, before, req.organizationId,
         (actor.get("name") or actor.get("username") or "사용자")[:120]),
    )
    return _to_response(cur, principal, repository.find_by_id(cur, connection_id))
