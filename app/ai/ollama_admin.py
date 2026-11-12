"""Ollama 서버 조회. 설치된 모델 목록과 생성 속도 실측 (ARC-011).

여기서는 아무것도 저장하지 않는다. 순수하게 서버에 묻고 파싱한 값을 돌려준다.
저장과 캐시는 model_settings 가 한다.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.common import errors

_TAGS_TIMEOUT = 5.0
# 적재 안 된 모델은 첫 응답까지 수십 초가 걸린다. 측정은 사람이 버튼을 눌러서만 한다.
_MEASURE_TIMEOUT = 180.0
_MEASURE_PROMPT = "1부터 40까지 세어라. 숫자만."
_MEASURE_PREDICT = 64


@dataclass(frozen=True)
class DiscoveredModel:
    name: str
    context_length: int  # 서버가 안 알려주면 0
    supports_tools: bool
    parameter_size: str | None
    quantization: str | None
    # 서버가 알려준 용도(completion·embedding·tools 등). 안 알려주면 None(모름)
    capabilities: tuple[str, ...] | None = None
    # 클라우드 위임 모델이면 생성이 나가는 외부 주소. 로컬 모델은 None
    remote_host: str | None = None


@dataclass(frozen=True)
class MeasuredRate:
    model: str
    # 서버가 생성 소요 시간을 주지 않으면(클라우드 위임 모델) 속도는 모른다. None
    tok_per_sec: float | None
    eval_count: int
    eval_duration_seconds: float | None


def list_models(base_url: str) -> list[DiscoveredModel]:
    """GET {base}/api/tags. 실패는 ApiError 로 올리고, 라우터가 상태 문구로 바꾼다."""
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with httpx.Client(timeout=_TAGS_TIMEOUT) as client:
            res = client.get(url)
    except httpx.RequestError as exc:
        raise errors.ApiError(503, "AI_UNAVAILABLE", f"LLM 서버에 닿지 못했습니다: {exc}") from exc
    if res.status_code >= 400:
        raise errors.ApiError(503, "AI_UNAVAILABLE", f"LLM 서버 오류 {res.status_code}")
    try:
        body = res.json()
    except ValueError as exc:
        raise errors.ApiError(503, "AI_UNAVAILABLE", "LLM 서버 응답을 읽지 못했습니다.") from exc
    return [parse_tag(item) for item in body.get("models") or [] if item.get("name")]


def parse_tag(item: dict[str, Any]) -> DiscoveredModel:
    """/api/tags 의 모델 한 건. context_length 와 capabilities 는 Ollama 0.6 이후에만 온다."""
    details = item.get("details") or {}
    raw = item.get("capabilities")
    capabilities = [str(c) for c in raw or []]
    return DiscoveredModel(
        name=str(item["name"]),
        context_length=_int(details.get("context_length")),
        supports_tools="tools" in capabilities,
        parameter_size=_str(details.get("parameter_size")),
        quantization=_str(details.get("quantization_level")),
        capabilities=tuple(capabilities) if raw is not None else None,
        remote_host=_str(item.get("remote_host")),
    )


def measure_rate(base_url: str, model: str) -> MeasuredRate:
    """POST {base}/api/generate 로 짧게 생성해 순수 생성 속도(tok/s)를 잰다.

    eval_count / eval_duration 이라 적재 시간과 프리필은 빠진다. think 를 끄는 이유는
    추론 모델이 여기서도 길게 생각하기 때문이다.
    """
    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": _MEASURE_PROMPT,
        "stream": False,
        "think": False,
        "options": {"num_predict": _MEASURE_PREDICT},
    }
    try:
        with httpx.Client(timeout=_MEASURE_TIMEOUT) as client:
            res = client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise errors.ApiError(503, "AI_UNAVAILABLE", f"LLM 서버에 닿지 못했습니다: {exc}") from exc
    if res.status_code >= 400:
        raise errors.ApiError(503, "AI_UNAVAILABLE", _ollama_error(res))
    return rate_from_generate(model, res.json())


def rate_from_generate(model: str, body: dict[str, Any]) -> MeasuredRate:
    eval_count = _int(body.get("eval_count"))
    duration_ns = _int(body.get("eval_duration"))
    if eval_count <= 0:
        raise errors.ApiError(503, "AI_UNAVAILABLE", "LLM 서버가 생성 통계를 주지 않았습니다.")
    if duration_ns <= 0:
        # 생성은 됐다(토큰 수가 있다). Ollama 클라우드 위임 모델은 소요 시간을 주지 않는다.
        # 속도를 지어내지 않고 비운다(DEF-045)
        return MeasuredRate(
            model=str(body.get("model") or model),
            tok_per_sec=None,
            eval_count=eval_count,
            eval_duration_seconds=None,
        )
    seconds = duration_ns / 1e9
    return MeasuredRate(
        model=str(body.get("model") or model),
        tok_per_sec=round(eval_count / seconds, 2),
        eval_count=eval_count,
        eval_duration_seconds=round(seconds, 3),
    )


def _ollama_error(res: httpx.Response) -> str:
    try:
        detail = res.json().get("error")
    except ValueError:
        detail = None
    return f"LLM 서버 오류 {res.status_code}" + (f": {detail}" if detail else "")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
