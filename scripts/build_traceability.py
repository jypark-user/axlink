#!/usr/bin/env python3
"""
docs/traceability.csv 생성기.

git 커밋 메시지의 [SWFR.CON.001] 태그와 docs/ 산출물의 ID를 파싱해
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
# 설계 근거 판별은 앱과 같은 함수를 쓴다(ARC-024 4절). 두 결과가 다르면 원천이 다른 것이다.
sys.path.insert(0, str(ROOT))
from app.standard import design_refs  # noqa: E402

DOCS = ROOT / "docs"
DESIGN_GLOBS = ["docs/20-design/*.md"]
OUT = DOCS / "traceability.csv"
REQUIREMENTS = DOCS / "10-requirements" / "IM-001-요구사항정의서.md"
# 파일럿 원본은 참고자료지 납품 산출물이 아니다(CLAUDE.md 1절). 추적표에 섞지 않는다.
EXCLUDED = {"90-pilot"}

# 요구사항 축은 IM-001 의 코드 체계를 쓴다. 근거는 ARC-002.
#   SWFR = 소프트웨어 / QUR = 품질 / SER = 보안·기타 / SFR = 상위 과업 항목
REQ_RE = re.compile(r"\b((?:SWFR|QUR|SER)\.[A-Z]{3}\.\d{3})\b")
TASK_RE = re.compile(r"\b(SFR\.[A-Z]{3}\.\d{3})\b")
# 설계·시험 축. DSN 은 파일럿 시절 표기라 읽기만 하고 새로 쓰지 않는다.
ARTIFACT_RE = re.compile(r"\b((?:ARC|DSN|TST|RSK|DEF)-\d{3})\b")
# 도구별 접두 필수: GH-23 (GitHub) / RM-204 (Redmine).
# 맨 "#17"은 규약 위반 — 도구 구분이 안 되고, Redmine이 자기 이슈로 오인한다.
ISSUE_RE = re.compile(r"\b(GH|RM)-(\d+)\b")
BARE_ISSUE_RE = re.compile(r"(?:Refs|Closes|Fixes):?\s*#\d+", re.IGNORECASE)
# scope 목록은 CLAUDE.md 3절이 기준이다.
SUBJECT_RE = re.compile(
    r"^(feat|fix|docs|test|refactor|chore|perf)"
    r"\((auth|org|project|integration|standard|dashboard|rag|document"
    r"|ai|semantic|frontend|infra|docs)\):\s+.+"
)
# IM-001 요구사항 표의 행. | SWFR.CON.001 | 커넥터는 ... | 필수 | R·D | S2-2 |
ROW_RE = re.compile(r"^\|\s*((?:SWFR|QUR|SER)\.[A-Z]{3}\.\d{3})\s*\|\s*(.+?)\s*\|")
FIELDS = [
    "req_id", "req_title", "task_item", "design_id", "test_id",
    "issue_no", "commit_sha", "status", "updated_at",
]


class GitError(RuntimeError):
    """git 을 못 읽었다. 빈 출력으로 넘기면 커밋 0건짜리 표가 나오고 검사도 통과한다."""


def git(*args: str) -> str:
    """git 출력을 UTF-8 로 읽는다. 로캘에 맡기면 Windows(cp949)에서 깨진다."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:  # git 이 없거나 경로가 없다
        raise GitError(f"git {args[0]} 실패: {exc}") from exc
    if proc.returncode != 0:
        raise GitError(f"git {args[0]} 실패: {(proc.stderr or '').strip()}")
    return proc.stdout or ""


def markdown_files() -> list[Path]:
    return sorted(
        md for md in DOCS.rglob("*.md")
        if not EXCLUDED.intersection(md.relative_to(DOCS).parts)
    )


def scan_requirements() -> tuple[dict[str, str], dict[str, str]]:
    """요구사항정의서에서 요구사항 제목과 상위 과업 항목을 읽는다."""
    titles: dict[str, str] = {}
    tasks: dict[str, str] = {}
    if not REQUIREMENTS.exists():
        return titles, tasks

    current_task = ""
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            found = TASK_RE.search(line)
            if found:
                current_task = found.group(1)
            continue
        row = ROW_RE.match(line.strip())
        if not row:
            continue
        rid, title = row.group(1), row.group(2)
        titles[rid] = title.replace("**", "").strip()
        tasks[rid] = current_task

    return titles, tasks


