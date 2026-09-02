"""GitHub 커넥터. 읽기 전용이다 — 저장소에 아무것도 쓰지 않는다(QUR.CON.001).

verify: 저장소에 닿는지 + 각 항목(커밋·이슈·PR)을 실제로 읽을 수 있는지 항목별로 확인한다.
        토큰에 권한이 빠지면 붙이는 시점에 드러난다(수집 때 조용히 실패하지 않게).
fetch:  BACKFILL 이 항목종류별로 페이지를 돌며 원본을 가져온다.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from app.common import errors
from app.config import settings

_API_VERSION = "2022-11-28"

# 항목종류 → 저장소 하위 경로. 프로브·수집이 같은 정의를 쓴다.
ITEM_PATHS = {
    "issue": "/issues",
    "pull_request": "/pulls",
    "commit": "/commits",
}


@dataclass
class ProbeResult:
    name: str
    readable: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


def _headers(token: str) -> dict[str, str]:
    if not token or not token.strip():
        raise errors.ApiError(401, "TOOL_AUTH", "개인 토큰이 없습니다.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }


def _base(base_url: str) -> str:
    return (base_url or "https://api.github.com").rstrip("/")


def _repo_url(base_url: str, target: str) -> str:
    return f"{_base(base_url)}/repos/{target.strip('/')}"


def _get(client: httpx.Client, url: str, headers: dict[str, str], params: dict | None = None):
    try:
        return client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:
        raise errors.ApiError(502, "TOOL_UNREACHABLE", f"GitHub 에 닿지 못했습니다: {exc}") from exc


def _raise_repo_error(res: httpx.Response) -> None:
    """저장소 자체에 닿지 못하는 건 하드 실패다 — 연결이 성립하지 않는다."""
    if res.status_code == 401:
        raise errors.ApiError(401, "TOOL_AUTH", "토큰이 유효하지 않습니다.")
    if res.status_code == 404:
        raise errors.ApiError(
            404, "TOOL_NOT_FOUND", "저장소를 찾을 수 없거나 토큰에 접근 권한이 없습니다."
        )
    if res.status_code == 403 and res.headers.get("X-RateLimit-Remaining") == "0":
        raise errors.ApiError(429, "TOOL_RATE_LIMITED", "GitHub 레이트리밋에 걸렸습니다.")
    if res.status_code >= 400:
        raise errors.ApiError(502, "TOOL_UNREACHABLE", f"GitHub 오류 {res.status_code}")


def verify(base_url: str, target_resource: str, token: str) -> ProbeResult:
    """저장소 도달을 확인하고, 항목종류별로 실제 읽기 권한을 찔러본다.

    저장소를 못 보면 하드 실패. 저장소는 보이지만 특정 항목이 403 이면 denied 에 담아
    "읽을 수 있는 것"과 "권한이 빠진 것"을 함께 돌려준다.
    """
    headers = _headers(token)
    repo_url = _repo_url(base_url, target_resource)
    with httpx.Client(timeout=settings.connector_timeout) as client:
        res = _get(client, repo_url, headers)
        _raise_repo_error(res)
        name = res.json().get("full_name") or target_resource

        result = ProbeResult(name=name)
        for kind, path in ITEM_PATHS.items():
            probe = _get(client, repo_url + path, headers, params={"per_page": 1})
            # 200 = 읽힘. 빈 저장소의 커밋은 409(비어있음)지만 권한 문제는 아니라 읽힘으로 본다.
            if probe.status_code < 300 or probe.status_code == 409:
                result.readable.append(kind)
            elif probe.status_code == 403 and probe.headers.get("X-RateLimit-Remaining") == "0":
                raise errors.ApiError(429, "TOOL_RATE_LIMITED", "GitHub 레이트리밋에 걸렸습니다.")
            elif probe.status_code in (403, 404):
                result.denied.append(kind)
            else:
                # 예상 못 한 응답은 보수적으로 denied 로 둔다 — 있다고 잘못 알리지 않는다.
                result.denied.append(kind)
    return result


def fetch_items(
    base_url: str, target_resource: str, token: str, kind: str, per_page: int, max_pages: int
) -> Iterator[tuple[str, dict]]:
    """항목종류 하나를 페이지 단위로 가져온다. (external_id, payload) 를 순서대로 낸다.

    denied 는 예외로 올린다 — 호출부가 부분 실패로 기록하고 다음 종류로 넘어간다.
    /issues 는 PR 도 섞여 오므로 pull_request 항목은 제외한다(PR 은 /pulls 로 따로 가져온다).
    """
    headers = _headers(token)
    base = _repo_url(base_url, target_resource) + ITEM_PATHS[kind]
    params = {"per_page": per_page}
    if kind in ("issue", "pull_request"):
        params.update(state="all", sort="updated", direction="asc")

    with httpx.Client(timeout=settings.connector_timeout) as client:
        for page in range(1, max_pages + 1):
            res = _get(client, base, headers, params={**params, "page": page})
            if res.status_code == 403:
                if res.headers.get("X-RateLimit-Remaining") == "0":
                    raise errors.ApiError(429, "TOOL_RATE_LIMITED", "레이트리밋")
                raise errors.ApiError(403, "TOOL_AUTH", f"{kind} 읽기 권한이 없습니다.")
            if res.status_code == 409:  # 빈 저장소
                return
            if res.status_code >= 400:
                raise errors.ApiError(502, "TOOL_UNREACHABLE", f"GitHub 오류 {res.status_code}")
            batch = res.json()
            if not isinstance(batch, list) or not batch:
                return
            for item in batch:
                if kind == "issue" and item.get("pull_request") is not None:
                    continue  # PR 은 /pulls 에서 가져온다
                yield _external_id(kind, item), item
            if len(batch) < per_page:
                return


def _external_id(kind: str, item: dict) -> str:
    if kind == "commit":
        return f"commit:{item.get('sha')}"
    return f"{kind}:{item.get('number')}"
