#!/usr/bin/env python3
"""AX-Link 구축 진행상황 대시보드. 표준 라이브러리만 사용한다.

    python3 tools/progress_dashboard.py [--port 8765]
    python3 tools/progress_dashboard.py --demo
"""

import argparse
import glob
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_PROJECTS = os.path.expanduser(
    "~/.claude/projects/-Users-userinsight-design-Documents-SourceCode-ax-link"
)
ACTIVE_WINDOW_SECONDS = 90
API_DESIGN_DOC = "docs/design/02-logical-api.md"

BE = "backend/src/main/java/kr/co/axlink"
FE = "frontend/src"


def check(label, pattern, need=1):
    return {"label": label, "glob": pattern, "need": need}


STAGES = [
    {
        "id": "design",
        "name": "설계",
        "checks": [
            check("설계 문서", "docs/design/*.md", 9),
            check("DB 마이그레이션", "backend/src/main/resources/db/migration/V*.sql", 2),
        ],
    },
    {
        "id": "scaffold",
        "name": "스캐폴드",
        "checks": [
            check("Gradle 빌드", "backend/build.gradle"),
            check("Gradle 래퍼", "backend/gradlew"),
            check("애플리케이션 설정", "backend/src/main/resources/application*.yml"),
            check("Vite 설정", "frontend/vite.config.ts"),
            check("프론트 엔트리", f"{FE}/main.tsx"),
        ],
    },
    {
        "id": "backend-core",
        "name": "백엔드 도메인",
        "checks": [
            check("컨트롤러", f"{BE}/**/web/*Controller.java", 20),
            check("웹 DTO", f"{BE}/**/web/*.java", 40),
            check("서비스", f"{BE}/**/service/*.java", 20),
            check("리포지토리", f"{BE}/**/repository/*.java", 15),
        ],
    },
    {
        "id": "backend-auth",
        "name": "백엔드 인증",
        "checks": [
            check("보안 필터·JWT", f"{BE}/auth/security/*.java", 5),
            check("인증 서비스", f"{BE}/auth/service/AuthService.java"),
            check("인증 DTO", f"{BE}/auth/web/AuthDtos.java"),
            check("인증 컨트롤러", f"{BE}/auth/web/AuthController.java"),
        ],
    },
    {
        "id": "backend-ai",
        "name": "AI 어댑터",
        "checks": [
            check("포트", f"{BE}/ai/port/*.java", 8),
            check("Ollama 어댑터", f"{BE}/ai/adapter/ollama/*.java", 4),
            check("Fake 어댑터", f"{BE}/ai/adapter/fake/*.java", 2),
            check("RAG·시맨틱", f"{BE}/{{rag,semantic}}/**/*.java", 10),
        ],
    },
    {
        "id": "frontend-base",
        "name": "프론트 기반",
        "checks": [
            check("shadcn/ui", f"{FE}/components/ui/*.tsx", 17),
            check("레이아웃", f"{FE}/components/layout/*.tsx", 6),
            check("API 클라이언트", f"{FE}/api/*.ts", 5),
            check("라우팅", f"{FE}/routes.tsx"),
            check("인증 화면", f"{FE}/features/auth/*.tsx", 4),
        ],
    },
    {
        "id": "frontend-screens",
        "name": "프론트 화면",
        "checks": [
            check("프로젝트", f"{FE}/features/projects/*.tsx", 3),
            check("연동·수집", f"{FE}/features/{{connections,collection}}/*.tsx", 4),
            check("문서·산출물", f"{FE}/features/{{documents,deliverables}}/*.tsx", 4),
            check("추적·변경·종료", f"{FE}/features/{{traceability,changes,closure}}/*.tsx", 4),
            check("대시보드", f"{FE}/features/dashboard/*.tsx", 4),
            check("위젯 렌더러", f"{FE}/features/widgets/renderers/*.tsx", 7),
            check("Q&A", f"{FE}/features/ask/*.tsx", 3),
        ],
    },
    {
        "id": "test",
        "name": "테스트",
        "checks": [
            check("백엔드 테스트", "backend/src/test/java/**/*Test.java", 12),
            check("프론트 테스트", f"{FE}/**/*.test.tsx", 6),
        ],
    },
    {
        "id": "package",
        "name": "패키징",
        "checks": [
            check("실행 JAR", "backend/build/libs/*.jar", 1),
            check("프론트 번들", "frontend/dist/index.html"),
        ],
    },
]

