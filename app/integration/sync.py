"""수집 오케스트레이션 — 첫 회는 전체(BACKFILL), 그 다음부터는 증분(POLL).

붙인 연결에서 항목을 가져와 원본을 raw_artifact 에 적재한다. PoC 규모라
요청 안에서 동기로 돈다(대형 저장소면 비동기로 승격). 한 항목종류의 권한이 빠지면
통째로 실패시키지 않고 그 종류만 건너뛰며 잡에 남긴다 — 부분 성공을 정직하게 기록한다.

증분의 커서는 마지막 성공 잡의 cursor_to 다(SWFR.CON.005). cursor_to 에는 잡의
종료가 아니라 **시작 시각**을 적는다 — 수집 도중의 갱신분을 다음 회차가 겹쳐 읽게
되지만, 내용해시 적재가 걸러 주므로 놓치는 것보다 겹치는 쪽이 재현 가능하다.

원본을 적재한 뒤 표준 모델로 승격하고 색인까지 한 흐름에서 끝낸다 — 수집이 끝났는데
화면에는 아무것도 없는 상태를 만들지 않기 위해서다.
"""

from datetime import UTC, datetime
from typing import Any

from app.ai.embedding import embedding_port
from app.common import crypto, errors
from app.config import settings
from app.integration import port, repository
from app.standard import service as standard

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


def run_sync(cur: Any, connection: dict[str, Any], retry_of: str | None = None) -> str:
    """수집을 실행하고 sync_job id 를 돌려준다. 첫 회는 전체, 이후는 증분이다.

    재시도도 새 잡이다. 실패한 잡은 그대로 두고 retry_of 로 잇는다. 커서는 마지막
    성공 잡 기준이라 실패한 회차의 범위를 자연히 다시 읽는다.
    """
    now = datetime.now(UTC)
    cid = str(connection["id"])
    since = repository.last_success_cursor(cur, cid)
    job_id = repository.insert_sync_job(
        cur, cid, "POLL" if since else "BACKFILL", since or _EPOCH, now, retry_of
    )
    token = crypto.decrypt(connection["auth_encrypted"])
    base, target = connection["base_url"], connection["target_resource"]

    stats = {"fetched": 0, "upserted": 0, "unmapped": 0, "indexed": 0, "skippedUnchanged": 0}
    denied: list[str] = []
    connector = port.get_connector(connection["tool"])

    try:
        for kind in connector.item_kinds:
            try:
                for external_id, payload in connector.fetch_items(
                    base, target, token, kind, _PER_PAGE, _MAX_PAGES, since=since
                ):
                    stats["fetched"] += 1
                    # 원본이 이전과 같으면 적재하지 않는다. upserted 는 원본이 아니라
                    # 표준 모델 반영 건수로 쓴다(화면 라벨이 "반영"이다).
                    if not repository.upsert_raw_artifact(
                        cur, cid, external_id, kind, payload, job_id
                    ):
                        stats["skippedUnchanged"] += 1
            except errors.ApiError as exc:
                # 이 항목종류만 권한이 빠진 경우 — 건너뛰고 다음으로. 나머지는 하드 실패.
                if exc.code == "TOOL_AUTH":
                    denied.append(kind)
                else:
                    raise
    except errors.ApiError as exc:
        finished = datetime.now(UTC)
        repository.finish_sync_job(
            cur, job_id, "FAILED", stats, now, finished,
            error=exc.message, error_code=_ERROR_CODE.get(exc.code, "TOOL_UNAVAILABLE"),
        )
        repository.mark_synced(cur, cid, finished, exc.message)
        return job_id

    denied += _collect_files(cur, cid, connector, base, target, token, job_id, stats)

    promoted = standard.promote_connection(cur, connection, embedding_port())
    stats["upserted"] = promoted.upserted
    stats["unmapped"] = promoted.unmapped
    stats["indexed"] = promoted.indexed

    notes = []
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
