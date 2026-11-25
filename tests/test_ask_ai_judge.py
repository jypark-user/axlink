"""AI 판단 답변 방식 (ARC-034). 설정 전환, 판정 생략, 사업 자원, 수치 검문을 실제 DB 로 본다.

모델은 대본 흉내다. 문장 품질이 아니라 흐름을 본다: AI 판단이면 판정(complete)을 부르지 않고
생성(stream)을 한 번만 부르며, 프롬프트에 사업 자원이 들어가고, 자원에 없는 숫자는 막힌다.
"""

import pytest

from app.config import settings
from app.db import tx
from app.rag import number_guard
from app.rag import service as ask_service
from tests.conftest import requires_db
from tests.test_ask_api import PID, ScriptedLlm, _ask, _auth

pytestmark = requires_db


class NoJudgeLlm(ScriptedLlm):
    """판정을 부르면 실패한다. AI 판단은 판정 단계가 없다."""

    def complete(self, system, user, *, json_schema=None):  # noqa: ARG002
        raise AssertionError("AI 판단에서 판정(complete)을 불렀다")


@pytest.fixture
def ai_mode():
    with tx() as cur:
        cur.execute(
            "insert into answer_setting (id, mode) values (1, 'AI_JUDGE') "
            "on conflict (id) do update set mode = 'AI_JUDGE'"
        )
    yield
    with tx() as cur:
        cur.execute("delete from answer_setting")


@pytest.fixture
def conversation(client, client_token):
    created: list[str] = []

    def _new() -> tuple[str, str]:
        token = client_token("r2")
        res = client.post(
            "/api/conversations",
            json={"title": "AI 판단", "projectScope": [PID]},
            headers=_auth(token),
        )
        assert res.status_code == 201, res.text
        created.append(res.json()["id"])
        return res.json()["id"], token

    yield _new
    with tx() as cur:
        cur.execute("delete from conversation where id = any(%s::uuid[])", (created,))


def test_답변_방식은_기본이_지표_기반이고_관리자만_바꾼다(client, client_token):
    with tx() as cur:
        cur.execute("delete from answer_setting")
    reader = client_token("r2")
    res = client.get("/api/ai/answer-mode", headers=_auth(reader))
    assert res.status_code == 200
    assert res.json()["mode"] == "STRUCTURED" and res.json()["label"] == "지표 기반"

    denied = client.put("/api/ai/answer-mode", json={"mode": "AI_JUDGE"}, headers=_auth(reader))
    assert denied.status_code == 403

    admin = client_token("r1")
    bad = client.put("/api/ai/answer-mode", json={"mode": "FREE"}, headers=_auth(admin))
    assert bad.status_code in (400, 422)
    try:
        ok = client.put("/api/ai/answer-mode", json={"mode": "AI_JUDGE"}, headers=_auth(admin))
        assert ok.status_code == 200 and ok.json()["label"] == "AI 판단"
        assert client.get("/api/ai/answer-mode", headers=_auth(reader)).json()["mode"] == "AI_JUDGE"
    finally:
        with tx() as cur:
            cur.execute("delete from answer_setting")


def test_AI_판단은_판정없이_사업_자원으로_한_번에_답한다(
    client, conversation, ai_mode, monkeypatch
):
    with tx() as cur:
        open_count = cur.execute(
            "select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL' "
            "and status not in ('RESOLVED','CLOSED')",
            (PID,),
        ).fetchone()["n"]
    scripted = NoJudgeLlm(None, "가장 먼저 볼 것은 열린 일반 이슈입니다 [자원: 핵심 지표].")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)  # 문서 근거 없이 자원만으로

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "지금 이 사업에서 가장 급한 게 뭐야?")

    start = events[0][1]
    assert start["routing"]["type"] == "AI_JUDGE"
    assert scripted.stream_calls == 1
    prompt = scripted.prompts[0]
    assert "## 사업 자원" in prompt and "### 핵심 지표" in prompt
    assert "열린 일반 이슈" in prompt  # 지표와 목록이 자원으로 들어간다
    if open_count:
        assert "처리 중 일반 이슈" in prompt or "일반 이슈" in prompt
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert text.startswith("가장 먼저 볼 것은 열린 일반 이슈입니다")
    assert events[-1][1]["finishReason"] == "STOP"

    with tx() as cur:
        saved = cur.execute(
            "select route_type from message where conversation_id = %s and role = 'ASSISTANT'",
            (conversation_id,),
        ).fetchone()
    assert saved["route_type"] == "AI_JUDGE"


def test_AI_판단도_자원에_없는_숫자는_막는다(client, conversation, ai_mode, monkeypatch):
    scripted = NoJudgeLlm(None, "열린 이슈가 9876건이라 위험합니다. 일정부터 확인하십시오.")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "위험한 게 뭐야?")
    deltas = [d["text"] for e, d in events if e == "delta"]
    assert all("9876" not in piece for piece in deltas)
    assert number_guard.BLOCKED_NOTE in "".join(deltas)
    assert events[-1][1]["finishReason"] == "NUMBER_GUARD"


def test_지표_기반이면_예전처럼_판정을_거친다(client, conversation, monkeypatch):
    with tx() as cur:
        cur.execute("delete from answer_setting")
    scripted = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"}, "확인했습니다."
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)
    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈 건수는?")
    assert events[0][1]["routing"]["type"] == "AGGREGATE"
