"""LlmPort 구현체 2종과 선택 지점.

- OllamaLlm: 실제 모델. 폐쇄망 온프레미스 전제(QUR.RAG.001)라 로컬 엔드포인트만 부른다.
- FakeLlm:   같은 입력이면 항상 같은 문장. 모델 없이도 상위 흐름을 테스트한다.

구현체는 여기서만 고른다(SWFR.RAG.002). 상위 계층은 llm_port() 만 부른다.
모델이나 실행환경을 바꿔도 이 파일과 설정 밖은 변하지 않는다.

모델별 num_ctx·num_predict 는 DB(llm_model_cache)에서 온다(ARC-011). DB 에 행이 없거나
DB 에 닿지 못하면 환경변수 기본값으로 돈다. 설정 화면이 없어도 기동은 된다.
"""

import hashlib
import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

from app.ai.port import LlmPort, LlmResult
from app.common import errors
from app.config import settings

log = logging.getLogger(__name__)

_RETRY_DELAYS = (0.2, 0.4)  # 임베딩과 같은 규칙. 5xx 만 재시도, 불통은 즉시 실패

# 출력이 길이 제한에 걸리면 같은 요청을 이렇게 이어서 최대 3회 다시 묻는다.
MAX_LENGTH_RETRIES = 3
_CONTINUE_INSTRUCTION = (
    "출력이 길이 제한에 걸렸습니다. 같은 내용을 더 작게 나눠 다시 제안하세요. "
    "핵심만 짧게, 앞서 쓴 내용을 반복하지 마세요."
)


def stop_reason_of(body: dict[str, Any]) -> str:
    """Ollama done_reason → 내부 stop_reason.

    "length" 는 num_predict 에 걸려 잘린 것이다(max_tokens). 도구 호출이 있으면 tool_use.
    그 외는 모두 end_turn 이다. AX Link 는 도구 호출을 쓰지 않지만(ARC-003 4절) 모델이
    돌려주면 사실대로 남긴다.
    """
    if body.get("done_reason") == "length":
        return "max_tokens"
    if (body.get("message") or {}).get("tool_calls"):
        return "tool_use"
    return "end_turn"


class OllamaLlm:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        *,
        num_ctx: int | None = None,
        num_predict: int | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._timeout = timeout
        self._num_ctx = num_ctx
        self._num_predict = num_predict

    def _payload(
        self,
        messages: list[dict[str, str]],
        stream: bool,
        json_schema: dict[str, Any] | None,
    ) -> dict:
        # 기본 문맥(4096)은 근거 청크 5개를 못 담는다. 넘치면 Ollama 가 앞을 조용히 자른다.
        # num_ctx 가 비어 있으면 넣지 않고 모델 기본값에 맡긴다(ARC-011).
        options: dict[str, Any] = {}
        if self._num_ctx:
            options["num_ctx"] = self._num_ctx
        if self._num_predict:
            options["num_predict"] = self._num_predict
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": stream,
            # qwen3 계열의 생각 블록을 끈다. 켜 두면 4b 모델도 답 한 줄에 수십 초를 쓴다.
            "think": False,
            "options": options,
        }
        if json_schema is not None:
            # 09.14 실측: think 를 꺼도 qwen3:4b 는 영어로 생각을 늘어놓다 120초를 넘겼다.
            # 스키마로 출력을 묶으면 첫 토큰부터 JSON 이라 그 길로 못 새고 5초 안에 끝난다.
            payload["format"] = json_schema
            payload["options"]["temperature"] = 0
        return payload

    def complete(
        self, system: str, user: str, *, json_schema: dict[str, Any] | None = None
    ) -> LlmResult:
        """출력이 num_predict 에 걸려 잘리면(max_tokens) 잘린 답을 대화에 붙이고 더 작게
        나눠 답하라는 지시를 사용자 메시지로 실어 최대 3회 다시 묻는다. 그래도 잘리면
        요청 범위를 줄이라는 오류로 멈춘다. 잘린 답을 정상 답처럼 흘리지 않는다."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = self._call(messages, json_schema)
        for _ in range(MAX_LENGTH_RETRIES):
            if result.stop_reason != "max_tokens":
                return result
            messages.append({"role": "assistant", "content": result.text})
            messages.append({"role": "user", "content": _CONTINUE_INSTRUCTION})
            result = self._call(messages, json_schema)
        if result.stop_reason == "max_tokens":
            raise errors.ApiError(
                422,
                "AI_OUTPUT_TRUNCATED",
                "AI 출력이 길이 제한에 세 번 연속 걸렸습니다. 질문이나 요청 범위를 줄이세요.",
            )
        return result

    def _call(
        self, messages: list[dict[str, str]], json_schema: dict[str, Any] | None
    ) -> LlmResult:
        payload = self._payload(messages, stream=False, json_schema=json_schema)
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

        detail = f"LLM 서버 오류 {last.status_code}" if last is not None else "LLM 서버 오류"
        raise errors.ApiError(503, "AI_UNAVAILABLE", detail)

    def stream(
        self, system: str, user: str, *, json_schema: dict[str, Any] | None = None
    ) -> Iterator[str]:
        """Ollama 는 스트리밍을 NDJSON 으로 준다. 한 줄이 조각 하나다.

        재시도는 하지 않는다. 조각이 이미 화면에 나간 뒤 다시 시작하면 답이 두 번 붙는다.
        길이 제한에 걸린 것은 마지막 조각의 done_reason 으로 알 수 있으니 로그에만 남긴다.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload = self._payload(messages, stream=True, json_schema=json_schema)
        try:
            with (
                httpx.Client(timeout=self._timeout) as client,
                client.stream("POST", self._url, json=payload) as res,
            ):
                if res.status_code >= 400:
                    raise errors.ApiError(503, "AI_UNAVAILABLE", f"LLM 서버 오류 {res.status_code}")
                for line in res.iter_lines():
                    if not line.strip():
                        continue
                    body = json.loads(line)
                    if body.get("error"):
                        raise errors.ApiError(503, "AI_UNAVAILABLE", str(body["error"]))
                    piece = (body.get("message") or {}).get("content") or ""
                    if piece:
                        yield piece
                    if body.get("done"):
                        self._log(body, stream=True)
                        return
        except httpx.RequestError as exc:
            raise errors.ApiError(503, "AI_UNAVAILABLE", f"LLM 에 닿지 못했습니다: {exc}") from exc

    def _result(self, body: dict) -> LlmResult:
        self._log(body, stream=False)
        text = ((body.get("message") or {}).get("content") or "").strip()
        stop_reason = stop_reason_of(body)
        if not text and stop_reason != "max_tokens":
            # 빈 응답을 그대로 흘리면 상위가 "근거 부족"과 구분하지 못한다.
            raise errors.ApiError(503, "AI_UNAVAILABLE", "LLM 응답이 비어 있습니다.")
        return LlmResult(
            text=text,
            model=body.get("model") or self._model,
            stop_reason=stop_reason,
            prompt_tokens=int(body.get("prompt_eval_count") or 0),
            output_tokens=int(body.get("eval_count") or 0),
        )

    def _log(self, body: dict, *, stream: bool) -> None:
        log.info(
            "llm %s model=%s prompt_tokens=%s output_tokens=%s stop=%s",
            "stream" if stream else "complete",
            body.get("model") or self._model,
            body.get("prompt_eval_count"),
            body.get("eval_count"),
            stop_reason_of(body),
        )


