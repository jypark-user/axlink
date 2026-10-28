"""GitHub 어댑터. 읽기 전용이다 — 저장소에 아무것도 쓰지 않는다(QUR.CON.001).

구현은 모듈 함수고 GitHubConnector 는 포트(ToolConnector)에 그 함수들을 입힌 껍데기다.
시험이 모듈 함수를 갈아끼우는 방식과 클래스 등록을 같이 살리기 위해서다.

verify: 저장소에 닿는지 + 각 항목(커밋·이슈·PR)을 실제로 읽을 수 있는지 항목별로 확인한다.
        토큰에 권한이 빠지면 붙이는 시점에 드러난다(수집 때 조용히 실패하지 않게).
fetch:  BACKFILL 이 항목종류별로 페이지를 돌며 원본을 가져온다.
"""

import base64
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.common import errors
from app.config import settings
from app.integration.port import ProbeResult

_API_VERSION = "2022-11-28"

# 항목종류 → 저장소 하위 경로. 프로브·수집이 같은 정의를 쓴다.
ITEM_PATHS = {
    "issue": "/issues",
    "pull_request": "/pulls",
    "commit": "/commits",
    "milestone": "/milestones",
    "tree": "/git/trees/HEAD",  # 파일 목록. WBS 산출물 경로가 저장소에 있는지 본다(ARC-016)
}


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


def _iso_z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_items(
    base_url: str, target_resource: str, token: str, kind: str, per_page: int, max_pages: int,
    since: datetime | None = None,
) -> Iterator[tuple[str, dict]]:
    """항목종류 하나를 페이지 단위로 가져온다. (external_id, payload) 를 순서대로 낸다.

    denied 는 예외로 올린다 — 호출부가 부분 실패로 기록하고 다음 종류로 넘어간다.
    /issues 는 PR 도 섞여 오므로 pull_request 항목은 제외한다(PR 은 /pulls 로 따로 가져온다).

    증분(since)은 종류마다 수단이 다르다 — 이슈·커밋은 API 의 since 필터,
    PR 목록에는 그런 필터가 없어 갱신 내림차순으로 받다가 경계에서 끊는다.
    마일스톤은 갱신 필터도 정렬도 없고 저장소당 몇 개뿐이라 매번 전부 받는다. 원본이
    같으면 적재 단계가 걸러 낸다.
    """
    headers = _headers(token)
    if kind == "tree":
        yield from _fetch_tree(base_url, target_resource, headers)
        return
    base = _repo_url(base_url, target_resource) + ITEM_PATHS[kind]
    params = {"per_page": per_page}
    stop_before: str | None = None
    if kind in ("issue", "pull_request"):
        params.update(state="all", sort="updated", direction="asc")
    elif kind == "milestone":
        params.update(state="all")  # 닫힌 마일스톤이 달성 기록이다(SWFR.PIP.007)
    if since is not None and kind != "milestone":
        if kind in ("issue", "commit"):
            params["since"] = _iso_z(since)
        else:  # pull_request
            params["direction"] = "desc"
            stop_before = _iso_z(since)

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
                if stop_before and (item.get("updated_at") or "") < stop_before:
                    return  # 경계 이전 갱신분 — 이 뒤로는 전부 이미 가진 것이다
                yield _external_id(kind, item), item
            if len(batch) < per_page:
                return


def _html_base(base_url: str) -> str:
    """API 주소에서 웹 주소를 만든다. api.github.com 은 github.com, 사내 서버는 /api/v3 를 뗀다."""
    base = base_url.rstrip("/")
    if "api.github.com" in base:
        return "https://github.com"
    return base.removesuffix("/api/v3")


