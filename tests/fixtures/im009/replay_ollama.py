"""재생 서버의 Ollama 흉내. 원격 대상(5174)에서 대본 모델 시나리오를 돌린다.

프로세스 안 시험은 ask_service.llm_port 를 대본 객체(ScriptedLlm)로 바꾼다. 원격 서버는 그렇게
바꿀 수 없으므로, 시험 DB 의 llm_setting 주소를 이 경로(`<재생 서버>/ollama`)로 돌려 5174 의
실제 어댑터(app/ai/llm.py)가 이 흉내를 부르게 한다. 임베딩은 건드리지 않는다(실임베딩 그대로).

- PUT  /ollama/_script  {"route": {...}|null, "text": "...", "fail": false}  대본 교체, 호출 수 0
- GET  /ollama/_calls   {"complete": n, "stream": n}
- POST /ollama/api/chat 어댑터 요청. stream=false 는 판정(route JSON), true 는 본문 조각(NDJSON)
- GET  /ollama/api/tags 모델 목록(대본 모델 하나)
- POST /ollama/api/generate 설정 저장 전 짧은 생성 확인

fail 이면 /api/chat 이 503 을 낸다(모델 서버 오류). 연결 거부와 달리 호출 수를 셀 수 있다.
어댑터는 둘 다 AI_UNAVAILABLE 로 읽는다.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response, StreamingResponse

MODEL = "scripted:remote"

router = APIRouter(prefix="/ollama")
_script: dict[str, Any] = {"route": None, "text": "", "fail": False}
_calls: dict[str, int] = {"complete": 0, "stream": 0}


@router.put("/_script")
def put_script(body: dict) -> dict:
    _script.update(
        route=body.get("route"), text=body.get("text") or "", fail=bool(body.get("fail"))
    )
    _calls.update(complete=0, stream=0)
    return {"ok": True}


@router.get("/_calls")
def get_calls() -> dict:
    return dict(_calls)


@router.get("/api/tags")
def tags() -> dict:
    model = {"name": MODEL, "model": MODEL, "details": {}, "capabilities": ["completion"]}
    return {"models": [model]}


@router.post("/api/generate")
def generate(body: dict) -> Response:
    """설정 저장 전 짧은 생성 확인(ollama_admin.measure_rate). fail 이면 503."""
    if _script["fail"]:
        return JSONResponse({"error": "scripted outage"}, status_code=503)
    return JSONResponse({"model": MODEL, "response": "확인", "done": True,
                         "eval_count": 8, "eval_duration": 400_000_000})


@router.post("/api/chat")
def chat(body: dict) -> Response:
    stream = bool(body.get("stream"))
    _calls["stream" if stream else "complete"] += 1
    if _script["fail"]:
        return JSONResponse({"error": "scripted outage"}, status_code=503)
    if not stream:
        route = _script["route"]
        text = json.dumps(route, ensure_ascii=False) if route else "모르겠다"
        return JSONResponse({"model": MODEL, "message": {"role": "assistant", "content": text},
                             "done": True, "done_reason": "stop"})
    raw = _script["text"]
    if body.get("format"):
        raw = json.dumps({"answer": raw}, ensure_ascii=False)

    def lines():
        for i in range(0, len(raw), 7):
            yield json.dumps({"model": MODEL, "message": {"content": raw[i:i + 7]}, "done": False},
                             ensure_ascii=False) + "\n"
        yield json.dumps({"model": MODEL, "message": {"content": ""}, "done": True,
                          "done_reason": "stop"}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")