CODE_GROUPS = [
    ("백엔드 Java", f"{BE}/**/*.java"),
    ("백엔드 테스트", "backend/src/test/java/**/*.java"),
    ("DB 마이그레이션", "backend/src/main/resources/db/migration/*.sql"),
    ("프론트 컴포넌트", f"{FE}/**/*.tsx"),
    ("프론트 모듈", f"{FE}/**/*.ts"),
    ("프론트 테스트", f"{FE}/**/*.test.*"),
]

TASK_RE = re.compile(r"#\s*당신의 임무\s*:\s*(.+)")
API_ROW_RE = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]+)`")
CLASS_MAP_RE = re.compile(r'@RequestMapping\(\s*(?:value\s*=\s*)?"([^"]*)"')
METHOD_MAP_RE = re.compile(
    r'@(Get|Post|Put|Patch|Delete)Mapping\s*(?:\(\s*(?:value\s*=\s*)?"([^"]*)")?'
)


def expand(pattern):
    """glob + 중괄호 대안 `{a,b}` 지원."""
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return glob.glob(os.path.join(PROJECT_ROOT, pattern), recursive=True)
    found = []
    for option in match.group(1).split(","):
        found.extend(expand(pattern[: match.start()] + option + pattern[match.end():]))
    return found


def newest_mtime(paths):
    stamps = []
    for path in paths:
        try:
            stamps.append(os.path.getmtime(path))
        except OSError:
            continue
    return max(stamps) if stamps else None


def total_size(paths):
    size = 0
    for path in paths:
        try:
            size += os.path.getsize(path)
        except OSError:
            continue
    return size


def read_jsonl(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        return None


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def summarize_agent(path):
    title = None
    started = None
    last_activity = None
    tool_calls = 0
    last_tool = None
    final_text = None

    for entry in read_jsonl(path):
        stamp = parse_timestamp(entry.get("timestamp"))
        if stamp:
            started = stamp if started is None else min(started, stamp)
            last_activity = stamp if last_activity is None else max(last_activity, stamp)

        message = entry.get("message") or {}
        content = message.get("content")

        if entry.get("type") == "user" and title is None:
            match = TASK_RE.search(text_of(content))
            if match:
                title = match.group(1).strip()

        if entry.get("type") == "assistant" and isinstance(content, list):
            produced_text = None
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    tool_calls += 1
                    last_tool = block.get("name")
                elif block.get("type") == "text" and block.get("text", "").strip():
                    produced_text = block["text"].strip()
            if produced_text:
                final_text = produced_text

    try:
        last_activity = max(last_activity or 0, os.path.getmtime(path))
    except OSError:
        pass

    idle = time.time() - last_activity if last_activity else None

    return {
        "id": os.path.basename(path).replace("agent-", "").replace(".jsonl", ""),
        "title": title or "(작업명 미확인)",
        "started": started,
        "lastActivity": last_activity,
        "toolCalls": tool_calls,
        "lastTool": last_tool,
        "running": idle is not None and idle < ACTIVE_WINDOW_SECONDS,
        "result": (final_text or "")[:400],
    }


def collect_workflows():
    pattern = os.path.join(CLAUDE_PROJECTS, "*", "subagents", "workflows", "wf_*")
    runs = []
    for directory in sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True):
        agents = [
            summarize_agent(p)
            for p in sorted(glob.glob(os.path.join(directory, "agent-*.jsonl")))
        ]
        if not agents:
            continue
        agents.sort(key=lambda a: a["started"] or 0)
        runs.append(
            {
                "runId": os.path.basename(directory),
                "modified": os.path.getmtime(directory),
                "agents": agents,
                "running": any(a["running"] for a in agents),
            }
        )
    return runs[:4]


def collect_stages():
    stages = []
    for stage in STAGES:
        checks = []
        for spec in stage["checks"]:
            matches = expand(spec["glob"])
            checks.append(
                {
                    "label": spec["label"],
                    "glob": spec["glob"],
                    "matched": len(matches),
                    "need": spec["need"],
                    "ok": len(matches) >= spec["need"],
                    "size": total_size(matches),
                    "modified": newest_mtime(matches),
                }
            )
        need = sum(c["need"] for c in checks)
        have = sum(min(c["matched"], c["need"]) for c in checks)
        done = sum(1 for c in checks if c["ok"])
        state = "done" if done == len(checks) else "active" if have else "pending"
        stages.append(
            {
                "id": stage["id"],
                "name": stage["name"],
                "state": state,
                "done": done,
                "total": len(checks),
                "ratio": have / need if need else 0,
                "checks": checks,
            }
        )
    return stages


def collect_code_counts():
    counts = []
    for label, pattern in CODE_GROUPS:
        matches = expand(pattern)
        lines = 0
        for path in matches:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    lines += sum(1 for _ in fh)
            except OSError:
                continue
        counts.append({"label": label, "files": len(matches), "lines": lines})
    return counts


def collect_build():
    jars = [p for p in expand("backend/build/libs/*.jar") if not p.endswith("-plain.jar")]
    classes = expand("backend/build/classes/**/*.class")
    sources = expand(f"{BE}/**/*.java")
    newest_class = newest_mtime(classes)
    newest_source = newest_mtime(sources)
    stale = bool(newest_class and newest_source and newest_source > newest_class)
    if not classes:
        compile_state = "none"
    elif stale:
        compile_state = "stale"
    else:
        compile_state = "fresh"
    return {
        "compileState": compile_state,
        "classes": len(classes),
        "newestClass": newest_class,
        "newestSource": newest_source,
        "sources": len(sources),
        "jar": os.path.relpath(jars[0], PROJECT_ROOT) if jars else None,
        "jarSize": total_size(jars[:1]),
        "jarModified": newest_mtime(jars[:1]),
        "frontendBundle": bool(expand("frontend/dist/index.html")),
        "frontendDeps": bool(expand("frontend/node_modules/vite")),
    }


def junit_summary(patterns):
    files = [p for pattern in patterns for p in expand(pattern)]
    total = failures = errors = skipped = 0
    duration = 0.0
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
        for suite in suites:
            total += int(float(suite.get("tests", 0)))
            failures += int(float(suite.get("failures", 0)))
            errors += int(float(suite.get("errors", 0)))
            skipped += int(float(suite.get("skipped", 0)))
            duration += float(suite.get("time", 0) or 0)
    return {
        "hasRun": bool(files),
        "tests": total,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "duration": round(duration, 2),
        "ranAt": newest_mtime(files),
    }


def collect_tests():
    return {
        "backend": {
            "files": len(expand("backend/src/test/java/**/*Test.java")),
            "run": junit_summary(["backend/build/test-results/**/*.xml"]),
        },
        "frontend": {
            "files": len(expand(f"{FE}/**/*.test.*")),
            "run": junit_summary(
                ["frontend/test-results/**/*.xml", "frontend/junit*.xml"]
            ),
        },
    }


def normalize_path(path):
    path = path.split("?")[0].strip()
    path = re.sub(r"\{[^}]*\}", "{}", path)
    return path.rstrip("/") or "/"


def designed_endpoints():
    endpoints = set()
    doc = os.path.join(PROJECT_ROOT, API_DESIGN_DOC)
    try:
        with open(doc, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = API_ROW_RE.match(line)
                if match and match.group(2).startswith("/api/"):
                    endpoints.add((match.group(1), normalize_path(match.group(2))))
    except OSError:
        return endpoints
    return endpoints


def implemented_endpoints():
    endpoints = set()
    for path in expand(f"{BE}/**/*Controller.java"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError:
            continue
        base_match = CLASS_MAP_RE.search(source)
        base = base_match.group(1) if base_match else ""
        for verb, suffix in METHOD_MAP_RE.findall(source):
            full = (base + (suffix or "")) or "/"
            endpoints.add((verb.upper(), normalize_path(full)))
    return endpoints


def collect_api():
    designed = designed_endpoints()
    implemented = implemented_endpoints()
    covered = designed & implemented
    missing = sorted(designed - implemented, key=lambda e: (e[1], e[0]))
    groups = {}
    for verb, path in designed:
        key = "/".join(path.split("/")[:3])
        entry = groups.setdefault(key, {"group": key, "designed": 0, "implemented": 0})
        entry["designed"] += 1
        if (verb, path) in implemented:
            entry["implemented"] += 1
    return {
        "designed": len(designed),
        "implemented": len(covered),
        "ratio": len(covered) / len(designed) if designed else 0,
        "controllers": len(expand(f"{BE}/**/*Controller.java")),
        "undocumented": len(implemented - designed),
        "missing": [{"method": m, "path": p} for m, p in missing[:14]],
        "missingTotal": len(missing),
        "groups": sorted(groups.values(), key=lambda g: g["group"]),
    }


def build_state():
    stages = collect_stages()
    current = next((s for s in stages if s["state"] != "done"), None)
    return {
        "generatedAt": time.time(),
        "projectRoot": PROJECT_ROOT,
        "currentStage": current["name"] if current else "전체 완료",
        "stages": stages,
        "workflows": collect_workflows(),
        "code": collect_code_counts(),
        "build": collect_build(),
        "tests": collect_tests(),
        "api": collect_api(),
    }


PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AX-Link 구축 현황</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --bg: #f4f5f7; --panel: #ffffff; --ink: #16181d; --muted: #5f6672;
  --line: #dfe2e8; --accent: #2f5fd0; --ok: #1f7a4d; --run: #b26a00; --idle: #8c93a0;
  --bad: #b4232b;
  --shadow: 0 1px 2px rgba(16,18,24,.06), 0 8px 24px rgba(16,18,24,.05);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #101215; --panel: #181b20; --ink: #e8eaee; --muted: #9aa2b0;
    --line: #2a2f37; --accent: #7aa2f7; --ok: #4cc38a; --run: #e0a458; --idle: #6b7280;
    --bad: #f47174;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.3);
  }
}
:root[data-theme="dark"] {
  --bg: #101215; --panel: #181b20; --ink: #e8eaee; --muted: #9aa2b0;
  --line: #2a2f37; --accent: #7aa2f7; --ok: #4cc38a; --run: #e0a458; --idle: #6b7280;
  --bad: #f47174;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.3);
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: 'IBM Plex Sans KR', system-ui, -apple-system, sans-serif;
  font-size: 14px; line-height: 1.55;
}
.wrap { max-width: 1140px; margin: 0 auto; padding: 32px 24px 72px; }
header { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; margin-bottom: 4px; }
h1 { font-size: 20px; font-weight: 600; margin: 0; letter-spacing: -.01em; }
.sub { color: var(--muted); font-size: 13px; }
.live { display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
        color: var(--muted); margin-left: auto; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--idle); }
.dot.on { background: var(--run); animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .35 } }
@media (prefers-reduced-motion: reduce) { .dot.on { animation: none } }
section { margin-top: 28px; }
h2 { font-size: 12px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase;
     color: var(--muted); margin: 0 0 12px; }
.rail { display: grid; grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: 10px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
.stage, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
         padding: 12px 13px; box-shadow: var(--shadow); }
.stage .nm, .card .nm { font-weight: 600; font-size: 13px; display: flex;
             align-items: center; gap: 6px; flex-wrap: wrap; }
.card .nm { font-size: 11px; font-weight: 500; letter-spacing: .06em;
            text-transform: uppercase; color: var(--muted); }
.stage .ct, .card .ct { font-family: 'IBM Plex Mono', monospace; font-size: 20px;
             margin-top: 6px; font-variant-numeric: tabular-nums; }
.stage .lbl, .card .lbl { font-size: 11px; color: var(--muted); }
.card .lbl.block { display: block; margin-top: 2px; }
.bar { height: 3px; background: var(--line); border-radius: 2px; margin-top: 9px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: var(--accent); }
.stage.done .bar > i { background: var(--ok); }
.stage.active .bar > i { background: var(--run); }
.pill { font-size: 10px; padding: 1px 6px; border-radius: 20px; border: 1px solid var(--line);
        color: var(--muted); font-weight: 500; }
.stage.done .pill { color: var(--ok); border-color: var(--ok); }
.stage.active .pill { color: var(--run); border-color: var(--run); }
.ok { color: var(--ok); } .warn { color: var(--run); } .bad { color: var(--bad); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
         box-shadow: var(--shadow); overflow: hidden; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 760px) { .two { grid-template-columns: 1fr } }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-weight: 500; font-size: 11px; letter-spacing: .06em;
     text-transform: uppercase; color: var(--muted); padding: 10px 14px;
     border-bottom: 1px solid var(--line); white-space: nowrap; }
td { padding: 9px 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
tr:last-child td { border-bottom: none; }
.mono { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
.num { text-align: right; }
.dim { color: var(--muted); }
.tag { font-size: 11px; padding: 1px 7px; border-radius: 4px; border: 1px solid var(--line);
       white-space: nowrap; }
.tag.run { color: var(--run); border-color: var(--run); }
.tag.ok { color: var(--ok); border-color: var(--ok); }
.tag.bad { color: var(--bad); border-color: var(--bad); }
.tag.no { color: var(--idle); }
.res { color: var(--muted); font-size: 12px; margin-top: 3px; max-width: 560px; }
footer { margin-top: 32px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>AX-Link 구축 현황</h1>
    <span class="sub" id="stage"></span>
    <span class="live"><span class="dot" id="dot"></span><span id="tick"></span></span>
  </header>
  <section><h2>상태 요약</h2><div class="cards" id="summary"></div></section>
  <section><h2>파이프라인</h2><div class="rail" id="rail"></div></section>
  <section><h2>API 커버리지</h2><div class="two">
    <div class="panel scroll"><table id="apigroups"></table></div>
    <div class="panel scroll"><table id="apimissing"></table></div>
  </div></section>
  <section><h2>에이전트</h2><div class="panel scroll"><table id="agents"></table></div></section>
  <section><h2>산출물 점검</h2><div class="panel scroll"><table id="files"></table></div></section>
  <section><h2>코드베이스</h2><div class="panel scroll"><table id="code"></table></div></section>
  <footer id="foot"></footer>
</div>
<script>
const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ago = t => {
  if (!t) return '—';
  const d = Math.max(0, Date.now() / 1000 - t);
  if (d < 60) return Math.floor(d) + '초 전';
  if (d < 3600) return Math.floor(d / 60) + '분 전';
  return Math.floor(d / 3600) + '시간 ' + Math.floor((d % 3600) / 60) + '분 전';
};
const kb = n => n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB'
  : n >= 1024 ? (n / 1024).toFixed(1) + ' KB' : n + ' B';
const card = (nm, ct, cls, lbl) => `<div class="card"><div class="nm">${esc(nm)}</div>
  <div class="ct ${cls || ''}">${ct}</div>
  <span class="lbl block">${lbl || ''}</span></div>`;

function summary(s) {
  const b = s.build, t = s.tests, a = s.api;
  const compile = { fresh: ['최신', 'ok'], stale: ['소스가 더 최신', 'warn'],
                    none: ['산출물 없음', 'bad'] }[b.compileState];
  const beRun = t.backend.run, feRun = t.frontend.run;
  const runText = r => !r.hasRun ? '실행 기록 없음'
    : `${r.tests}건 · 실패 ${r.failures + r.errors} · ${ago(r.ranAt)}`;
  const runCls = r => !r.hasRun ? 'dim' : (r.failures + r.errors) ? 'bad' : 'ok';
  document.getElementById('summary').innerHTML = [
    card('컴파일', `<span class="mono">${b.classes}</span>`, compile[1],
      `class 파일 · ${compile[0]} · ${ago(b.newestClass)}`),
    card('실행 JAR', b.jar ? kb(b.jarSize) : '없음', b.jar ? 'ok' : 'bad',
      b.jar ? `${esc(b.jar)} · ${ago(b.jarModified)}` : 'bootJar 미실행'),
    card('API 커버리지', `${Math.round(a.ratio * 100)}<span class="lbl">%</span>`,
      a.ratio >= 0.9 ? 'ok' : a.ratio >= 0.5 ? 'warn' : 'bad',
      `${a.implemented}/${a.designed} 엔드포인트 · 컨트롤러 ${a.controllers}개`),
    card('백엔드 테스트', `<span class="mono">${t.backend.files}</span>`,
      runCls(beRun), `테스트 파일 · ${runText(beRun)}`),
    card('프론트 테스트', `<span class="mono">${t.frontend.files}</span>`,
      runCls(feRun), `테스트 파일 · ${runText(feRun)}`),
    card('프론트 빌드', b.frontendBundle ? '번들 있음' : '미빌드',
      b.frontendBundle ? 'ok' : 'dim',
      b.frontendDeps ? 'node_modules 설치됨' : 'node_modules 없음'),
  ].join('');
}

function render(s) {
  document.getElementById('stage').textContent = '현재 단계 · ' + s.currentStage;
  const busy = s.workflows.some(w => w.running);
  document.getElementById('dot').className = 'dot' + (busy ? ' on' : '');
  document.getElementById('tick').textContent = busy ? '작업 진행 중' : '유휴';
  summary(s);

  document.getElementById('rail').innerHTML = s.stages.map(st => `
    <div class="stage ${st.state}">
      <div class="nm">${esc(st.name)} <span class="pill">${
        st.state === 'done' ? '완료' : st.state === 'active' ? '진행' : '대기'}</span></div>
      <div class="ct">${st.done}<span class="lbl"> / ${st.total}</span></div>
      <div class="bar"><i style="width:${Math.round(st.ratio * 100)}%"></i></div>
    </div>`).join('');

  document.getElementById('apigroups').innerHTML =
    '<thead><tr><th>그룹</th><th class="num">구현</th><th class="num">설계</th><th class="num">비율</th></tr></thead><tbody>' +
    s.api.groups.map(g => {
      const r = g.designed ? g.implemented / g.designed : 0;
      return `<tr><td class="mono">${esc(g.group)}</td>
        <td class="num mono">${g.implemented}</td>
        <td class="num mono dim">${g.designed}</td>
        <td class="num mono ${r === 1 ? 'ok' : r ? 'warn' : 'bad'}">${Math.round(r * 100)}%</td></tr>`;
    }).join('') + '</tbody>';

  document.getElementById('apimissing').innerHTML =
    `<thead><tr><th>미구현 엔드포인트 (${s.api.missingTotal})</th></tr></thead><tbody>` +
    (s.api.missing.length ? s.api.missing.map(m =>
      `<tr><td class="mono"><span class="tag">${esc(m.method)}</span> ${esc(m.path)}</td></tr>`).join('')
      : '<tr><td class="dim ok">설계된 엔드포인트 전부 구현됨</td></tr>') +
    (s.api.missingTotal > s.api.missing.length
      ? `<tr><td class="dim">… 외 ${s.api.missingTotal - s.api.missing.length}건</td></tr>` : '') +
    '</tbody>';

  const rows = [];
  s.workflows.forEach(w => w.agents.forEach(a => rows.push(a)));
  document.getElementById('agents').innerHTML =
    '<thead><tr><th>작업</th><th>상태</th><th class="num">도구호출</th><th>최근 활동</th></tr></thead><tbody>' +
    (rows.length ? rows.map(a => `
      <tr>
        <td><div>${esc(a.title)}</div>${a.result ? `<div class="res">${esc(a.result)}</div>` : ''}</td>
        <td><span class="tag ${a.running ? 'run' : a.result ? 'ok' : 'no'}">${
          a.running ? '실행 중' : a.result ? '완료' : '대기'}</span></td>
        <td class="num mono">${a.toolCalls}</td>
        <td class="dim mono">${ago(a.lastActivity)}${a.lastTool ? ' · ' + esc(a.lastTool) : ''}</td>
      </tr>`).join('')
      : '<tr><td colspan="4" class="dim">실행된 에이전트가 없습니다.</td></tr>') + '</tbody>';

  document.getElementById('files').innerHTML =
    '<thead><tr><th>단계</th><th>항목</th><th class="num">개수</th><th class="num">크기</th><th>갱신</th><th>경로</th></tr></thead><tbody>' +
    s.stages.flatMap(st => st.checks.map(c => `
      <tr>
        <td class="dim">${esc(st.name)}</td>
        <td>${esc(c.label)}</td>
        <td class="num mono ${c.ok ? 'ok' : c.matched ? 'warn' : 'dim'}">${c.matched}<span class="lbl"> / ${c.need}</span></td>
        <td class="num mono ${c.matched ? '' : 'dim'}">${c.matched ? kb(c.size) : '—'}</td>
        <td class="dim mono">${c.matched ? ago(c.modified) : '미생성'}</td>
        <td class="dim mono">${esc(c.glob)}</td>
      </tr>`)).join('') + '</tbody>';

  document.getElementById('code').innerHTML =
    '<thead><tr><th>구분</th><th class="num">파일</th><th class="num">라인</th></tr></thead><tbody>' +
    s.code.map(c => `<tr><td>${esc(c.label)}</td>
      <td class="num mono ${c.files ? '' : 'dim'}">${c.files}</td>
      <td class="num mono ${c.lines ? '' : 'dim'}">${c.lines.toLocaleString()}</td></tr>`).join('') +
    '</tbody>';

  document.getElementById('foot').textContent =
    s.projectRoot + ' · ' + new Date(s.generatedAt * 1000).toLocaleTimeString('ko-KR');
}

async function poll() {
  try {
    render(await (await fetch('/api/state')).json());
  } catch (e) {
    document.getElementById('tick').textContent = '연결 끊김';
  }
}
poll();
setInterval(poll, 4000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/state"):
            body = json.dumps(build_state()).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def demo():
    assert set(expand(f"{FE}/features/{{auth,widgets}}/*.tsx")) == set(
        expand(f"{FE}/features/auth/*.tsx") + expand(f"{FE}/features/widgets/*.tsx")
    )
    assert normalize_path("/api/projects/{projectId}/close") == "/api/projects/{}/close"
    assert normalize_path("/api/sync-jobs?status=X") == "/api/sync-jobs"

    state = build_state()
    assert len(state["stages"]) == len(STAGES)
    for stage in state["stages"]:
        assert stage["state"] in ("pending", "active", "done")
        assert 0 <= stage["ratio"] <= 1
        assert len(stage["checks"]) == stage["total"]
        for item in stage["checks"]:
            assert item["ok"] == (item["matched"] >= item["need"])
            assert item["need"] >= 1 and item["matched"] >= 0

    build = state["build"]
    assert build["compileState"] in ("fresh", "stale", "none")
    assert build["sources"] > 0, "백엔드 소스를 찾지 못했다"

    api = state["api"]
    assert api["designed"] > 0, "설계 문서에서 엔드포인트를 파싱하지 못했다"
    assert 0 <= api["implemented"] <= api["designed"]
    assert api["controllers"] > 0
    assert len(api["missing"]) == min(api["missingTotal"], 14)

    for scope in ("backend", "frontend"):
        run = state["tests"][scope]["run"]
        assert run["tests"] >= run["failures"] + run["errors"]

    assert isinstance(state["workflows"], list)
    for run in state["workflows"]:
        for agent in run["agents"]:
            assert isinstance(agent["toolCalls"], int)
            assert isinstance(agent["running"], bool)
    assert all("label" in c and "files" in c for c in state["code"])
    assert "<title>AX-Link 구축 현황</title>" in PAGE
    json.dumps(state)
    print(
        "demo ok:", state["currentStage"],
        "| stages", "/".join(f"{s['name']}:{s['state']}" for s in state["stages"]),
        "\n  compile", build["compileState"],
        "| jar", build["jar"],
        "| api", f"{api['implemented']}/{api['designed']}",
        "(missing", api["missingTotal"], ", undocumented", api["undocumented"], ")",
        "| tests be", state["tests"]["backend"]["files"],
        "fe", state["tests"]["frontend"]["files"],
        "| agents", sum(len(w["agents"]) for w in state["workflows"]),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.demo:
        demo()
    else:
        print(f"http://localhost:{args.port}")
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
