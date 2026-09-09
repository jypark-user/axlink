"""LlmPort 구현체 2종과 선택 지점.

- OllamaLlm: 실제 모델. 폐쇄망 온프레미스 전제(QUR.RAG.001)라 로컬 엔드포인트만 부른다.
- FakeLlm:   같은 입력이면 항상 같은 문장. 모델 없이도 상위 흐름을 테스트한다.

구현체는 여기서만 고른다(SWFR.RAG.002). 상위 계층은 llm_port() 만 부른다 —
모델이나 실행환경을 바꿔도 이 파일과 설정 밖은 변하지 않는다.
"""

import hashlib
import time

import httpx

from app.ai.port import LlmPort, LlmResult
from app.common import errors
from app.config import settings

_RETRY_DELAYS = (0.2, 0.4)  # 임베딩과 같은 규칙 — 5xx 만 재시도, 불통은 즉시 실패


class OllamaLlm:
    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._timeout = timeout

    def complete(self, system: str, user: str) -> LlmResult:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        last: httpx.Response | None = None
        with httpx.Client(timeout=self._timeout) as client:
            for attempt in range(len(_RETRY_DELAYS) + 1):
                try:
                    res = client.post(self._url, json=payload)
                except httpx.RequestError as exc:
                    raise errors.ApiError(
                        503, "AI_UNAVAILABLE", f"LLM 에 닿지 못했습니다: {exc}"
                    ) from exc
                if res.status_code < 400:
                    return self._result(res.json())
                last = res
                if res.status_code < 500 or attempt == len(_RETRY_DELAYS):
                    break
                time.sleep(_RETRY_DELAYS[attempt])

        detail = f"Ollama 오류 {last.status_code}" if last is not None else "Ollama 오류"
        raise errors.ApiError(503, "AI_UNAVAILABLE", detail)

    def _result(self, body: dict) -> LlmResult:
        text = ((body.get("message") or {}).get("content") or "").strip()
        if not text:
            # 빈 응답을 그대로 흘리면 상위가 "근거 부족"과 구분하지 못한다.
            raise errors.ApiError(503, "AI_UNAVAILABLE", "LLM 응답이 비어 있습니다.")
        return LlmResult(text=text, model=body.get("model") or self._model)


class FakeLlm:
    """입력 해시를 박은 고정 문장. 결정성이 핵심이다 — 같은 입력은 항상 같은 답이라야
    상위 흐름(프롬프트 조립·응답 처리) 테스트가 성립한다."""

    def complete(self, system: str, user: str) -> LlmResult:
        digest = hashlib.sha256(f"{system}\x1f{user}".encode()).hexdigest()[:12]
        return LlmResult(text=f"[fake:{digest}] {user[:80]}", model="fake")


def llm_port() -> LlmPort:
    """구현체 선택 단일 지점. 여기 말고 다른 곳에서 어댑터를 직접 만들지 않는다."""
    if settings.llm_provider == "fake":
        return FakeLlm()
    return OllamaLlm(settings.ollama_base_url, settings.llm_model, settings.llm_timeout)
