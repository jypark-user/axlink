#!/usr/bin/env python3
"""
docs/traceability.csv 생성기.

git 커밋 메시지의 [REQ-###] 태그와 docs/ 산출물 헤딩의 ID를 파싱해
요구사항 -> 설계 -> 시험 -> 이슈 -> 커밋 추적표를 만든다.

자기참조(dogfooding)의 핵심 도구다. 이 스크립트가 빈 표를 뱉으면
그건 스크립트 버그가 아니라 우리가 규약을 안 지킨 것이다.

usage:  python scripts/build_traceability.py [--check]
        --check : 파일을 쓰지 않고 규약 위반만 보고 (CI용, 위반 시 exit 1)
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "traceability.csv"

# 설계 접두는 CLAUDE.md §2 가 정한 ARC 다. DSN 은 파일럿 시절 표기라 읽기만 하고 새로 쓰지 않는다.
ID_RE = re.compile(r"\b(REQ|ARC|DSN|TST|RSK|DEF)-(\d{3})\b")
# 도구별 접두 필수: GH-23 (GitHub) / RM-204 (Redmine).
# 맨 "#17"은 규약 위반 — 도구 구분이 안 되고, Redmine이 자기 이슈로 오인한다.
ISSUE_RE = re.compile(r"\b(GH|RM)-(\d+)\b")
BARE_ISSUE_RE = re.compile(r"(?:Refs|Closes|Fixes):?\s*#\d+", re.IGNORECASE)
# scope 목록은 CLAUDE.md 3절이 기준이다. 파일럿 시절 파서(connectors/pipeline/templates/web)가
# 헌법과 어긋나 있어 맞춘다.
SUBJECT_RE = re.compile(
    r"^(feat|fix|docs|test|refactor|chore|perf)"
    r"\((auth|org|project|integration|standard|dashboard|rag|document"
    r"|ai|semantic|frontend|infra|docs)\):\s+.+"
)
FIELDS = [
    "req_id", "req_title", "task_item", "design_id", "test_id",
    "issue_no", "commit_sha", "status", "updated_at",
]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout


def scan_commits() -> tuple[dict[str, set], dict[str, set], list[str]]:
    """커밋을 훑어 REQ별 커밋/이슈를 모으고 규약 위반을 수집한다."""
    raw = git("log", "--no-merges", "--pretty=format:%H%x1f%s%x1f%b%x1e")
    by_req_commit: dict[str, set] = defaultdict(set)
    by_req_issue: dict[str, set] = defaultdict(set)
    violations: list[str] = []

    for rec in filter(None, (r.strip() for r in raw.split("\x1e"))):
        parts = rec.split("\x1f")
        if len(parts) < 2:
            continue
        sha, subject, body = parts[0], parts[1], parts[2] if len(parts) > 2 else ""

        if not SUBJECT_RE.match(subject):
            violations.append(f"{sha[:8]} 커밋 제목 규약 위반: {subject}")

        ids = ID_RE.findall(subject)
        if not ids and "[chore]" not in subject:
            violations.append(f"{sha[:8]} 추적 ID 누락: {subject}")

        full = f"{subject}\n{body}"
        if BARE_ISSUE_RE.search(full):
            violations.append(
                f"{sha[:8]} 접두 없는 이슈 참조(#숫자) — GH-/RM- 를 붙일 것: {subject}"
            )

        issues = {f"{p}-{n}" for p, n in ISSUE_RE.findall(full)}
        for prefix, num in ids:
            if prefix != "REQ":
                continue
            key = f"REQ-{num}"
            by_req_commit[key].add(sha[:8])
            by_req_issue[key].update(issues)

    return by_req_commit, by_req_issue, violations


def scan_docs() -> tuple[dict[str, str], dict[str, set], dict[str, set]]:
    """docs/ 마크다운에서 REQ 제목과 REQ<->DSN/TST 연결을 읽는다."""
    titles: dict[str, str] = {}
    designs: dict[str, set] = defaultdict(set)
    tests: dict[str, set] = defaultdict(set)

    for md in sorted(DOCS.rglob("*.md")):
        current_req: str | None = None
        for line in md.read_text(encoding="utf-8", errors="ignore").splitlines():
            found = ID_RE.findall(line)
            if not found:
                continue
            reqs = [f"REQ-{n}" for p, n in found if p == "REQ"]
            if reqs:
                current_req = reqs[0]
                if line.lstrip().startswith("#"):
                    titles[current_req] = re.sub(
                        r"^#+\s*|\bREQ-\d{3}\b[\s:.-]*", "", line
                    ).strip()
            if current_req:
                designs[current_req].update(f"DSN-{n}" for p, n in found if p == "DSN")
                tests[current_req].update(f"TST-{n}" for p, n in found if p == "TST")

    return titles, designs, tests


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="규약 검사만 수행 (CI)")
    args = ap.parse_args()

    commits, issues, violations = scan_commits()
    titles, designs, tests = scan_docs()

    if args.check:
        for v in violations:
            print(f"[규약위반] {v}", file=sys.stderr)
        print(f"검사 완료 — 위반 {len(violations)}건", file=sys.stderr)
        return 1 if violations else 0

    req_ids = sorted(set(commits) | set(titles) | set(designs) | set(tests))
    today = date.today().isoformat()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for rid in req_ids:
            w.writerow({
                "req_id": rid,
                "req_title": titles.get(rid, ""),
                "task_item": "",
                "design_id": " ".join(sorted(designs.get(rid, []))),
                "test_id": " ".join(sorted(tests.get(rid, []))),
                "issue_no": " ".join(sorted(issues.get(rid, []))),
                "commit_sha": " ".join(sorted(commits.get(rid, []))),
                "status": "implemented" if commits.get(rid) else "draft",
                "updated_at": today,
            })

    print(f"{OUT.relative_to(ROOT)} 생성 — 요구사항 {len(req_ids)}건, 규약위반 {len(violations)}건")
    for v in violations:
        print(f"  [규약위반] {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
