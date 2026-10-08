"""LLM 모델별 토큰 설정 (ARC-011 · SWFR.RAG.002).

Ollama 조회·실측 파싱, done_reason 매핑, 길이 제한 재시도는 모델 없이 시험한다.
설정 API 는 시험용 DB 에서 Ollama 호출을 가짜로 바꿔 돈다.
"""

import json

import httpx
import pytest

from app.ai import llm, model_settings, ollama_admin
from app.common import errors
from tests.conftest import requires_db

_ADMIN = "r1"
_BASE = "http://ollama.test:11434"


def _done(text: str) -> dict:
    return {"model": "m", "message": {"content": text}, "done_reason": "stop"}


def _cut(text: str) -> dict:
    return {"model": "m", "message": {"content": text}, "done_reason": "length"}


def _client_with(handler, monkeypatch):
    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: real(transport=transport))


# --- /api/tags 파싱 ------------------------------------------------------------


def test_tags_응답에서_문맥과_도구지원을_읽는다():
    m = ollama_admin.parse_tag({
        "name": "qwen3:4b",
        "details": {
            "context_length": 40960, "parameter_size": "4.0B", "quantization_level": "Q4_K_M",
        },
        "capabilities": ["completion", "tools", "thinking"],
    })
    assert m.context_length == 40960
    assert m.supports_tools is True
    assert m.parameter_size == "4.0B" and m.quantization == "Q4_K_M"


def test_문맥을_안_알려주는_옛_서버는_0_이다():
    m = ollama_admin.parse_tag({"name": "old:latest", "details": {}})
    assert m.context_length == 0
    assert m.supports_tools is False
    assert m.parameter_size is None


# --- 생성 속도 실측 -------------------------------------------------------------


def test_실측은_eval_count_나누기_eval_duration_이다():
    rate = ollama_admin.rate_from_generate("m", {"eval_count": 64, "eval_duration": 3_440_860_215})
    assert rate.tok_per_sec == 18.6
    assert rate.eval_count == 64


def test_통계가_없으면_숫자를_지어내지_않는다():
    with pytest.raises(errors.ApiError) as exc:
        ollama_admin.rate_from_generate("m", {"response": "1 2 3"})
    assert exc.value.code == "AI_UNAVAILABLE"


def test_실측_요청은_짧고_생각을_끈다(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"model": "m", "eval_count": 40, "eval_duration": 2_000_000_000}
        )

    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(ollama_admin.httpx, "Client", lambda **kw: real(transport=transport))
    rate = ollama_admin.measure_rate(_BASE, "m")

    assert rate.tok_per_sec == 20.0
    assert seen["stream"] is False and seen["think"] is False
    assert seen["options"]["num_predict"] == 64


# --- done_reason → stop_reason ------------------------------------------------


def test_done_reason_매핑():
    assert llm.stop_reason_of({"done_reason": "length"}) == "max_tokens"
    with_tool = {"done_reason": "stop", "message": {"tool_calls": [{}]}}
    assert llm.stop_reason_of(with_tool) == "tool_use"
    plain = {"done_reason": "stop", "message": {"content": "x"}}
    assert llm.stop_reason_of(plain) == "end_turn"


def test_옵션은_모델별_값을_넣고_비면_넣지_않는다(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_done("답"))

    _client_with(handler, monkeypatch)
    llm.OllamaLlm(_BASE, "m", 5, num_ctx=None, num_predict=4000).complete("s", "u")
    assert "num_ctx" not in seen["options"]
    assert seen["options"]["num_predict"] == 4000

    llm.OllamaLlm(_BASE, "m", 5, num_ctx=8192, num_predict=16000).complete("s", "u")
    assert seen["options"] == {"num_ctx": 8192, "num_predict": 16000}


def test_결과에_토큰_수와_멈춘_이유가_남는다(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "model": "m", "message": {"content": "답"}, "done_reason": "stop",
            "prompt_eval_count": 120, "eval_count": 7,
        })

    _client_with(handler, monkeypatch)
    r = llm.OllamaLlm(_BASE, "m", 5).complete("s", "u")
    assert (r.stop_reason, r.prompt_tokens, r.output_tokens) == ("end_turn", 120, 7)


# --- 길이 제한 재시도 ---------------------------------------------------------


def test_잘리면_더_작게_나눠_달라고_이어_묻는다(monkeypatch):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body["messages"])
        if len(calls) < 3:
            return httpx.Response(200, json=_cut("잘린"))
        return httpx.Response(200, json=_done("완성"))

    _client_with(handler, monkeypatch)
    r = llm.OllamaLlm(_BASE, "m", 5).complete("s", "u")

    assert r.text == "완성" and r.stop_reason == "end_turn"
    assert len(calls) == 3
    # 두 번째 호출부터 잘린 답과 지시가 대화에 붙는다
    assert [m["role"] for m in calls[1]] == ["system", "user", "assistant", "user"]
    assert "더 작게 나눠" in calls[1][-1]["content"]


