#!/usr/bin/env python3
"""세션 토큰이 소진됐을 때 Ollama qwen3.5 로 남은 작업을 이어서 진행한다.

    python3 tools/ollama_continue.py --task "AuthService 를 구현한다"
    python3 tools/ollama_continue.py --demo

표준 라이브러리만 사용한다. 파일 수정은 tool calling 으로만 이뤄지고,
쓰기 전에 프로젝트 경로 안인지 검증한다.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL_CHAT", "qwen3.5:cloud")
MAX_STEPS = 40
MAX_READ_BYTES = 60_000

SYSTEM_PROMPT = """\
너는 AX-Link 프로젝트를 이어서 구현하는 시니어 개발자다. 한국어로 답한다.

## 반드시 지킬 규칙
- DTO 는 도메인별 단일 `XxxDtos.java` 에 `public final class` + private 생성자 + 중첩 record.
- import 순서: java.* → jakarta.* → kr.co.axlink.* → 서드파티. 와일드카드 금지.
- 들여쓰기 2칸, 한 줄 100자, 파일 하나에 최상위 public 클래스 하나.
- **코드에 주석을 쓰지 않는다.** 생성자 주입만. Lombok·필드주입·@Autowired 금지.
- JPA 금지, Spring JdbcClient 단독. enum 은 전 계층 CONSTANT_CASE.
- AI 어댑터는 Ollama + Fake 2벌만. Ollama 의 `format` 파라미터는 무시되므로
  구조화 출력은 tool calling 으로 얻는다. 스트리밍은 SSE 가 아니라 NDJSON 이다.
- 프론트: named export 만, `@/` alias, any 금지, 모든 UI 는 shadcn/ui,
  목업 데이터 파일 금지, 위젯 렌더러 맵 키는 CONSTANT_CASE.