class FakeLlm:
    """입력 해시를 박은 고정 문장. 결정성이 핵심이다. 같은 입력은 항상 같은 답이라야
    상위 흐름(프롬프트 조립·응답 처리) 테스트가 성립한다."""

    def complete(
        self, system: str, user: str, *, json_schema: dict[str, Any] | None = None
    ) -> LlmResult:
        digest = hashlib.sha256(f"{system}\x1f{user}".encode()).hexdigest()[:12]
        return LlmResult(text=f"[fake:{digest}] {user[:80]}", model="fake")

    def stream(
        self, system: str, user: str, *, json_schema: dict[str, Any] | None = None
    ) -> Iterator[str]:
        """complete 와 같은 문장을 잘게 쪼개 준다. 스키마를 주면 첫 필수 속성에 담은
        JSON 을 쪼개서, 조각 경계가 이스케이프 한가운데 걸리는 경우까지 시험된다."""
        text = self.complete(system, user).text
        if json_schema is not None:
            text = json.dumps({first_property(json_schema): text}, ensure_ascii=False)
        for i in range(0, len(text), 7):
            yield text[i : i + 7]


def first_property(schema: dict[str, Any]) -> str:
    keys = list(schema.get("required") or schema.get("properties") or ["text"])
    return str(keys[0])


def llm_port() -> LlmPort:
    """구현체 선택 단일 지점. 여기 말고 다른 곳에서 어댑터를 직접 만들지 않는다."""
    if settings.llm_provider == "fake":
        return FakeLlm()
    cfg = _runtime_config()
    return OllamaLlm(
        cfg.base_url,
        cfg.model,
        settings.llm_timeout,
        num_ctx=cfg.num_ctx,
        num_predict=cfg.num_predict,
    )


def _runtime_config():
    """DB 의 활성 설정. DB 가 없거나 표가 아직 없으면 환경변수로 돈다."""
    from app.ai import model_settings  # 순환 import 회피 (model_settings → config 만 본다)
    from app.db import tx

    try:
        with tx() as cur:
            return model_settings.runtime_config(cur)
    except Exception as exc:  # noqa: BLE001 — 설정을 못 읽는 것이 답변을 막아선 안 된다
        log.warning("llm 설정을 DB 에서 읽지 못해 환경변수로 돕니다: %s", exc)
        return model_settings.RuntimeConfig(
            settings.ollama_base_url,
            settings.llm_model,
            settings.llm_num_ctx,
            model_settings.DEFAULT_NUM_PREDICT,
        )
