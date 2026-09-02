"""AI 포트 정의. 상위 계층은 이 프로토콜만 알고 어댑터를 모른다."""

from typing import Protocol


class EmbeddingPort(Protocol):
    """텍스트를 벡터로 만든다. 구현체는 Ollama 든 vLLM 이든 상관없다."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """입력 순서 그대로 벡터를 돌려준다. 길이가 다르면 계약 위반이다."""
        ...

    def dimension(self) -> int:
        """벡터 차원. doc_chunk.embedding 컬럼과 맞는지 기동 때 검사한다."""
        ...
