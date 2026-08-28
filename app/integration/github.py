"""GitHub 커넥터. 파일럿 GithubConnector 의 동작을 옮겼다.

읽기 전용이다 — 저장소에 아무것도 쓰지 않는다(QUR.CON.001). verify 는 대상 저장소가
토큰으로 닿는지 확인하고, 무엇을 읽을 수 있는지(이슈·PR·커밋)를 돌려준다.
박PM 시나리오 S2-2 의 "연결 테스트" 가 이 함수를 부른다.
"""

import httpx

from app.common import errors
from app.config import settings

_API_VERSION = "2022-11-28"


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


def verify(base_url: str, target_resource: str, token: str) -> tuple[str, list[str]]:
    """대상 저장소에 닿는지 확인하고 (표시이름, 읽을 수 있는 항목종류) 를 돌려준다.

    실패는 도구별 예외로 명확히 구분한다 — 토큰 오류(401)·저장소 없음(404)·레이트리밋(403).
    """
    url = _repo_url(base_url, target_resource)
    headers = _headers(token)
    try:
        with httpx.Client(timeout=settings.connector_timeout) as client:
            res = client.get(url, headers=headers)
    except httpx.RequestError as exc:
        raise errors.ApiError(502, "TOOL_UNREACHABLE", f"GitHub 에 닿지 못했습니다: {exc}") from exc

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

    repo = res.json()
    name = repo.get("full_name") or target_resource
    detected = ["issue", "pull_request", "commit"]
    return name, detected
