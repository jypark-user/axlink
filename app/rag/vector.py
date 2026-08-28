"""pgvector 텍스트 표현 변환.

pgvector 파이썬 바인딩을 의존성으로 들이지 않는다 — 필요한 건 리터럴 두 방향뿐이고,
SQL 에서는 항상 %s::vector 로 캐스트해 넘긴다.
"""


def to_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def from_literal(text: str) -> list[float]:
    inner = text.strip().strip("[]")
    if not inner:
        return []
    return [float(part) for part in inner.split(",")]
