"""수집 오케스트레이션 — 첫 회는 전체(BACKFILL), 그 다음부터는 증분(POLL).

붙인 연결에서 항목을 가져와 원본을 raw_artifact 에 적재한다. PoC 규모라
요청 안에서 동기로 돈다(대형 저장소면 비동기로 승격). 한 항목종류의 권한이 빠지면
통째로 실패시키지 않고 그 종류만 건너뛰며 잡에 남긴다 — 부분 성공을 정직하게 기록한다.

증분의 커서는 마지막 성공 잡의 cursor_to 다(SWFR.CON.005). cursor_to 에는 잡의
종료가 아니라 **시작 시각**을 적는다 — 수집 도중의 갱신분을 다음 회차가 겹쳐 읽게
되지만, 내용해시 적재가 걸러 주므로 놓치는 것보다 겹치는 쪽이 재현 가능하다.

한 회차는 항목종류마다 _PER_PAGE × _MAX_PAGES 건까지만 읽는다. 상한에 걸린 종류는 다 읽은
것이 아니므로 어댑터가 이어 읽을 자리를 돌려주고, 잡의 stats_json.resume 에 남긴다. 다음
회차는 그 종류만 그 자리부터 읽는다(점검 DATA-01). 다른 종류의 커서는 그대로 넘어간다.

원본을 적재한 뒤 표준 모델로 승격하고 색인까지 한 흐름에서 끝낸다 — 수집이 끝났는데
화면에는 아무것도 없는 상태를 만들지 않기 위해서다.
"""

import base64
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from typing import Any

from app.ai.embedding import embedding_port
from app.common import crypto, errors
from app.config import settings
from app.integration import port, repository
from app.standard import design_refs, trace_service
from app.standard import service as standard
from app.standard.mapping_rules import MappingRules

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_PER_PAGE = 50
_MAX_PAGES = 20  # PoC 상한. 우리 저장소 규모엔 충분하고 폭주를 막는다.

# 내부 오류코드 → sync_job.error_code CHECK 허용값
_ERROR_CODE = {
    "TOOL_AUTH": "TOOL_AUTH_FAILED",
    "TOOL_NOT_FOUND": "TOOL_RESOURCE_NOT_FOUND",
    "TOOL_RATE_LIMITED": "TOOL_RATE_LIMITED",
    "TOOL_UNREACHABLE": "TOOL_UNAVAILABLE",
}


def _fail_if_core_denied(connector: Any, denied: list[str]) -> None:
    """권한이 빠진 항목이 수집의 본체면 부분 성공이 아니라 실패다.

    모든 항목이 막혔거나(키가 무효, 프로젝트 접근 없음) 커넥터가 필수로 둔 항목이 막히면
    "성공 · 0건" 처럼 보이지 않게 실패로 끝낸다. 앞서 받은 데이터는 지우지 않는다.
    """
    required = set(getattr(connector, "required_kinds", ()))
    blocked = sorted(required & set(denied))
    if denied and (blocked or set(denied) >= set(connector.item_kinds)):
        names = ", ".join(blocked or denied)
        raise errors.ApiError(
            403, "TOOL_AUTH",
            f"인증이 거부되었거나 읽기 권한이 없어 수집하지 못했습니다: {names}. "
            "연결 테스트로 토큰·권한을 확인해 주세요.",
        )


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _drain(
    items: Generator[tuple[str, dict], None, Any], take: Callable[[str, dict], None]
) -> port.PageResult | None:
    """어댑터가 낸 항목을 모두 받고, 다 읽었는지(None) 상한에 걸렸는지(PageResult) 돌려준다."""
    while True:
        try:
            external_id, payload = next(items)
        except StopIteration as stop:
            return stop.value
        take(external_id, payload)


def _passes(
    plan: dict[str, str] | None, since: datetime | None
) -> list[tuple[datetime | None, datetime | None]]:
    """이번 회차에 이 종류를 읽을 범위들. 이어 읽을 자리가 있으면 그것을 먼저 쓴다."""
    if not plan:
        return [(since, None)]
    start = datetime.fromisoformat(plan["since"])
    if "until" in plan:  # 최신부터 오는 목록이 못 읽은 구간. 그 구간 뒤에 새 범위
        return [(start, datetime.fromisoformat(plan["until"])), (since, None)]
    return [(start if since is None else min(start, since), None)]


def _merge(old: dict[str, str] | None, got: port.PageResult) -> dict[str, str] | None:
    """상한에 걸려 새로 생긴 이어 읽을 자리. 앞서 남은 구간과 겹치면 넓혀 합친다."""
    if got.resume_since is not None:
        new = {"since": _iso(got.resume_since)}
    elif got.gap is not None:
        new = {"since": _iso(got.gap[0]), "until": _iso(got.gap[1])}
    else:
        return old
    if old and "until" in old and "until" in new:
        return {"since": min(old["since"], new["since"]), "until": max(old["until"], new["until"])}
    return new