def _fetch_tree(
    base_url: str, target_resource: str, headers: dict[str, str]
) -> Iterator[tuple[str, dict]]:
    """저장소 파일 목록 한 장. 한 번에 다 받고(recursive) 경로와 blob SHA 를 남긴다.

    갱신 필터가 없으니 매번 받는다. 내용이 같으면 적재 단계가 거른다. 트리가 잘리면
    (아주 큰 저장소) truncated 를 그대로 남겨 판정이 "없다" 고 단정하지 않게 한다.

    HEAD 커밋 SHA 를 먼저 받아 그 커밋의 트리를 읽는다. 설계 문서 근거가 "어느 커밋의 몇째 줄" 을
    가리키려면 트리 SHA 가 아니라 커밋 SHA 가 필요하다(ARC-024). 못 받으면 HEAD 로 읽는다.
    """
    repo = _repo_url(base_url, target_resource)
    with httpx.Client(timeout=settings.connector_timeout) as client:
        commit_sha = _head_commit(client, repo, headers)
        url = f"{repo}/git/trees/{commit_sha or 'HEAD'}"
        res = _get(client, url, headers, params={"recursive": "1"})
    if res.status_code == 403:
        if res.headers.get("X-RateLimit-Remaining") == "0":
            raise errors.ApiError(429, "TOOL_RATE_LIMITED", "레이트리밋")
        raise errors.ApiError(403, "TOOL_AUTH", "tree 읽기 권한이 없습니다.")
    if res.status_code in (404, 409):  # 빈 저장소
        return
    if res.status_code >= 400:
        raise errors.ApiError(502, "TOOL_UNREACHABLE", f"GitHub 오류 {res.status_code}")
    body = res.json()
    sha = str(body.get("sha") or "")
    blobs = {
        e["path"]: str(e.get("sha") or "")
        for e in body.get("tree") or [] if e.get("type") == "blob" and e.get("path")
    }
    yield "tree:HEAD", {
        "sha": sha,
        "commit": commit_sha,
        "truncated": bool(body.get("truncated")),
        "paths": list(blobs),
        "blobs": blobs,
        "html_url": f"{_html_base(base_url)}/{target_resource}/blob/{commit_sha or sha}/",
    }


def _head_commit(client: httpx.Client, repo: str, headers: dict[str, str]) -> str | None:
    """기본 브랜치 HEAD 의 커밋 SHA. 실패하면 None(트리는 HEAD 로 그대로 읽는다)."""
    res = _get(client, f"{repo}/commits/HEAD", {**headers, "Accept": "application/vnd.github.sha"})
    if res.status_code >= 400:
        return None
    text = res.text.strip()
    return text if len(text) == 40 else None


def remaining(res: httpx.Response) -> int | None:
    value = res.headers.get("X-RateLimit-Remaining")
    return int(value) if value and value.isdigit() else None


def fetch_change_files(
    base_url: str, target_resource: str, token: str, kind: str, ident: str
) -> tuple[list[str] | None, int | None]:
    """커밋·PR 하나의 변경 파일 이름(ARC-024 2-3). (파일 목록, 남은 호출 수).

    못 받으면 (None, 남은 수)다. 실패를 "바뀐 파일 없음" 으로 읽지 않게 None 과 [] 를 나눈다.
    PR 은 100개씩 3쪽(300개)까지 본다. 그보다 많으면 None 으로 둔다(일부만 보고 판정하지 않는다).
    """
    headers = _headers(token)
    repo = _repo_url(base_url, target_resource)
    with httpx.Client(timeout=settings.connector_timeout) as client:
        if kind == "commit":
            res = _get(client, f"{repo}/commits/{ident}", headers)
            left = remaining(res)
            _raise_limit(res)
            if res.status_code >= 400:
                return None, left
            body = res.json()
            files = body.get("files")
            if not isinstance(files, list) or len(files) >= 300:
                return None, left  # 300 개에서 잘린다. 일부만으로 판정하지 않는다
            return [str(f.get("filename")) for f in files if f.get("filename")], left
        names: list[str] = []
        left = None
        for page in (1, 2, 3):
            res = _get(client, f"{repo}/pulls/{ident}/files", headers,
                       params={"per_page": 100, "page": page})
            left = remaining(res)
            _raise_limit(res)
            if res.status_code >= 400:
                return None, left
            batch = res.json()
            if not isinstance(batch, list):
                return None, left
            names += [str(f.get("filename")) for f in batch if f.get("filename")]
            if len(batch) < 100:
                return names, left
        return None, left


def _raise_limit(res: httpx.Response) -> None:
    if res.status_code == 429 or (res.status_code == 403 and remaining(res) == 0):
        raise errors.ApiError(429, "TOOL_RATE_LIMITED", "GitHub 레이트리밋에 걸렸습니다.")


