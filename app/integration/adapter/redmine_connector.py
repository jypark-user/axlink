"""Redmine 어댑터. 읽기 전용이다 — 원천에 아무것도 쓰지 않는다(QUR.CON.001).

포트의 두 번째 구현체다. 이 파일과 등록소 한 줄이 "신규 도구 연동은 커넥터 구현체
추가만으로 가능하다"(SWFR.CON.001)의 실증이다.

인증은 API 키(X-Redmine-API-Key 헤더) — GitHub 의 Bearer 와 다르지만 "비밀 문자열
하나"라는 포트 계약은 같다. REST API 는 Redmine 기본 설정에서 꺼져 있다(ARC-003 §3).

이슈는 relations 를 함께 실어 온다(추적관계의 재료, SWFR.PIP.003). journals 는 목록
API 가 지원하지 않아 싣지 않는다 — 경과 기록이 필요해지면 상세 API 로 승격한다.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.common import errors
from app.config import settings
from app.integration.port import PageResult, ProbeResult

ITEM_KINDS = ("issue", "version", "tracker")
# 이 항목이 막히면 수집 전체를 실패로 본다. 버전·트래커만 받고 성공으로 끝나면 안 된다
REQUIRED_KINDS = ("issue",)


def external_id(kind: str, item: dict[str, Any]) -> str:
    """원본 키. Redmine 은 일감·버전·트래커에 번호를 각각 1부터 매긴다.

    번호만 쓰면 같은 연결 안에서 버전 7 이 일감 7 을 덮는다. 버전·트래커에는 종류를 붙인다.
    일감은 번호 그대로 둔다. 표준 이슈의 external_id 와 추적 링크 해석(RM-번호)이 이 값을 쓴다.
    """
    ident = str(item.get("id"))
    return ident if kind == "issue" else f"{kind}:{ident}"


def _headers(secret: str) -> dict[str, str]:
    if not secret or not secret.strip():
        raise errors.ApiError(401, "TOOL_AUTH", "API 키가 없습니다.")
    return {"X-Redmine-API-Key": secret}


def _base(base_url: str) -> str:
    return (base_url or "").rstrip("/")


def _get(client: httpx.Client, url: str, headers: dict[str, str], params: dict | None = None):
    try:
        return client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:
        raise errors.ApiError(
            502, "TOOL_UNREACHABLE", f"Redmine 에 닿지 못했습니다: {exc}"
        ) from exc

def _raise_http(res: httpx.Response) -> None:
    """앞에서 따로 다루지 않은 오류 응답을 사용자가 읽을 사유로 바꾼다(DEF-V040).

    상태 코드만 남기면 수집 이력에 「Redmine 오류 401」처럼 남아 무엇을 고쳐야 할지 모른다.
    """
    code = res.status_code
    if code == 401:
        raise errors.ApiError(
            401, "TOOL_AUTH", "인증에 실패했습니다. 토큰이 유효하지 않거나 만료됐습니다."
        )
    if code >= 500:
        raise errors.ApiError(
            502,
            "TOOL_UNREACHABLE",
            f"Redmine 서버가 응답하지 않습니다(HTTP {code}). "
            "서버 상태와 연결 주소를 확인해 주세요.",
        )
    raise errors.ApiError(502, "TOOL_UNREACHABLE", f"Redmine 이 요청을 거절했습니다(HTTP {code}).")



def _raise_project_error(res: httpx.Response) -> None:
    """프로젝트 자체에 닿지 못하면 하드 실패다 — 연결이 성립하지 않는다."""
    if res.status_code == 401:
        raise errors.ApiError(401, "TOOL_AUTH", "API 키가 유효하지 않습니다.")
    if res.status_code in (403, 404):
        raise errors.ApiError(
            404, "TOOL_NOT_FOUND", "프로젝트를 찾을 수 없거나 API 키에 접근 권한이 없습니다."
        )
    if res.status_code == 429:
        raise errors.ApiError(429, "TOOL_RATE_LIMITED", "Redmine 이 요청을 제한했습니다.")
    if res.status_code >= 400:
        _raise_http(res)


def _kind_url(base: str, target: str, kind: str) -> tuple[str, dict[str, Any]]:
    """항목종류별 목록 endpoint. 트래커는 전역이지만 이슈 해석에 필요해 함께 수집한다."""
    if kind == "issue":
        # status_id=* 가 없으면 열린 이슈만 온다. 닫힌 이슈도 이력이다.
        return f"{base}/issues.json", {
            "project_id": target, "status_id": "*",
            "sort": "updated_on:asc", "include": "relations",
        }
    if kind == "version":
        return f"{base}/projects/{target}/versions.json", {}
    if kind == "tracker":
        return f"{base}/trackers.json", {}
    raise errors.ApiError(400, "TOOL_NOT_FOUND", f"모르는 항목종류: {kind}")


def verify(base_url: str, target: str, secret: str) -> ProbeResult:
    """프로젝트 도달을 확인하고, 항목종류별로 실제 읽기 권한을 찔러본다."""
    headers = _headers(secret)
    base = _base(base_url)
    with httpx.Client(timeout=settings.connector_timeout) as client:
        res = _get(client, f"{base}/projects/{target}.json", headers)
        _raise_project_error(res)
        name = (res.json().get("project") or {}).get("name") or target

        result = ProbeResult(name=name)
        for kind in ITEM_KINDS:
            url, params = _kind_url(base, target, kind)
            probe = _get(client, url, headers, params={**params, "limit": 1})
            if probe.status_code < 300:
                result.readable.append(kind)
            elif probe.status_code == 429:
                raise errors.ApiError(429, "TOOL_RATE_LIMITED", "Redmine 이 요청을 제한했습니다.")
            else:
                # 403·404 는 권한 결손. 예상 못 한 응답도 있다고 잘못 알리지 않는다.
                result.denied.append(kind)
    return result


def fetch_items(
    base_url: str, target: str, secret: str, kind: str, per_page: int, max_pages: int,
    since: datetime | None = None, until: datetime | None = None,
) -> Generator[tuple[str, dict], None, PageResult | None]:
    """항목종류 하나를 offset 페이지로 가져온다. (external_id, payload) 를 낸다.

    증분(since)은 이슈만 updated_on 필터를 쓴다. 버전·트래커에는 갱신 필터가 없어
    전량을 다시 낸다 — 몇 건 안 되고, 내용해시 적재가 걸러 준다.

    이슈는 갱신 오름차순(updated_on:asc)이라 상한에 걸리면 마지막으로 읽은 시각부터 다음
    회차가 이어 읽는다(점검 DATA-01). until 은 쓰지 않는다(최신부터 오는 목록이 없다).
    """
    headers = _headers(secret)
    url, params = _kind_url(_base(base_url), target, kind)
    if since is not None and kind == "issue":
        stamp = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        params["updated_on"] = f">={stamp}"
    key = f"{kind}s"  # issues / versions / trackers — Redmine 목록 응답의 루트 키
    last: str | None = None

    with httpx.Client(timeout=settings.connector_timeout) as client:
        for page in range(max_pages):
            res = _get(
                client, url, headers,
                params={**params, "limit": per_page, "offset": page * per_page},
            )
            if res.status_code == 401:
                _raise_http(res)
            if res.status_code == 403:
                raise errors.ApiError(403, "TOOL_AUTH", f"{kind} 읽기 권한이 없습니다.")
            if res.status_code == 429:
                raise errors.ApiError(429, "TOOL_RATE_LIMITED", "Redmine 이 요청을 제한했습니다.")
            if res.status_code >= 400:
                _raise_http(res)
            batch = res.json().get(key) or []
            for item in batch:
                last = item.get("updated_on") or last
                yield external_id(kind, item), item
            if len(batch) < per_page:
                return None
    # 상한에 걸렸다. 다 읽은 것이 아니다
    if kind == "issue" and last:
        return PageResult(resume_since=datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ")
                          .replace(tzinfo=UTC))
    return PageResult()


def fetch_file(
    base_url: str, target: str, secret: str, path: str, ref: str | None = None
) -> dict | None:
    """Redmine 에는 저장소 파일 개념이 없다. WBS 는 형상관리 쪽 커넥터가 가져온다."""
    return None


class RedmineConnector:
    """ToolConnector 구현. 상태가 없다 — 자격증명은 호출마다 받는다."""

    tool = "REDMINE"
    item_kinds = ITEM_KINDS
    required_kinds = REQUIRED_KINDS

    def verify(self, base_url: str, target: str, secret: str) -> ProbeResult:
        return verify(base_url, target, secret)

    def fetch_items(
        self, base_url: str, target: str, secret: str,
        kind: str, per_page: int, max_pages: int,
        since: datetime | None = None, until: datetime | None = None,
    ) -> Generator[tuple[str, dict[str, Any]], None, PageResult | None]:
        return fetch_items(base_url, target, secret, kind, per_page, max_pages, since, until)

    def fetch_file(
        self, base_url: str, target: str, secret: str, path: str, ref: str | None = None,
    ) -> dict[str, Any] | None:
        return fetch_file(base_url, target, secret, path, ref)
