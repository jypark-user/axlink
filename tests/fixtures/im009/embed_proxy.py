"""임베딩 중계(5174 전용 장애 주입). 재생 서버에 붙는다.

5174 API 의 임베딩 주소(AXLINK_EMBEDDING_BASE_URL)를 시험하는 동안만 이 중계로 돌린다.
평소에는 실제 임베딩 서버로 그대로 넘기고, 시험이 스위치를 바꾸면 장애를 낸다. 공유 모델
서버(axlink-ollama)를 멈추지 않고 5174 의 색인 경로만 끊는다.

- pass: 그대로 넘긴다
- down: 503 을 낸다. 어댑터는 재시도 뒤 AI_UNAVAILABLE 로 읽는다(색인 실패, UC-070-S05)
- hold: 스위치가 바뀔 때까지 응답하지 않는다. 처리 중인 작업을 붙잡아 두고 그 사이 API 를
  다시 시작한다(UC-070-S07). 어댑터 시간 제한(120초)보다 오래 붙잡지 않게 시험이 서두른다

조작: GET/PUT /_replay/embed  {"mode": "pass|down|hold"} → {"mode", "calls", "waiting"}
중계: POST /embed-proxy/api/embed (넘기는 곳: REPLAY_EMBED_UPSTREAM, 기본 http://ollama:11434)
"""

from __future__ import annotations

import asyncio
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

MODES = ("pass", "down", "hold")
HOLD_LIMIT_S = 600.0


def mount(app: FastAPI, upstream: str | None = None) -> None:
    base = (upstream or os.environ.get("REPLAY_EMBED_UPSTREAM") or "http://ollama:11434").rstrip("/")
    state = {"mode": "pass", "calls": 0, "waiting": 0}

    @app.get("/_replay/embed")
    def get_embed() -> dict:
        return dict(state, upstream=base)

    @app.put("/_replay/embed")
    def put_embed(body: dict) -> Response:
        mode = body.get("mode")
        if mode not in MODES:
            return JSONResponse({"message": f"mode 는 {MODES} 중 하나"}, status_code=400)
        state["mode"] = mode
        if body.get("reset"):
            state["calls"] = 0
        return JSONResponse(dict(state))

    @app.post("/embed-proxy/api/embed")
    async def embed(request: Request) -> Response:
        state["calls"] += 1
        if state["mode"] == "hold":
            state["waiting"] += 1
            try:
                waited = 0.0
                while state["mode"] == "hold" and waited < HOLD_LIMIT_S:
                    await asyncio.sleep(0.2)
                    waited += 0.2
            finally:
                state["waiting"] -= 1
        if state["mode"] == "down":
            return JSONResponse({"error": "임베딩 서버 중단(시험 주입)"}, status_code=503)
        async with httpx.AsyncClient(timeout=120) as client:
            res = await client.post(
                base + "/api/embed", content=await request.body(),
                headers={"content-type": "application/json"},
            )
        return Response(
            res.content, status_code=res.status_code,
            media_type=res.headers.get("content-type", "application/json"),
        )
