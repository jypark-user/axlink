"""수집(BACKFILL) 오케스트레이션.

붙인 연결에서 이슈·PR·커밋을 가져와 원본을 raw_artifact 에 적재한다. PoC 규모라
요청 안에서 동기로 돈다(대형 저장소면 비동기로 승격). 한 항목종류의 권한이 빠지면
통째로 실패시키지 않고 그 종류만 건너뛰며 잡에 남긴다 — 부분 성공을 정직하게 기록한다.

여기서는 원본 적재까지다. 표준 모델 승격(이슈→지표·대시보드)은 다음 슬라이스다.
"""

from datetime import UTC, datetime
from typing import Any

from app.common import crypto, errors
from app.integration import github, repository

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


def run_backfill(cur: Any, connection: dict[str, Any]) -> str:
    """전체 수집을 실행하고 sync_job id 를 돌려준다."""
    now = datetime.now(UTC)
    cid = str(connection["id"])
    job_id = repository.insert_sync_job(cur, cid, "BACKFILL", _EPOCH, now)
    token = crypto.decrypt(connection["auth_encrypted"])
    base, target = connection["base_url"], connection["target_resource"]

    stats = {"fetched": 0, "upserted": 0, "unmapped": 0, "indexed": 0, "skippedUnchanged": 0}
    denied: list[str] = []

    try:
        for kind in ("issue", "pull_request", "commit"):
            try:
                for external_id, payload in github.fetch_items(
                    base, target, token, kind, _PER_PAGE, _MAX_PAGES
                ):
                    stats["fetched"] += 1
                    if repository.upsert_raw_artifact(cur, cid, external_id, kind, payload, job_id):
                        stats["upserted"] += 1
                    else:
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
            cur, job_id, "FAILED", stats, finished, finished,
            error=exc.message, error_code=_ERROR_CODE.get(exc.code, "TOOL_UNAVAILABLE"),
        )
        repository.mark_synced(cur, cid, finished, exc.message)
        return job_id

    # 아직 표준 모델로 승격하지 않으므로 가져온 전부가 미매핑이다(다음 슬라이스에서 매핑).
    stats["unmapped"] = stats["fetched"]
    note = None if not denied else f"권한이 없어 건너뛴 항목: {', '.join(denied)}"
    finished = datetime.now(UTC)
    repository.finish_sync_job(
        cur, job_id, "SUCCEEDED", stats, finished, finished, error=note, error_code=None
    )
    repository.mark_synced(cur, cid, finished, note)
    return job_id