def run_sync(
    cur: Any, connection: dict[str, Any], retry_of: str | None = None, full: bool = False
) -> str:
    """수집을 실행하고 sync_job id 를 돌려준다. 첫 회는 전체, 이후는 증분이다.

    full 이면 커서를 무시하고 처음부터 다시 읽는다(화면의 "전체 수집"). 원본 키 규칙이
    바뀌었거나 증분으로는 다시 오지 않는 항목을 되살릴 때 쓴다.

    재시도도 새 잡이다. 실패한 잡은 그대로 두고 retry_of 로 잇는다. 커서는 마지막
    성공 잡 기준이라 실패한 회차의 범위를 자연히 다시 읽는다.
    """
    now = datetime.now(UTC)
    cid = str(connection["id"])
    since = None if full else repository.last_success_cursor(cur, cid)
    job_id = repository.insert_sync_job(
        cur, cid, "POLL" if since else "BACKFILL", since or _EPOCH, now, retry_of
    )
    token = crypto.decrypt(connection["auth_encrypted"])
    base, target = connection["base_url"], connection["target_resource"]

    # changed = 새로 생기거나 바뀐 원본 건수(fetched − skippedUnchanged). 화면의 「신규·갱신」.
    # upserted 는 표준 모델로 올린(재승격 포함) 건수라 「반영」으로만 쓴다(IM-007 AC-011-2, GH-213).
    stats = {
        "fetched": 0,
        "changed": 0,
        "upserted": 0,
        "unmapped": 0,
        "indexed": 0,
        "skippedUnchanged": 0,
    }
    denied: list[str] = []
    connector = port.get_connector(connection["tool"])
    # 전체 수집은 처음부터 읽으므로 앞 회차의 이어 읽을 자리를 쓰지 않는다
    resume_before = {} if full else repository.last_success_resume(cur, cid)
    resume: dict[str, dict[str, str]] = {}
    limited: list[str] = []

    def take(kind: str) -> Callable[[str, dict], None]:
        def put(external_id: str, payload: dict) -> None:
            stats["fetched"] += 1
            _carry_files(cur, cid, external_id, kind, payload)
            # 원본이 이전과 같으면 적재하지 않는다. upserted 는 원본이 아니라
            # 표준 모델 반영 건수로 쓴다(화면 라벨이 "반영"이다).
            if not repository.upsert_raw_artifact(cur, cid, external_id, kind, payload, job_id):
                stats["skippedUnchanged"] += 1
        return put

    try:
        for kind in connector.item_kinds:
            plan = resume_before.get(kind)
            try:
                for start, until in _passes(plan, since):
                    got = _drain(
                        connector.fetch_items(
                            base, target, token, kind, _PER_PAGE, _MAX_PAGES,
                            since=start, until=until,
                        ),
                        take(kind),
                    )
                    if got is not None and got.truncated:
                        if kind not in limited:
                            limited.append(kind)
                        merged = _merge(resume.get(kind), got)
                        if merged:
                            resume[kind] = merged
            except errors.ApiError as exc:
                # 이 항목종류만 권한이 빠진 경우 — 건너뛰고 다음으로. 나머지는 하드 실패.
                if exc.code == "TOOL_AUTH":
                    denied.append(kind)
                    if plan:  # 이번에 못 읽었으니 이어 읽을 자리를 다음 회차로 넘긴다
                        resume[kind] = plan
                else:
                    raise
        _fail_if_core_denied(connector, denied)
    except errors.ApiError as exc:
        finished = datetime.now(UTC)
        repository.finish_sync_job(
            cur, job_id, "FAILED", stats, now, finished,
            error=exc.message, error_code=_ERROR_CODE.get(exc.code, "TOOL_UNAVAILABLE"),
        )
        repository.mark_synced(cur, cid, finished, exc.message)
        from app.activity import service as activity

        activity.record(
            cur, project_id=str(connection["project_id"]), kind=activity.SYNC_FAILED,
            audience=activity.ALL, actor_label="동기화",
            summary=f"동기화 실패: {connection.get('name') or connection['tool']} · {exc.message}",
            target_type="SYNC_JOB", target_key=str(job_id), occurred_at=finished,
        )
        return job_id

    denied += _collect_files(cur, cid, connector, base, target, token, job_id, stats)
    rules = MappingRules.from_json(connection.get("mapping_rules_json"))
    _collect_details(cur, cid, connector, base, target, token, job_id, stats, rules)

    stats["changed"] = stats["fetched"] - stats["skippedUnchanged"]
    promoted = standard.promote_connection(cur, connection, embedding_port())
    stats["upserted"] = promoted.upserted
    stats["unmapped"] = promoted.unmapped
    stats["indexed"] = promoted.indexed
    # 승격이 끝나야 링크의 양 끝이 있다. 다른 연결의 원본까지 같이 보므로 사업 단위로 돈다.
    trace_service.build_project_links(cur, str(connection["project_id"]))

    notes = []
    if limited:
        notes.append(
            f"회차 상한({_PER_PAGE * _MAX_PAGES:,}건)에 걸려 다 읽지 못한 항목: "
            f"{', '.join(limited)}. 다음 회차에 이어 읽습니다"
        )
    if resume:
        stats["resume"] = resume
    if denied:
        notes.append(f"권한이 없어 건너뛴 항목: {', '.join(denied)}")
    if promoted.index_error:
        notes.append(f"색인을 건너뛰었습니다 — {promoted.index_error}")
    note = " / ".join(notes) or None
    finished = datetime.now(UTC)
    repository.finish_sync_job(
        cur, job_id, "SUCCEEDED", stats, now, finished, error=note, error_code=None
    )
    repository.mark_synced(cur, cid, finished, note)
    changed = stats["fetched"] - stats["skippedUnchanged"]
    if changed > 0:
        # 수집도 사업의 사건이다(IM-007 AC-053-4, GH-221). 바뀐 원본이 있을 때만 남긴다 —
        # 변경 없는 회차까지 적으면 기록이 수집 주기로 메워진다
        from app.activity import service as activity

        activity.record(
            cur,
            project_id=str(connection["project_id"]),
            kind=activity.SYNC_CHANGED,
            audience=activity.ALL,
            actor_label="동기화",
            summary=(
                f"수집 완료: {connection.get('name') or connection['tool']} · "
                f"바뀐 원본 {changed}건 · 반영 {stats['upserted']}건"
            ),
            target_type="SYNC_JOB",
            target_key=str(job_id),
            occurred_at=finished,
            detail={
                "fetched": stats["fetched"],
                "changed": changed,
                "upserted": stats["upserted"],
                "denied": denied,
            },
        )
    return job_id


