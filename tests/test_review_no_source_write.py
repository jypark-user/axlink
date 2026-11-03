"""확인 요청·조치 보고는 AX Link 안에만 남는다 (QUR.WEB.003).

요청·보고·활동 기록 코드가 원천 도구로 가는 길(커넥터 어댑터·포트·동기화, HTTP 클라이언트)을
직접이든 다른 모듈을 거쳐서든 가져오지 않는지 본다. 원천 호출은 어댑터에만 있고 어댑터는 GET 만
쓴다(test_readonly_guard). 여기서는 요청·보고 쪽이 그 어댑터에도 닿지 않는다는 것을 굳힌다.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"

# 원천 도구에 닿는 모듈. 이 가운데 하나라도 import 그래프에 들어오면 실패한다
_FORBIDDEN = (
    "httpx",
    "requests",
    "urllib.request",
    "app.integration.adapter",
    "app.integration.port",
    "app.integration.sync",
    "app.integration.service",
)
_STARTS = ("app.review", "app.activity")


def _module_file(name: str) -> Path | None:
    base = ROOT / Path(*name.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    return None


def _imports(name: str, path: Path) -> set[str]:
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                mod = f"{base}.{node.module}" if node.module else base
            else:
                mod = node.module or ""
            found.add(mod)
            # from app.x import y 에서 y 가 모듈일 수 있다
            found.update(f"{mod}.{a.name}" for a in node.names)
    return found


def _graph() -> dict[str, set[str]]:
    """app.review·app.activity 에서 닿는 app 모듈과 그 import 를 모은다."""
    todo = [
        ".".join(p.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")
        for start in _STARTS
        for p in (ROOT / Path(*start.split("."))).rglob("*.py")
    ]
    seen: dict[str, set[str]] = {}
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        path = _module_file(name)
        if path is None:
            continue
        seen[name] = _imports(name, path)
        todo.extend(m for m in seen[name] if m.startswith("app.") and m not in seen)
    return seen


def _hits(mod: str) -> bool:
    return any(mod == f or mod.startswith(f + ".") for f in _FORBIDDEN)


def test_요청과_보고는_원천_도구로_가는_모듈을_가져오지_않는다():
    graph = _graph()
    offenders = sorted(
        f"{name} → {mod}" for name, mods in graph.items() for mod in mods if _hits(mod)
    )
    assert not offenders, "요청·보고 코드가 원천 도구에 닿는다(QUR.WEB.003):\n" + "\n".join(
        offenders
    )


def test_검사_대상이_비지_않는다():
    """모듈을 옮겨 검사가 헛돌지 않게 한다."""
    graph = _graph()
    assert "app.review.service" in graph and "app.activity.service" in graph
    # 집계 화면을 거쳐 연계 저장소(DB 읽기)까지는 따라간다
    assert any(name.startswith("app.dashboard") for name in graph)
