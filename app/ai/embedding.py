"""EmbeddingPort 구현체 2종과 선택 지점.

- OllamaEmbedding: 실제 모델(bge-m3). 폐쇄망 온프레미스 전제라 로컬 엔드포인트만 부른다.
- FakeEmbedding:   같은 입력이면 항상 같은 벡터. 모델 없이도 색인 경로를 테스트한다.

구현체는 여기서만 고른다(SWFR.RAG.002). 상위 계층은 embedding_port() 만 부른다.
"""

import hashlib
import math
import random
import time

import httpx

from app.ai.port import EmbeddingPort
from app.common import errors
from app.config import settings

_RETRY_DELAYS = (0.2, 0.4)  # 5xx 만 재시도한다. 닿지 못하는 건 즉시 실패시킨다.


class OllamaEmbedding:
    def __init__(self, base_url: str, model: str, dim: int, batch: int, timeout: float) -> None:
        self._url = base_url.rstrip("/") + "/api/embed"
        self._model = model
        self._dim = dim
        self._batch = batch
        self._timeout = timeout

    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        with httpx.Client(timeout=self._timeout) as client:
            for start in range(0, len(texts), self._batch):
                out.extend(self._embed_batch(client, texts[start : start + self._batch]))
        return out

    def _embed_batch(self, client: httpx.Client, batch: list[str]) -> list[list[float]]:
        payload = {"model": self._model, "input": batch}
        last: httpx.Response | None = None
        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                res = client.post(self._url, json=payload)
            except httpx.RequestError as exc:
                raise errors.ApiError(
                    503, "AI_UNAVAILABLE", f"임베딩 모델에 닿지 못했습니다: {exc}"
                ) from exc
            if res.status_code < 400:
                return self._vectors(res.json(), len(batch))
            last = res
            if res.status_code < 500 or attempt == len(_RETRY_DELAYS):
                break
            time.sleep(_RETRY_DELAYS[attempt])

        detail = f"Ollama 오류 {last.status_code}" if last is not None else "Ollama 오류"
        raise errors.ApiError(503, "AI_UNAVAILABLE", detail)

    def _vectors(self, body: dict, expected: int) -> list[list[float]]:
        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != expected:
            raise errors.ApiError(
                503, "AI_UNAVAILABLE", f"임베딩 응답 개수가 맞지 않습니다({expected}건 요청)"
            )
        for vec in vectors:
            if len(vec) != self._dim:
                raise errors.ApiError(
                    503,
                    "AI_UNAVAILABLE",
                    f"임베딩 차원이 {self._dim} 이 아닙니다: {len(vec)} — 모델 설정을 확인하세요.",
                )
        return [[float(x) for x in vec] for vec in vectors]


class FakeEmbedding:
    """SHA-256 앞 8바이트를 시드로 정규분포 벡터를 만들고 L2 정규화한다.

    결정성이 핵심이다 — 같은 텍스트는 항상 같은 벡터라야 재색인 테스트가 성립한다.
    """

    def __init__(self, dim: int) -> None:
        self._dim = dim

    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        vec = [rng.gauss(0.0, 1.0) for _ in range(self._dim)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def embedding_port() -> EmbeddingPort:
    """구현체 선택 단일 지점. 여기 말고 다른 곳에서 어댑터를 직접 만들지 않는다."""
    if settings.embedding_provider == "fake":
        return FakeEmbedding(settings.embedding_dimension)
    return OllamaEmbedding(
        settings.ollama_base_url,
        settings.embedding_model,
        settings.embedding_dimension,
        settings.embedding_batch,
        settings.embedding_timeout,
    )