def test_세_번_이어도_잘리면_범위를_줄이라고_멈춘다(monkeypatch):
    n = {"calls": 0}

    def handler(request):
        n["calls"] += 1
        return httpx.Response(200, json=_cut("잘린"))

    _client_with(handler, monkeypatch)
    with pytest.raises(errors.ApiError) as exc:
        llm.OllamaLlm(_BASE, "m", 5).complete("s", "u")
    assert exc.value.code == "AI_OUTPUT_TRUNCATED" and exc.value.status == 422
    assert n["calls"] == 1 + llm.MAX_LENGTH_RETRIES


# --- 설정 API (시험용 DB) -----------------------------------------------------


_TAGS = [
    ollama_admin.DiscoveredModel("qwen3:4b", 40960, True, "4.0B", "Q4_K_M"),
    ollama_admin.DiscoveredModel("gemma3:1b", 0, False, "1.0B", "Q4_0"),
    ollama_admin.DiscoveredModel("bge-m3:latest", 8192, False, "566M", "F16", ("embedding",)),
    ollama_admin.DiscoveredModel(
        "gemma4:e4b", 131072, True, "8.0B", "Q4_K_M", ("completion", "tools", "vision")
    ),
]


@pytest.fixture
def admin_headers(client_token):
    return {"Authorization": f"Bearer {client_token(_ADMIN)}"}


@pytest.fixture
def fake_ollama(monkeypatch):
    """Ollama 호출을 가짜로 바꾸고, 지난 실행이 남긴 시험용 주소의 캐시를 비운다."""
    from app.db import tx

    with tx() as cur:
        cur.execute("delete from llm_setting where base_url = %s", (_BASE,))
        cur.execute("delete from llm_model_cache where base_url = %s", (_BASE,))
    monkeypatch.setattr(model_settings.ollama_admin, "list_models", lambda base: list(_TAGS))
    monkeypatch.setattr(
        model_settings.ollama_admin,
        "measure_rate",
        lambda base, model: ollama_admin.MeasuredRate(model, 18.6, 64, 3.44),
    )


