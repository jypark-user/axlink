"""커넥터 읽기 전용 상시 검증 (QUR.CON.001 · ARC-004 ①).

공식검토의 결론("어댑터는 GET 만 쓴다")을 시험으로 굳힌다. 사람 검토는 한 번이고
코드는 계속 바뀌므로, 어댑터가 추가·수정될 때마다 여기서 자동으로 다시 검토된다.
"""

import re
from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parent.parent / "app" / "integration" / "adapter"

# httpx 의 쓰기 계열 호출. request(는 메서드를 변수로 숨길 수 있어 함께 금지한다.
_WRITE_CALL = re.compile(r"\.(post|put|patch|delete|request)\s*\(")


def test_어댑터는_원천에_쓰지_않는다():
    offenders = []
    for src in sorted(ADAPTER_DIR.glob("*.py")):
        for no, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            if _WRITE_CALL.search(line):
                offenders.append(f"{src.name}:{no} {line.strip()}")
    assert not offenders, "어댑터에 쓰기 호출이 있다 — 읽기 전용(QUR.CON.001) 위반:\n" + "\n".join(
        offenders
    )


def test_어댑터가_실제로_존재한다():
    """검사 대상이 비면 시험이 헛돈다 — 디렉토리 이동을 여기서 잡는다."""
    assert any(
        f.name.endswith("_connector.py") for f in ADAPTER_DIR.glob("*.py")
    ), f"{ADAPTER_DIR} 에 어댑터가 없다"
