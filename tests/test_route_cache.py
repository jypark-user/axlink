"""라우팅 캐시 (ARC-014 · SWFR.RAG.005).

같은 질문이면 판정을 모델에 다시 묻지 않는다. 값은 매번 새로 뽑는다. 키가 정확히 같은
문자열과 카탈로그 버전인지, 유사한 문장은 맞추지 않는지를 본다.
"""

import json
from collections.abc import Iterator

import pytest

from app.ai.port import LlmResult
from app.config import settings
from app.db import tx
from app.rag import route_cache, routing
from app.rag import service as ask_service
from tests.conftest import requires_db
from tests.test_widget_generation import _catalog

PID = "c0000000-0000-4000-8000-000000000001"


def test_정규화는_공백과_끝_문장부호만_뗀다():
    assert route_cache.normalize("  이슈  목록   조회해줘? ") == "이슈 목록 조회해줘"
    with_dot = route_cache.normalize("이슈 목록 조회해줘.")
    assert with_dot == route_cache.normalize("이슈 목록 조회해줘")
    # 조건이 다른 질문은 다른 키다. 유사도로 맞추지 않는다
    v = "v"
    assert route_cache.key_of("열린 이슈 목록", v) != route_cache.key_of("닫힌 이슈 목록", v)


def test_카탈로그_버전은_프롬프트_전체를_따른다(monkeypatch):
    cat = _catalog()
    before = route_cache.catalog_version(cat)
    monkeypatch.setattr(routing, "system_prompt", lambda c: "다른 프롬프트")
    assert route_cache.catalog_version(cat) != before


class _Counting:
    def __init__(self, route: dict, text: str = "답") -> None:
        self.route, self.text = route, text
        self.complete_calls = 0

    def complete(self, system: str, user: str, *, json_schema=None) -> LlmResult:
        self.complete_calls += 1
        return LlmResult(text=json.dumps(self.route, ensure_ascii=False), model="counting")

    def stream(self, system: str, user: str, *, json_schema=None) -> Iterator[str]:
        raw = json.dumps({"answer": self.text}, ensure_ascii=False) if json_schema else self.text
        yield raw


@pytest.fixture
def clean_cache():
    with tx() as cur:
        cur.execute("delete from route_cache")
    yield
    with tx() as cur:
        cur.execute("delete from route_cache")


@requires_db
def test_같은_질문은_모델을_다시_부르지_않는다(clean_cache):
    cat = _catalog()
    llm = _Counting({"route": "AGGREGATE", "measure": "open_issue_count", "template": "STAT_CARD"})
    with tx() as cur:
        first = route_cache.decide(cur, cat, llm, "열린 이슈 몇 건이야?")
        assert route_cache.remember(cur, "열린 이슈 몇 건이야?", first) is True
        second = route_cache.decide(cur, cat, llm, "열린  이슈 몇 건이야")
        assert route_cache.remember(cur, "열린  이슈 몇 건이야", second) is False  # 캐시에서 온 것
        other = route_cache.decide(cur, cat, llm, "닫힌 이슈 몇 건이야?")
        hits = cur.execute("select sum(hit_count) as n from route_cache").fetchone()["n"]
    assert (first.cached, second.cached, other.cached) == (False, True, False)
    assert llm.complete_calls == 2
    assert second.decision.measure is not None
    assert second.decision.measure.key == first.decision.measure.key == "open_issue_count"
    assert hits == 1


@requires_db
def test_읽을_수_없는_답은_저장하지_않는다(clean_cache):
    class _Garbage(_Counting):
        def complete(self, system, user, *, json_schema=None):
            self.complete_calls += 1
            return LlmResult(text="모르겠다", model="counting")

    cat = _catalog()
    llm = _Garbage({})
    with tx() as cur:
        r1 = route_cache.decide(cur, cat, llm, "아무거나")
        assert route_cache.remember(cur, "아무거나", r1) is False
        route_cache.decide(cur, cat, llm, "아무거나")
        n = cur.execute("select count(*) as n from route_cache").fetchone()["n"]
    assert llm.complete_calls == 2 and n == 0