@requires_db
def test_목록_조회는_캐시를_갈아_끼운다(client, admin_headers, fake_ollama):
    res = client.post(
        "/api/ai/models/refresh", params={"baseUrl": _BASE + "/"}, headers=admin_headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["error"] is None and body["baseUrl"] == _BASE
    by_name = {m["name"]: m for m in body["models"]}
    assert by_name["qwen3:4b"]["numCtx"] == 40960 and by_name["qwen3:4b"]["supportsTools"] is True
    # 최대치를 모르면 비워 모델 기본값에 맡긴다
    assert by_name["gemma3:1b"]["numCtx"] is None and by_name["gemma3:1b"]["contextLength"] == 0
    assert by_name["gemma3:1b"]["numPredict"] == 16000


@requires_db
def test_조회_실패는_예외가_아니라_상태_문구다(client, admin_headers, monkeypatch):
    def boom(base):
        raise errors.ApiError(503, "AI_UNAVAILABLE", "닿지 못했습니다")

    monkeypatch.setattr(model_settings.ollama_admin, "list_models", boom)
    res = client.post(
        "/api/ai/models/refresh", params={"baseUrl": "http://nowhere:1"}, headers=admin_headers
    )
    assert res.status_code == 200
    assert "닿지 못했습니다" in res.json()["error"]


@requires_db
def test_실측은_캐시에_남고_설정은_그_값을_다시_읽는다(client, admin_headers, fake_ollama):
    client.post("/api/ai/models/refresh", params={"baseUrl": _BASE}, headers=admin_headers)
    res = client.post(
        "/api/ai/models/measure",
        params={"baseUrl": _BASE, "model": "qwen3:4b"},
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["tokPerSec"] == 18.6

    saved = client.put(
        "/api/ai/settings",
        json={"baseUrl": _BASE, "model": "qwen3:4b", "numCtx": 16384, "numPredict": 8000},
        headers=admin_headers,
    )
    assert saved.status_code == 200, saved.text
    got = client.get("/api/ai/settings", headers=admin_headers).json()
    assert got["model"] == "qwen3:4b" and got["requestTimeoutSeconds"] > 0
    me = next(m for m in got["models"] if m["name"] == "qwen3:4b")
    assert (me["tokPerSec"], me["numCtx"], me["numPredict"]) == (18.6, 16384, 8000)

    # 목록을 다시 받아도 설정과 실측은 물려받는다
    client.post("/api/ai/models/refresh", params={"baseUrl": _BASE}, headers=admin_headers)
    models = client.get("/api/ai/settings", headers=admin_headers).json()["models"]
    again = next(m for m in models if m["name"] == "qwen3:4b")
    assert (again["tokPerSec"], again["numCtx"], again["numPredict"]) == (18.6, 16384, 8000)


@requires_db
def test_어댑터는_활성_모델의_값으로_요청을_만든다(client, admin_headers, fake_ollama):
    from app.db import tx

    client.post("/api/ai/models/refresh", params={"baseUrl": _BASE}, headers=admin_headers)
    client.put(
        "/api/ai/settings",
        json={"baseUrl": _BASE, "model": "gemma3:1b", "numCtx": None, "numPredict": 2000},
        headers=admin_headers,
    )
    with tx() as cur:
        cfg = model_settings.runtime_config(cur)
    assert (cfg.base_url, cfg.model) == (_BASE, "gemma3:1b")
    assert (cfg.num_ctx, cfg.num_predict) == (None, 2000)


@requires_db
def test_목록에_없는_모델은_고를_수_없다(client, admin_headers, fake_ollama):
    res = client.put(
        "/api/ai/settings",
        json={"baseUrl": _BASE, "model": "없는모델", "numPredict": 100},
        headers=admin_headers,
    )
    assert res.status_code == 422 or res.status_code == 400


@requires_db
def test_관리자가_아니면_못_본다(client, client_token):
    res = client.get("/api/ai/settings", headers={"Authorization": f"Bearer {client_token('r2')}"})
    assert res.status_code == 403


# --- 모델 용도 (ARC-022) ---------------------------------------------------------


def test_용도는_서버가_알려준_capabilities_로만_판단한다():
    assert model_settings.purpose_of(["completion", "tools"]) == "ANSWER"
    assert model_settings.purpose_of(["embedding"]) == "EMBEDDING"
    # 이름이 embed 같아도, 안 알려주면 모른다
    assert model_settings.purpose_of(None) == "UNKNOWN"
    assert model_settings.purpose_of([]) == "UNKNOWN"
    assert model_settings.purpose_of(["vision"]) == "UNKNOWN"


def test_capabilities_를_안_주는_서버는_모름으로_남긴다():
    assert ollama_admin.parse_tag({"name": "old", "details": {}}).capabilities is None
    m = ollama_admin.parse_tag({"name": "bge-m3", "details": {}, "capabilities": ["embedding"]})
    assert m.capabilities == ("embedding",)


@requires_db
def test_목록에_용도가_실린다(client, admin_headers, fake_ollama):
    body = client.post(
        "/api/ai/models/refresh", params={"baseUrl": _BASE}, headers=admin_headers
    ).json()
    by_name = {m["name"]: m for m in body["models"]}
    assert by_name["bge-m3:latest"]["purpose"] == "EMBEDDING"
    assert by_name["gemma4:e4b"]["purpose"] == "ANSWER"
    assert by_name["qwen3:4b"]["purpose"] == "UNKNOWN"


@requires_db
def test_임베딩_전용_모델은_답변_모델로_저장되지_않는다(client, admin_headers, fake_ollama):
    from app.db import fetch_one, tx

    client.post("/api/ai/models/refresh", params={"baseUrl": _BASE}, headers=admin_headers)
    res = client.put(
        "/api/ai/settings",
        json={"baseUrl": _BASE, "model": "bge-m3:latest", "numPredict": 100},
        headers=admin_headers,
    )
    assert res.status_code == 400 and res.json()["code"] == "MODEL_ROLE_MISMATCH"
    with tx() as cur:
        assert fetch_one(cur, "select 1 from llm_setting where base_url = %s", (_BASE,)) is None


@requires_db
def test_짧은_생성이_안_되면_저장하지_않는다(client, admin_headers, fake_ollama, monkeypatch):
    def boom(base, model):
        raise errors.ApiError(503, "AI_UNAVAILABLE", "생성 실패")

    monkeypatch.setattr(model_settings.ollama_admin, "measure_rate", boom)
    client.post("/api/ai/models/refresh", params={"baseUrl": _BASE}, headers=admin_headers)
    res = client.put(
        "/api/ai/settings",
        json={"baseUrl": _BASE, "model": "qwen3:4b", "numPredict": 100},
        headers=admin_headers,
    )
    assert res.status_code == 400 and res.json()["code"] == "MODEL_CHECK_FAILED"


@requires_db
def test_저장하면_확인_시각과_출처가_남는다(client, admin_headers, fake_ollama):
    client.post("/api/ai/models/refresh", params={"baseUrl": _BASE}, headers=admin_headers)
    res = client.put(
        "/api/ai/settings",
        json={"baseUrl": _BASE, "model": "qwen3:4b", "numPredict": 100},
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["source"] == "DB" and "답변 생성" in got["usedFor"]
    me = next(m for m in got["models"] if m["name"] == "qwen3:4b")
    assert me["verifiedAt"] is not None and me["tokPerSec"] == 18.6


@requires_db
def test_검색_모델은_현황만_보이고_바꾸지_못한다(client, admin_headers):
    got = client.get("/api/ai/embedding", headers=admin_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["source"] == "ENV" and body["dimension"] == body["columnDimension"]
    assert body["changeBlockedReason"]
    put = client.put("/api/ai/embedding", json={"model": "other"}, headers=admin_headers)
    assert put.status_code == 409 and put.json()["code"] == "EMBEDDING_CHANGE_BLOCKED"


@requires_db
def test_검색_모델_현황은_관리자만(client, client_token):
    res = client.get("/api/ai/embedding", headers={"Authorization": f"Bearer {client_token('r2')}"})
    assert res.status_code == 403