def scan_commits(known: set[str]) -> tuple[dict[str, set], dict[str, set], list[str]]:
    """커밋을 훑어 요구사항별 커밋·이슈를 모으고 규약 위반을 수집한다."""
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

        reqs = REQ_RE.findall(subject)
        artifacts = ARTIFACT_RE.findall(subject)
        if not reqs and not artifacts and "[chore]" not in subject:
            violations.append(f"{sha[:8]} 추적 ID 누락: {subject}")

        # 요구사항정의서에 없는 코드는 오타다. 조용히 넘기면 추적표에 유령 행이 생긴다.
        for rid in reqs:
            if known and rid not in known:
                violations.append(f"{sha[:8]} 정의되지 않은 요구사항 ID {rid}: {subject}")

        full = f"{subject}\n{body}"
        if BARE_ISSUE_RE.search(full):
            violations.append(
                f"{sha[:8]} 접두 없는 이슈 참조(#숫자) — GH-/RM- 를 붙일 것: {subject}"
            )

        issues = {f"{p}-{n}" for p, n in ISSUE_RE.findall(full)}
        for rid in reqs:
            by_req_commit[rid].add(sha[:8])
            by_req_issue[rid].update(issues)

    return by_req_commit, by_req_issue, violations


def scan_docs(known: set[str]) -> tuple[dict[str, set], dict[str, set], list[str]]:
    """docs/ 마크다운에서 요구사항 <-> 설계·시험 연결을 읽는다.

    설계는 docs/20-design/ 문서의 명시적 참조 세 꼴(머리 표 관련 행, 요구사항 대응표, 절 제목
    괄호)만 읽는다(ARC-024). 문서 어딘가에 코드가 나왔다는 이유만으로 잇지 않는다. 초안 문서와
    "미결" 한정어는 설계 ID 옆에 괄호로 남긴다(예: `IM-003(초안)`, `ARC-006(미결)`).
    시험(TST)은 지금처럼 같은 줄에 함께 나온 것만 잇는다.
    """
    designs: dict[str, set] = defaultdict(set)
    tests: dict[str, set] = defaultdict(set)
    violations: list[str] = []

    for md in markdown_files():
        text = md.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        rel = md.relative_to(ROOT).as_posix()

        for no, line in enumerate(lines, 1):
            reqs = set(REQ_RE.findall(line))
            if not reqs:
                continue
            inline = set(ARTIFACT_RE.findall(line))
            for rid in sorted(reqs):
                if known and rid not in known:
                    violations.append(f"{rel}:{no} 정의되지 않은 요구사항 ID {rid}")
                    continue
                tests[rid].update(i for i in inline if i.startswith("TST-"))

        if not design_refs.match_any("docs/" + md.relative_to(DOCS).as_posix(), DESIGN_GLOBS):
            continue
        info = design_refs.parse(text, known)
        name = info.doc_id or md.stem
        # 문서 하나는 요구사항마다 한 번만 적는다. 같은 코드를 여러 곳에서 가리키면 한정어를 모은다
        qualifiers: dict[str, set[str]] = defaultdict(set)
        for ref in info.refs:
            qualifiers[ref.code].update([ref.qualifier] if ref.qualifier else [])
        for code, quals in qualifiers.items():
            tags = (["초안"] if info.status == design_refs.DRAFT else []) + sorted(quals)
            designs[code].add(f"{name}({','.join(tags)})" if tags else name)

    return designs, tests, violations


def main() -> int:
    # Windows 콘솔은 cp949 라 한글·em dash 출력에서 죽는다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="규약 검사만 수행 (CI)")
    args = ap.parse_args()

    titles, tasks = scan_requirements()
    known = set(titles)
    try:
        commits, issues, violations = scan_commits(known)
    except GitError as exc:
        print(f"[오류] {exc}. 추적표를 만들지 않았다.", file=sys.stderr)
        return 2
    designs, tests, doc_violations = scan_docs(known)
    violations += doc_violations

    if args.check:
        for v in violations:
            print(f"[규약위반] {v}", file=sys.stderr)
        print(f"검사 완료 — 위반 {len(violations)}건", file=sys.stderr)
        return 1 if violations else 0

    req_ids = sorted(set(titles) | set(commits) | set(designs) | set(tests))
    today = date.today().isoformat()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for rid in req_ids:
            w.writerow({
                "req_id": rid,
                "req_title": titles.get(rid, ""),
                "task_item": tasks.get(rid, ""),
                "design_id": " ".join(sorted(designs.get(rid, []))),
                "test_id": " ".join(sorted(tests.get(rid, []))),
                "issue_no": " ".join(sorted(issues.get(rid, []))),
                "commit_sha": " ".join(sorted(commits.get(rid, []))),
                "status": "implemented" if commits.get(rid) else "draft",
                "updated_at": today,
            })

    covered = sum(1 for rid in req_ids if commits.get(rid))
    print(
        f"{OUT.relative_to(ROOT)} 생성 — 요구사항 {len(req_ids)}건 "
        f"(커밋 연결 {covered}건), 규약위반 {len(violations)}건"
    )
    for v in violations:
        print(f"  [규약위반] {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
