"""AI 포트 정의. 상위 계층은 이 프로토콜만 알고 어댑터를 모른다."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol


class EmbeddingPort(Protocol):
    """텍스트를 벡터로 만든다. 구현체는 Ollama 든 vLLM 이든 상관없다."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """입력 순서 그대로 벡터를 돌려준다. 길이가 다르면 계약 위반이다."""
        ...

    def dimension(self) -> int:
        """벡터 차원. doc_chunk.embedding 컬럼과 맞는지 기동 때 검사한다."""
        ...


@dataclass
class LlmResult:
    text: str
    model: str  # 어느 모델이 만든 문장인지 답변에 남긴다. 감사 가능성


class LlmPort(Protocol):
    """문장 생성. 이 포트가 만드는 것은 문장뿐이다. 수치는 시맨틱 레이어의 집계에서,
    화면은 템플릿 선택에서 나온다(절대 규칙 1·2). 계약이 그 방어선을 넘지 않게 좁다.

    파일럿 계약(complete·stream·callTool) 중 complete 와 stream 을 승계한다. stream 은
    AI 질의 화면이 답변을 조각 단위로 받기 위해 쓴다(SWFR.RAG.001). callTool 은 채택하지
    않는다. 데이터 조회는 LLM 도구호출이 아니라 시맨틱 레이어의 몫이다(ARC-003 4절).

    json_schema 를 주면 출력이 그 스키마의 JSON 객체 하나로 제한된다. 경량 모델은 자유
    출력이면 답 대신 생각을 늘어놓는데, 형식을 못 박으면 그 길로 못 샌다. 값의 뜻을
    해석하는 것은 호출부다. 포트는 형식만 안다.
    """

    def complete(
        self, system: str, user: str, *, json_schema: dict[str, Any] | None = None
    ) -> LlmResult:
        """system 지시와 user 입력으로 응답 문장을 만든다. 결정은 호출부가 한다."""
        ...

    def stream(
        self, system: str, user: str, *, json_schema: dict[str, Any] | None = None
    ) -> Iterator[str]:
        """같은 입력으로 문장을 조각내어 돌려준다. 이어 붙이면 complete 의 text 와 같은 뜻이다."""
        ...
