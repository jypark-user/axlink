"""어댑터 오류 응답 → 수집 이력 사유 (DEF-V040, AC-011-6a, COMMON-S09).

프로세스 안 재생기는 어댑터 함수를 통째로 바꿔 이미 분류된 오류를 던진다. 그래서 실제
어댑터가 HTTP 상태를 사유로 옮기는 부분은 원격 리허설에서야 드러났다. 여기서는 HTTP 응답만
흉내 내고 어댑터 코드는 그대로 돈다.
"""

from collections.abc import Callable

import httpx
import pytest

from app.common import errors
from app.integration.adapter import github_connector, redmine_connector

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def http(monkeypatch):
    """어댑터가 여는 httpx.Client 에 응답 흉내를 끼운다."""

    def install(module, handler: Handler) -> None:
        real = httpx.Client

        def client(*args, **kwargs):
            return real(*args, transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(module.httpx, "Client", client)

    return install


def _drain(gen):
    for _ in gen:
        pass


def _github_list(status: int) -> Handler:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/issues"):
            return httpx.Response(status, json={"message": "x"})
        return httpx.Response(200, json=[])

    return handle


def test_GitHub_수집_중_401_은_인증_실패로_남는다(http):
    http(github_connector, _github_list(401))
    with pytest.raises(errors.ApiError) as exc:
        _drain(github_connector.fetch_items("https://gh.test", "o/r", "t", "issue", 50, 1))
    assert exc.value.code == "TOOL_AUTH"
    assert "인증" in exc.value.message and "401" not in exc.value.message


@pytest.mark.parametrize("status", [500, 502, 503])
def test_GitHub_수집_중_5xx_는_서버_연결_사유로_남는다(http, status):
    http(github_connector, _github_list(status))
    with pytest.raises(errors.ApiError) as exc:
        _drain(github_connector.fetch_items("https://gh.test", "o/r", "t", "issue", 50, 1))
    assert exc.value.code == "TOOL_UNREACHABLE"
    assert "서버" in exc.value.message and "연결" in exc.value.message
    assert not exc.value.message.startswith("GitHub 오류")


def test_GitHub_연결_테스트에서_서버_장애는_연결_사유로_거절한다(http):
    http(github_connector, lambda req: httpx.Response(502, text="bad gateway"))
    with pytest.raises(errors.ApiError) as exc:
        github_connector.verify("https://gh.test", "o/r", "t")
    assert exc.value.code == "TOOL_UNREACHABLE"
    assert "연결" in exc.value.message


def test_GitHub_그_밖의_4xx_는_거절로_남는다(http):
    http(github_connector, _github_list(422))
    with pytest.raises(errors.ApiError) as exc:
        _drain(github_connector.fetch_items("https://gh.test", "o/r", "t", "issue", 50, 1))
    assert exc.value.code == "TOOL_UNREACHABLE"
    assert "거절" in exc.value.message and "422" in exc.value.message


def _redmine_list(status: int) -> Handler:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/issues.json"):
            return httpx.Response(status, json={})
        return httpx.Response(200, json={"project": {"identifier": "p"}})

    return handle


def test_Redmine_수집_중_401_은_권한이_아니라_인증_실패다(http):
    http(redmine_connector, _redmine_list(401))
    with pytest.raises(errors.ApiError) as exc:
        _drain(redmine_connector.fetch_items("https://rm.test", "p", "k", "issue", 50, 1))
    assert exc.value.code == "TOOL_AUTH"
    assert "인증" in exc.value.message


def test_Redmine_수집_중_403_은_종류별_권한_결손으로_남는다(http):
    http(redmine_connector, _redmine_list(403))
    with pytest.raises(errors.ApiError) as exc:
        _drain(redmine_connector.fetch_items("https://rm.test", "p", "k", "issue", 50, 1))
    assert exc.value.code == "TOOL_AUTH" and "issue 읽기 권한" in exc.value.message


def test_Redmine_서버_장애는_서버_연결_사유로_남는다(http):
    http(redmine_connector, _redmine_list(502))
    with pytest.raises(errors.ApiError) as exc:
        _drain(redmine_connector.fetch_items("https://rm.test", "p", "k", "issue", 50, 1))
    assert exc.value.code == "TOOL_UNREACHABLE"
    assert "Redmine 서버" in exc.value.message and "연결" in exc.value.message


def _redmine_verify(project_status: int, current_status: int) -> Handler:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/users/current.json"):
            return httpx.Response(current_status, json={"user": {"id": 1}})
        if req.url.path.endswith("/projects/p.json"):
            return httpx.Response(project_status, json={"project": {"name": "P"}})
        return httpx.Response(200, json={})

    return handle


def test_Redmine_REST_가_꺼져_있으면_따로_안내한다(http):
    """DEF-V014. REST 가 꺼지면 프로젝트도 자기 정보도 403 이다."""
    http(redmine_connector, _redmine_verify(403, 403))
    with pytest.raises(errors.ApiError) as exc:
        redmine_connector.verify("https://rm.test", "p", "k")
    assert exc.value.code == "TOOL_REST_DISABLED"
    assert "REST" in exc.value.message and "관리" in exc.value.message


def test_Redmine_키는_유효한데_프로젝트가_403_이면_권한_문제다(http):
    http(redmine_connector, _redmine_verify(403, 200))
    with pytest.raises(errors.ApiError) as exc:
        redmine_connector.verify("https://rm.test", "p", "k")
    assert exc.value.code == "TOOL_NOT_FOUND"
    assert "REST" not in exc.value.message


def test_Redmine_프로젝트가_없으면_자기_정보를_묻지_않는다(http):
    seen: list[str] = []
    base = _redmine_verify(404, 403)

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        return base(req)

    http(redmine_connector, handle)
    with pytest.raises(errors.ApiError) as exc:
        redmine_connector.verify("https://rm.test", "p", "k")
    assert exc.value.code == "TOOL_NOT_FOUND"
    assert not any(p.endswith("/users/current.json") for p in seen)