@requires_db
def test_캐시된_판정도_카탈로그로_다시_검증한다(clean_cache, monkeypatch):
    """지표가 폐기되면 옛 판정은 문서 경로로 내려간다. 캐시가 카탈로그를 앞서지 않는다."""
    cat = _catalog()
    llm = _Counting({"route": "AGGREGATE", "measure": "open_issue_count", "template": "STAT_CARD"})
    with tx() as cur:
        route_cache.remember(cur, "열린 이슈", route_cache.decide(cur, cat, llm, "열린 이슈"))
        version = route_cache.catalog_version(cat)
        cur.execute(
            "update route_cache set choice_json = %s where catalog_version = %s",
            ('{"route": "AGGREGATE", "measure": "retired", "template": "STAT_CARD"}', version),
        )
        again = route_cache.decide(cur, cat, llm, "열린 이슈")
    assert again.cached is True and again.decision.type == routing.DOCUMENT


@requires_db
def test_끄면_매번_묻는다(clean_cache, monkeypatch):
    monkeypatch.setattr(settings, "rag_route_cache", False)
    cat = _catalog()
    llm = _Counting({"route": "DOCUMENT", "query": "x"})
    with tx() as cur:
        route_cache.remember(cur, "질문", route_cache.decide(cur, cat, llm, "질문"))
        r = route_cache.decide(cur, cat, llm, "질문")
        n = cur.execute("select count(*) as n from route_cache").fetchone()["n"]
    assert llm.complete_calls == 2 and r.cached is False and n == 0


@requires_db
def test_답변_경로에서_두_번째_질문은_캐시_표시가_붙는다(
    client, client_token, clean_cache, monkeypatch
):
    # 집계 경로는 청크가 없어도 답을 만든다. 답을 만든 판정만 저장되므로 그 길로 간다
    llm = _Counting(
        {"route": "AGGREGATE", "measure": "open_issue_count", "template": "STAT_CARD"}, "답입니다."
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: llm)
    monkeypatch.setattr(settings, "rag_overview_fallback", False)
    token = client_token("r2")
    headers = {"Authorization": f"Bearer {token}"}
    cid = client.post(
        "/api/conversations", json={"title": "캐시", "projectScope": [PID]}, headers=headers
    ).json()["id"]

    def ask() -> dict:
        with client.stream(
            "POST",
            f"/api/conversations/{cid}/messages",
            json={"question": "이슈 어떻게 돼 가?", "projectScope": []},
            headers={**headers, "Accept": "text/event-stream"},
        ) as res:
            start = None
            event = None
            for line in res.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event == "start":
                    start = json.loads(line[5:])
            return start["routing"]

    first, second = ask(), ask()
    assert first["routeCached"] is False and second["routeCached"] is True
    assert llm.complete_calls == 1
    client.delete(f"/api/conversations/{cid}", headers=headers)


@requires_db
def test_근거가_없어_막힌_판정은_저장하지_않는다(client, client_token, clean_cache, monkeypatch):
    """"가장 급한 작업" 을 문서 검색으로 보낸 판정이 캐시에 남아 같은 질문이 계속 막혔다.
    답을 못 만든 판정은 다음에 다시 묻는다."""
    llm = _Counting({"route": "DOCUMENT", "query": "급한 작업"})
    monkeypatch.setattr(ask_service, "llm_port", lambda: llm)
    monkeypatch.setattr(settings, "rag_overview_fallback", False)  # 게이트 자체를 본다
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)  # 근거 게이트가 막는다
    token = client_token("r2")
    headers = {"Authorization": f"Bearer {token}"}
    cid = client.post(
        "/api/conversations", json={"title": "급한", "projectScope": [PID]}, headers=headers
    ).json()["id"]
    for _ in range(2):
        with client.stream(
            "POST",
            f"/api/conversations/{cid}/messages",
            json={"question": "지금 가장 급한 작업이 뭐야?", "projectScope": []},
            headers={**headers, "Accept": "text/event-stream"},
        ) as res:
            res.read()
    with tx() as cur:
        n = cur.execute("select count(*) as n from route_cache").fetchone()["n"]
    assert n == 0 and llm.complete_calls == 2
    client.delete(f"/api/conversations/{cid}", headers=headers)
