"""연결 주소 정책과 인증정보 전달 범위 (SER.SEC.001, 점검 SEC-01·SEC-02).

- http 는 같은 기계(루프백) 주소만 받는다. 문자열 앞부분이 아니라 실제 호스트로 판단한다.
- 저장소 파일 본문은 연결에 등록한 API 호스트에서만 받는다. 응답이 알려 준 다른 주소에
  인증 헤더를 보내지 않는다. 시험은 가짜 토큰과 모의 HTTP 만 쓴다(실제 요청 없음).
"""

import base64

import httpx
import pytest

from app.common import errors
from app.integration import service
from app.integration.adapter import github_connector

FAKE_TOKEN = "ghp_fake_token_for_test_only"


@pytest.mark.parametrize("url", [
    "https://api.github.com",
    "https://ghe.example.internal/api/v3",   # 사내 GitHub Enterprise
    "https://redmine.example.internal",      # 사내 Redmine
    "https://10.0.0.5:8443/redmine",         # 사설 주소도 https 면 된다
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000/redmine",
    "http://[::1]:3000",
    "HTTPS://API.GITHUB.COM",
])
def test_https_와_같은_기계_http_는_받는다(url):
    service._require_https(url)


@pytest.mark.parametrize("url", [
    "http://localhost.attacker.invalid",      # 앞부분만 localhost
    "http://127.0.0.1.attacker.invalid",
    "http://localhost@attacker.invalid",      # 실제 호스트는 attacker.invalid
    "http://127.0.0.1@attacker.invalid/x",
    "https://user:pass@api.github.com",       # 주소에 사용자 정보
    "https://token@api.github.com",
    "http://example.com",
    "http://10.0.0.5",                        # 사설 주소라도 http 는 안 된다
    "ftp://localhost",
    "localhost:3000",                         # scheme 없음
    "https://",                               # 호스트 없음
    "http://localhost:notaport",
    "",
])
def test_루프백이_아닌_http_와_사용자_정보가_든_주소는_거절한다(url):
    with pytest.raises(errors.ApiError) as exc:
        service._require_https(url)
    assert exc.value.status == 400


# --------------------------------------------------------------- 파일 본문 받기


def _client(handler) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(record)), seen


REPO = "https://api.github.com/repos/o/r"
BIG_FILE = {  # 1MB 를 넘으면 contents 응답에 본문이 없다
    "type": "file", "path": "docs/WBS.xlsx", "sha": "abc123", "size": 2_000_000,
    "content": "", "encoding": "none",
    "download_url": "https://other-host.invalid/o/r/main/docs/WBS.xlsx",
}


def test_큰_파일은_같은_API_호스트의_blob_으로_받고_다른_호스트에_토큰을_보내지_않는다():
    body = b"wbs-bytes"

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "api.github.com" and req.url.path == "/repos/o/r/git/blobs/abc123":
            return httpx.Response(200, json={
                "sha": "abc123", "encoding": "base64",
                "content": base64.b64encode(body).decode(),
            })
        return httpx.Response(200, content=b"should-not-be-called")

    client, seen = _client(handler)
    headers = github_connector._headers(FAKE_TOKEN)
    got = github_connector._file_bytes(client, headers, REPO, BIG_FILE)
    assert got == body
    assert {r.url.host for r in seen} == {"api.github.com"}
    assert all(r.headers.get("Authorization") == f"Bearer {FAKE_TOKEN}" for r in seen)


def test_blob_API_가_다른_호스트로_보내면_따라가지_않고_실패한다():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "api.github.com":
            return httpx.Response(302, headers={"Location": "https://other-host.invalid/x"})
        return httpx.Response(200, content=b"leak")

    client, seen = _client(handler)
    with pytest.raises(errors.ApiError):
        github_connector._file_bytes(
            client, github_connector._headers(FAKE_TOKEN), REPO, BIG_FILE
        )
    assert all(r.url.host == "api.github.com" for r in seen)


def test_contents_응답에_본문이_있으면_더_요청하지_않는다():
    meta = {**BIG_FILE, "content": base64.b64encode(b"small").decode() + "\n",
            "encoding": "base64"}
    client, seen = _client(lambda req: httpx.Response(500))
    got = github_connector._file_bytes(client, github_connector._headers(FAKE_TOKEN), REPO, meta)
    assert got == b"small" and seen == []