def _collect_files(
    cur: Any,
    connection_id: str,
    connector: port.ToolConnector,
    base: str,
    target: str,
    token: str,
    job_id: str,
    stats: dict[str, int],
) -> list[str]:
    """설정에 적힌 저장소 파일을 함께 가져온다.

    WBS 는 이 경로로 들어온다. 없으면 조용히 넘어간다 — 아직 안 올렸을 수 있고,
    그건 수집 실패가 아니다. 파일이 없다는 사실 자체는 산출물 현황이 말해 준다.
    """
    skipped: list[str] = []
    for path in settings.collect_file_map:
        try:
            payload = connector.fetch_file(
                base, target, token, path, settings.collect_ref or None
            )
        except errors.ApiError as exc:
            # 토큰에 파일 읽기 권한이 없는 경우다. 이슈·커밋은 되는데 파일만 막힐 수 있다.
            if exc.code not in ("TOOL_AUTH", "TOOL_NOT_FOUND"):
                raise
            skipped.append(path)
            continue
        if payload is None:
            continue
        stats["fetched"] += 1
        if not repository.upsert_raw_artifact(
            cur, connection_id, f"file:{path}", "file", payload, job_id
        ):
            stats["skippedUnchanged"] += 1
    return skipped


# ─── 변경 파일과 저장소 설계 문서 (ARC-024 2-6) ──────────────────────────────


def _carry_files(cur: Any, cid: str, external_id: str, kind: str, payload: dict) -> None:
    """증분 수집이 커밋·PR 원본을 다시 받으면 목록 응답에는 변경 파일이 없다. 이미 받아 둔 것을
    이어 붙인다. 커밋은 SHA 가 같으면 내용이 같고, PR 은 head SHA 가 같을 때만 잇는다."""
    if kind not in ("commit", "pull_request") or "files" in payload:
        return
    old = repository.raw_payload(cur, cid, external_id)
    if not old or not isinstance(old.get("files"), list):
        return
    if kind == "pull_request" and (old.get("head") or {}).get("sha") != (
        payload.get("head") or {}
    ).get("sha"):
        return
    payload["files"] = old["files"]