def fetch_file(
    base_url: str, target_resource: str, token: str, path: str, ref: str | None = None
) -> dict | None:
    """저장소의 파일 하나를 가져온다. 없으면 None.

    WBS 는 도구가 아니라 저장소에 커밋된 파일로 관리한다(작업 규약 §2).
    GitHub 만 쓰는 업체도 파일만 올려 두면 진척 산정이 성립하려면 이 경로가 필요하다.

    돌려주는 dict 는 raw_artifact.payload_jsonb 에 그대로 들어간다 — 바이트는 뺀다.
    """
    headers = _headers(token)
    url = f"{_repo_url(base_url, target_resource)}/contents/{path.lstrip('/')}"
    # ref 를 안 주면 저장소 기본 브랜치를 본다. 업체가 develop 을 쓰면 여기로 지정한다.
    params = {"ref": ref} if ref else None
    with httpx.Client(timeout=settings.connector_timeout) as client:
        res = _get(client, url, headers, params)
        if res.status_code == 404:
            return None  # 아직 안 올렸을 수 있다. 실패가 아니라 없는 것이다.
        _raise_limit(res)
        if res.status_code >= 400:
            raise errors.ApiError(502, "TOOL_UNREACHABLE", f"GitHub 오류 {res.status_code}")

        meta = res.json()
        if meta.get("type") != "file":
            raise errors.ApiError(400, "TOOL_NOT_FOUND", f"파일이 아닙니다: {path}")

        blob = _file_bytes(client, headers, _repo_url(base_url, target_resource), meta)
        return {
            "path": meta.get("path", path),
            "sha": meta.get("sha"),
            "size": meta.get("size", len(blob)),
            "htmlUrl": meta.get("html_url"),
            "content": base64.b64encode(blob).decode("ascii"),
        }


def _file_bytes(
    client: httpx.Client, headers: dict[str, str], repo_url: str, meta: dict
) -> bytes:
    """파일 본문. 1MB 를 넘으면 contents 응답에 본문이 없어서 Git blob API 로 받는다.

    응답의 download_url 은 쓰지 않는다. 다른 호스트를 가리킬 수 있고, 거기에 연결 토큰을
    실어 보내게 된다(점검 SEC-02). blob 은 연결에 등록한 같은 API 호스트에서 받는다.
    리다이렉트는 따라가지 않는다(httpx 기본값).
    """
    encoded = meta.get("content")
    if encoded and meta.get("encoding") == "base64":
        return base64.b64decode(encoded)
    sha = meta.get("sha")
    if not sha:
        raise errors.ApiError(502, "TOOL_UNREACHABLE", "파일 본문을 받을 수 없습니다.")
    res = _get(client, f"{repo_url}/git/blobs/{sha}", headers)
    if res.status_code != 200:
        raise errors.ApiError(502, "TOOL_UNREACHABLE", f"파일 내려받기 실패 {res.status_code}")
    blob = res.json()
    if blob.get("encoding") != "base64" or blob.get("content") is None:
        raise errors.ApiError(502, "TOOL_UNREACHABLE", "파일 본문 형식을 읽을 수 없습니다.")
    return base64.b64decode(blob["content"])


def _external_id(kind: str, item: dict) -> str:
    if kind == "commit":
        return f"commit:{item.get('sha')}"
    return f"{kind}:{item.get('number')}"


class GitHubConnector:
    """ToolConnector 구현. 상태가 없다 — 자격증명은 호출마다 받는다."""

    tool = "GITHUB"
    item_kinds = tuple(ITEM_PATHS)

    def verify(self, base_url: str, target: str, secret: str) -> ProbeResult:
        return verify(base_url, target, secret)

    def fetch_items(
        self, base_url: str, target: str, secret: str,
        kind: str, per_page: int, max_pages: int,
        since: datetime | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        return fetch_items(base_url, target, secret, kind, per_page, max_pages, since)

    def fetch_file(
        self, base_url: str, target: str, secret: str, path: str, ref: str | None = None,
    ) -> dict[str, Any] | None:
        return fetch_file(base_url, target, secret, path, ref)

    def fetch_change_files(
        self, base_url: str, target: str, secret: str, kind: str, ident: str,
    ) -> tuple[list[str] | None, int | None]:
        return fetch_change_files(base_url, target, secret, kind, ident)