## 작업 방식
- 추측하지 말고 `read_file`·`list_files`·`search` 로 먼저 확인한다.
- 한 번의 write_file 에 400줄 이상 담지 않는다.
- 코드를 고친 뒤에는 반드시 `run_check` 로 컴파일이나 테스트를 돌려 확인한다.
- 확인 없이 "완료했다"고 말하지 않는다. 실패는 실패로 보고한다.
- 작업이 끝나면 도구를 더 호출하지 말고 최종 요약을 텍스트로 답한다.
"""

ALLOWED_CHECKS = {
    "compile": ["./gradlew", "compileJava", "--console=plain"],
    "build": ["./gradlew", "build", "-x", "test", "--console=plain"],
    "test": ["./gradlew", "test", "--console=plain"],
    "frontend-build": ["npm", "run", "build"],
    "frontend-test": ["npm", "test"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "프로젝트 안의 파일을 읽는다. 경로는 프로젝트 루트 기준 상대경로.",
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "디렉터리의 파일 목록을 얻는다. 경로는 프로젝트 루트 기준 상대경로.",
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "프로젝트 안에서 문자열을 검색한다(grep).",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "파일을 쓴다(덮어쓰기). 경로는 프로젝트 루트 기준 상대경로.",
            "parameters": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_check",
            "description": "빌드·테스트를 실행해 결과를 확인한다.",
            "parameters": {
                "type": "object",
                "required": ["check"],
                "properties": {
                    "check": {
                        "type": "string",
                        "enum": list(ALLOWED_CHECKS),
                    }
                },
            },
        },
    },
]


def safe_path(relative):
    target = os.path.realpath(os.path.join(PROJECT_ROOT, relative))
    root = os.path.realpath(PROJECT_ROOT)
    if target != root and not target.startswith(root + os.sep):
        raise ValueError(f"프로젝트 밖 경로 거부: {relative}")
    return target


def tool_read_file(path, **_):
    target = safe_path(path)
    if not os.path.isfile(target):
        return f"없는 파일: {path}"
    with open(target, "r", encoding="utf-8", errors="replace") as fh:
        body = fh.read(MAX_READ_BYTES + 1)
    if len(body) > MAX_READ_BYTES:
        return body[:MAX_READ_BYTES] + f"\n... (잘림, {path})"
    return body


def tool_list_files(path, pattern=None, **_):
    target = safe_path(path)
    if not os.path.isdir(target):
        return f"없는 디렉터리: {path}"
    found = []
    for base, _dirs, files in os.walk(target):
        if "node_modules" in base or "/build/" in base or "/.git" in base:
            continue
        for name in files:
            if pattern and pattern not in name:
                continue
            found.append(os.path.relpath(os.path.join(base, name), PROJECT_ROOT))
    found.sort()
    if len(found) > 300:
        return "\n".join(found[:300]) + f"\n... ({len(found)}개 중 300개)"
    return "\n".join(found) or "(없음)"


def tool_search(query, path=".", **_):
    target = safe_path(path)
    result = subprocess.run(
        ["grep", "-rn", "--exclude-dir=node_modules", "--exclude-dir=build",
         "--exclude-dir=.git", query, target],
        capture_output=True, text=True, timeout=60,
    )
    out = result.stdout.replace(PROJECT_ROOT + os.sep, "")
    lines = out.split("\n")
    if len(lines) > 200:
        return "\n".join(lines[:200]) + f"\n... ({len(lines)}줄 중 200줄)"
    return out or "(검색 결과 없음)"


def tool_write_file(path, content, **_):
    target = safe_path(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"작성 완료: {path} ({len(content.splitlines())}줄)"


def tool_run_check(check, **_):
    if check not in ALLOWED_CHECKS:
        return f"허용되지 않은 검사: {check}"
    cwd = os.path.join(PROJECT_ROOT, "frontend" if check.startswith("frontend") else "backend")
    try:
        result = subprocess.run(
            ALLOWED_CHECKS[check], cwd=cwd, capture_output=True, text=True, timeout=900
        )
    except subprocess.TimeoutExpired:
        return f"{check}: 시간 초과"
    tail = (result.stdout + result.stderr).strip().split("\n")[-40:]
    status = "성공" if result.returncode == 0 else f"실패(exit {result.returncode})"
    return f"{check}: {status}\n" + "\n".join(tail)


HANDLERS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "search": tool_search,
    "write_file": tool_write_file,
    "run_check": tool_run_check,
}


def call_ollama(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "think": False,
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read())


def run(task):
    handoff = ""
    handoff_path = os.path.join(PROJECT_ROOT, "docs", "HANDOFF.md")
    if os.path.isfile(handoff_path):
        with open(handoff_path, "r", encoding="utf-8") as fh:
            handoff = fh.read()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"# 인수인계 문서\n\n{handoff}\n\n# 이번 작업\n\n{task}"},
    ]

    for step in range(1, MAX_STEPS + 1):
        try:
            response = call_ollama(messages)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"[{step}] Ollama 호출 실패: {exc}", file=sys.stderr)
            return 1

        message = response.get("message") or {}
        messages.append(message)
        calls = message.get("tool_calls") or []

        if not calls:
            print(f"\n=== 완료 ({step}단계) ===")
            print(message.get("content", "").strip() or "(응답 없음)")
            return 0

        for call in calls:
            function = call.get("function") or {}
            name = function.get("name")
            args = function.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            handler = HANDLERS.get(name)
            if handler is None:
                result = f"알 수 없는 도구: {name}"
            else:
                try:
                    result = handler(**args)
                except Exception as exc:
                    result = f"{name} 실패: {exc}"
            preview = str(result).split("\n")[0][:100]
            print(f"[{step}] {name}({str(args)[:70]}) -> {preview}")
            messages.append({"role": "tool", "content": str(result)})

    print(f"\n{MAX_STEPS}단계 상한 도달. 중단한다.", file=sys.stderr)
    return 1


def demo():
    assert os.path.isdir(PROJECT_ROOT)
    assert safe_path("backend").startswith(os.path.realpath(PROJECT_ROOT))
    for escape in ("../etc", "/etc/passwd", "backend/../../.."):
        try:
            safe_path(escape)
        except ValueError:
            continue
        raise AssertionError(f"경로 탈출이 막히지 않았다: {escape}")
    assert set(HANDLERS) == {t["function"]["name"] for t in TOOLS}
    assert tool_run_check("rm -rf /").startswith("허용되지 않은 검사")
    listing = tool_list_files("tools")
    assert "tools/ollama_continue.py" in listing
    print("demo ok: 경로탈출 차단, 도구 정의 일치, 검사 화이트리스트, 목록 조회")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="이어서 진행할 작업 설명")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.demo:
        demo()
    elif args.task:
        sys.exit(run(args.task))
    else:
        parser.error("--task 또는 --demo 가 필요하다")