def _collect_details(
    cur: Any, cid: str, connector: Any, base: str, target: str, token: str, job_id: str,
    stats: dict[str, int], rules: MappingRules,
) -> None:
    """설계 문서와 변경 파일을 필요한 만큼만 받는다. 실패는 삭제·끊김이 아니다.

    차례로 하나씩 부른다. 남은 호출 한도가 낮거나 레이트리밋이면 멈추고 다음 회차로 넘긴다.
    호출 수는 잡 통계에 남긴다(요청·그대로·실패·삭제).
    """
    for key in ("docCalls", "docUnchanged", "docFailed", "docDeleted",
                "fileCalls", "fileCached", "fileFailed", "rateLimitStop"):
        stats.setdefault(key, 0)
    try:
        if rules.design_globs and hasattr(connector, "fetch_file"):
            _collect_design_docs(cur, cid, connector, base, target, token, job_id, stats,
                                 rules.design_globs)
        if settings.collect_change_files and hasattr(connector, "fetch_change_files"):
            _collect_change_files(cur, cid, connector, base, target, token, job_id, stats)
    except errors.ApiError as exc:
        if exc.code != "TOOL_RATE_LIMITED":
            raise
        stats["rateLimitStop"] = 1  # 받은 것까지만 쓴다. 남은 것은 다음 회차


def _collect_design_docs(
    cur: Any, cid: str, connector: Any, base: str, target: str, token: str, job_id: str,
    stats: dict[str, int], globs: list[str],
) -> None:
    tree = repository.raw_payload(cur, cid, "tree:HEAD")
    if not tree or not isinstance(tree.get("blobs"), dict):
        return  # 트리를 아직 못 받았다. 문서를 지운 것으로 보지 않는다
    commit = tree.get("commit")
    blobs = {p: s for p, s in tree["blobs"].items() if design_refs.match_any(p, globs)}
    existing = repository.raw_payloads_by_kind(cur, cid, "design_doc")
    html_base = str(tree.get("html_url") or "")

    fetched = 0
    for path, blob in sorted(blobs.items()):
        old = existing.get(f"doc:{path}")
        if old and old.get("blob_sha") == blob and not old.get("deleted"):
            stats["docUnchanged"] += 1
            continue
        if fetched >= settings.design_doc_fetch_limit:
            break
        fetched += 1
        stats["docCalls"] += 1
        try:
            got = connector.fetch_file(base, target, token, path, commit or None)
        except errors.ApiError as exc:
            if exc.code == "TOOL_RATE_LIMITED":
                raise
            stats["docFailed"] += 1  # 이전 원본과 링크를 그대로 둔다
            continue
        if got is None:
            stats["docFailed"] += 1  # 트리에는 있는데 못 읽었다. 삭제로 보지 않는다
            continue
        try:
            text = base64.b64decode(got.get("content") or "").decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            stats["docFailed"] += 1
            continue
        payload = {
            # 비교 기준은 트리의 blob SHA 다(같은 커밋이면 contents 의 sha 와 같다)
            "repo": target, "path": path, "commit_sha": commit, "blob_sha": blob,
            "html_url": f"{html_base}{path}" if html_base else got.get("htmlUrl"),
            "text": text, "deleted": False,
        }
        repository.upsert_raw_artifact(cur, cid, f"doc:{path}", "design_doc", payload, job_id)

    # 트리에서 빠진 문서만 삭제로 본다. 트리가 잘렸으면 판단하지 않는다(이동은 삭제 + 추가)
    if tree.get("truncated"):
        return
    for external_id, old in existing.items():
        path = external_id.removeprefix("doc:")
        if path in blobs or old.get("deleted"):
            continue
        if path in tree["blobs"]:
            continue  # 저장소에는 있는데 패턴에서 빠졌다. 지운 게 아니다
        stats["docDeleted"] += 1
        repository.upsert_raw_artifact(
            cur, cid, external_id, "design_doc",
            {**old, "deleted": True, "deleted_at_commit": commit}, job_id,
        )


def _collect_change_files(
    cur: Any, cid: str, connector: Any, base: str, target: str, token: str, job_id: str,
    stats: dict[str, int],
) -> None:
    rows = repository.raw_changes_without_files(cur, cid)
    stats["fileCached"] = repository.count_changes_with_files(cur, cid)
    for row in rows[: settings.change_files_fetch_limit]:
        payload = row["payload_jsonb"]
        kind = row["object_kind"]
        ident = payload.get("sha") if kind == "commit" else str(payload.get("number") or "")
        if not ident:
            continue
        stats["fileCalls"] += 1
        files, left = connector.fetch_change_files(base, target, token, kind, ident)
        if files is None:
            stats["fileFailed"] += 1  # 모르는 채로 둔다. 다음 회차에 다시 받는다
        else:
            repository.upsert_raw_artifact(
                cur, cid, row["external_id"], kind, {**payload, "files": files}, job_id
            )
        if left is not None and left < settings.github_min_remaining:
            stats["rateLimitStop"] = 1
            return
