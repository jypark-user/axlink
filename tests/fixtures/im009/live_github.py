"""IM-005A 시험자료를 실제 GitHub 저장소 두 곳에 만든다 (TD-CON-1 · TD-CON-3, 실연동 시험용).

재생 자료(payloads.py)와 같은 도메인 값(data.py)을 실제 저장소에 쓴다. 쓰기는 이 PC 의 `gh` CLI
로그인으로만 한다(이슈·라벨·마일스톤·PR 은 `gh api`, 커밋은 `gh auth git-credential` 로 push).
토큰 값을 이 모듈이 읽거나 남기지 않는다. 읽기 쪽(AX Link 연결과 원천 비교)은 읽기 전용 토큰
`AXLINK_VERIFY_GH_TOKEN` 을 쓴다.

실제 GitHub 은 생성·닫힌 시각을 지정할 수 없다. 커밋의 저자·커미터 시각만 IM-005A 값으로 맞추고,
이슈·PR·마일스톤의 시각은 원천(GitHub API)이 준 값과 AX Link 값을 비교한다.

번호는 생성 순서로 맞춘다. TD-CON-1: 마일스톤 M-a #1 · M-b #2, 이슈 G1~G5 #1~#5, PR #6~#8.
TD-CON-3: 이슈 #1~#3 을 만들었다 지워 W4 를 #4 로 둔다(번호는 재사용되지 않는다).

상태 전환
- seed():       두 저장소를 S0 로 채운다. 있는 것은 건너뛴다(멱등). 끝에 태그 td-s0 를 단다.
- to_s1():      TD-CON-1 에 S1 커밋 둘을 push 한다(TD-CMT-2 설계서 파일, WBS 3.2 85%).
- restore_s0(): 파일 내용을 td-s0 와 같게 되돌리는 커밋을 push 한다. 이력은 지우지 않는다
                (force push 를 쓰지 않는다). 그래서 S1 을 돌릴 때마다 커밋이 늘어난다.
                시험은 고정 건수가 아니라 원천 API 의 건수와 비교한다.

사용
    python -m tests.fixtures.im009.live_github seed | s1 | restore | status
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import files

HERE = Path(__file__).resolve().parent
MAP_PATH = HERE / "live" / "github-map.json"

API = "https://api.github.com"
TOKEN_ENV = "AXLINK_VERIFY_GH_TOKEN"
REPOS = {
    "TD-CON-1": os.environ.get("AXLINK_VERIFY_GH_REPO", "jypark-user/axlink-verify"),
    "TD-CON-3": os.environ.get("AXLINK_VERIFY_GH_REPO_WEB", "jypark-user/axlink-verify-web"),
}
TAG_S0 = "td-s0"
AUTHOR_NAME = "td-parkpm"
AUTHOR_EMAIL = "td-parkpm@example.invalid"

WBS_PATH = "docs/00-management/WBS.xlsx"
DESIGN_DOC_PATH = "docs/20-design/설계-민원조회.md"
DESIGN_FILE_PATH = "docs/20-design/SW설계서_v0.9.docx"
REQ_LABEL = "유형: 요구사항"

# 연결 설정(IM-005A 3절 TD-CON-1)
MAPPING_CON1 = {
    "designDocPaths": "docs/20-design/*.md",
    "collectFiles": f"{WBS_PATH}=PROJECT_PLAN",
}

# IM-005A 에 없는 받침 커밋. 실제 저장소는 파일을 커밋으로만 넣을 수 있어서 생긴다
SETUP_MESSAGE = "chore: 시험 저장소 초기 구성"
SETUP_DATE = "2026-03-20T09:00:00Z"
README_CON1 = "# 가상 시험 저장소 (IM-005A TD-CON-1)\n\n실제 사업 자료가 아니다.\n"
# PR 의 head 커밋. TD-PR-1 은 TD-CMT-3 이 head 다. 나머지 둘은 코드 참조가 없는 메시지로 둔다
# (메시지에 요구사항 코드나 RM- 참조를 넣으면 IM-005A 7.4 에 없는 추적 링크가 생긴다)
PR_HEADS = {
    "TD-PR-1": ("fix/button-align", "TD-CMT-3", None, None),
    "TD-PR-2": (
        "feat/portal-list",
        None,
        "refactor: 민원 목록 조회 정리",
        "2026-08-15T09:00:00Z",
    ),
    "TD-PR-3": ("refactor/login", None, "refactor: 로그인 처리 정리", "2026-08-18T09:00:00Z"),
}
S1_WBS_MESSAGE = "docs: WBS 3.2 실적 85% 반영"
S1_WBS_AUTHORED = "2026-09-25T09:00:00Z"
RESTORE_MESSAGE = "chore: 시험 상태 S0 로 되돌림"


class LiveSeedError(RuntimeError):
    pass


# ---------------------------------------------------------------- gh · git


def gh_available() -> bool:
    if shutil.which("gh") is None:
        return False
    r = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return r.returncode == 0


def _gh(method: str, path: str, body: dict | None = None, *, ok404: bool = False) -> Any:
    args = ["gh", "api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
    if body is not None:
        args += ["--input", "-"]
    r = subprocess.run(
        args,
        input=json.dumps(body, ensure_ascii=False) if body is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode:
        if ok404 and "HTTP 404" in r.stderr:
            return None
        raise LiveSeedError(f"gh api {method} {path} 실패: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    cmd = [
        "git",
        "-c", "credential.helper=",
        "-c", "credential.helper=!gh auth git-credential",
        "-c", "core.autocrlf=false",
        "-c", "core.quotepath=false",
        "-c", "init.defaultBranch=main",
        *args,
    ]  # fmt: skip
    full_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
        "GIT_TERMINAL_PROMPT": "0",
        **(env or {}),
    }
    r = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=full_env
    )
    if r.returncode:
        raise LiveSeedError(f"git {' '.join(args[:2])} 실패: {r.stderr.strip()[:300]}")
    return r.stdout


@contextmanager
def _clone(repo: str) -> Iterator[Path]:
    tmp = Path(tempfile.mkdtemp(prefix="axlink-live-"))
    try:
        _git(tmp, "clone", "-q", f"https://github.com/{repo}.git", "w")
        w = tmp / "w"
        if _has_remote_main(w):
            _git(w, "checkout", "-q", "-B", "main", "origin/main")
        else:  # 빈 저장소. 첫 커밋이 main 에 들어가게 한다
            _git(w, "symbolic-ref", "HEAD", "refs/heads/main")
        yield w
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _has_remote_main(w: Path) -> bool:
    return bool(_git(w, "ls-remote", "--heads", "origin", "main").strip())


def _subjects(w: Path, ref: str = "HEAD") -> dict[str, str]:
    """{커밋 제목: SHA}. 같은 제목이 여럿이면 가장 최근 것."""
    try:
        out = _git(w, "log", ref, "--format=%H%x09%s")
    except LiveSeedError:
        return {}  # 커밋이 아직 없다
    found: dict[str, str] = {}
    for line in out.splitlines():
        sha, _, subject = line.partition("\t")
        found.setdefault(subject, sha)
    return found


def _commit(
    w: Path,
    message: str,
    writes: dict[str, bytes | None],
    authored: str,
    committed: str | None = None,
) -> str:
    for path, data in writes.items():
        if data is None:
            _git(w, "rm", "-q", "--", path)
            continue
        p = w / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        _git(w, "add", "--", path)
    _git(
        w,
        "commit", "-q", "-m", message,
        env={"GIT_AUTHOR_DATE": authored, "GIT_COMMITTER_DATE": committed or authored},
    )  # fmt: skip
    return _git(w, "rev-parse", "HEAD").strip()


def _now_git() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- 파일 내용


def _source(path: str, note: str) -> bytes:
    return f"# {path}\n# 가상 시험자료(IM-005A). {note}\n".encode()


def _files_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="axlink-live-files-"))


def _commit_files(tid: str) -> dict[str, bytes]:
    c = next(c for c in d.COMMITS if c.tid == tid)
    return {p: _source(p, c.message) for p in c.files}


# ---------------------------------------------------------------- TD-CON-1


def _ensure_label(repo: str, name: str) -> None:
    labels = _gh("GET", f"repos/{repo}/labels?per_page=100") or []
    if not any(lb["name"] == name for lb in labels):
        _gh("POST", f"repos/{repo}/labels", {"name": name, "color": "0e8a16"})


def _ensure_milestones(repo: str) -> dict[str, int]:
    """M-a #1, M-b #2. 닫기는 이슈를 단 뒤에 한다."""
    have = {m["title"]: m for m in _gh("GET", f"repos/{repo}/milestones?state=all") or []}
    out: dict[str, int] = {}
    for ms in (m for m in d.MILESTONES if m.connection == "TD-CON-1"):
        if ms.name not in have:
            have[ms.name] = _gh(
                "POST",
                f"repos/{repo}/milestones",
                {
                    "title": ms.name,
                    "due_on": f"{ms.due.isoformat()}T12:00:00Z",
                    "description": f"가상 시험자료 {ms.tid}",
                },
            )
        if have[ms.name]["number"] != ms.number:
            raise LiveSeedError(f"{ms.tid} 번호 {have[ms.name]['number']} (기대 {ms.number})")
        out[ms.tid] = ms.number
    return out


def _all_issue_numbers(repo: str) -> dict[int, dict]:
    """이슈와 PR 을 함께(번호를 공유한다)."""
    rows = _gh("GET", f"repos/{repo}/issues?state=all&per_page=100") or []
    return {r["number"]: r for r in rows}


def _ensure_issues(repo: str, issues: list[d.GithubIssue], ms_numbers: dict[str, int]) -> None:
    by_name = {m.name: m.number for m in d.MILESTONES if m.connection == "TD-CON-1"}
    for issue in issues:
        have = _all_issue_numbers(repo)
        if issue.number in have:
            if have[issue.number]["title"] != issue.title:
                raise LiveSeedError(
                    f"{issue.tid}: #{issue.number} 제목이 다르다({have[issue.number]['title']})"
                )
            continue
        body: dict[str, Any] = {"title": issue.title, "body": issue.body or ""}
        if issue.labels:
            body["labels"] = list(issue.labels)
        if issue.milestone:
            body["milestone"] = by_name[issue.milestone]
        made = _gh("POST", f"repos/{repo}/issues", body)
        if made["number"] != issue.number:
            raise LiveSeedError(f"{issue.tid} 번호 {made['number']} (기대 {issue.number})")


def _ensure_pr(w: Path, repo: str, pr: d.PullRequest) -> None:
    branch, cmt_tid, message, authored = PR_HEADS[pr.tid]
    if cmt_tid:
        c = next(c for c in d.COMMITS if c.tid == cmt_tid)
        message, authored, writes = c.message, c.authored, _commit_files(cmt_tid)
    else:
        writes = {p: _source(p, pr.title) for p in pr.files}
    existing = _gh("GET", f"repos/{repo}/pulls/{pr.number}", ok404=True)
    if existing and existing.get("merged_at"):
        return
    if message not in _subjects(w):
        remote = _git(w, "ls-remote", "--heads", "origin", branch).strip()
        if remote:
            _git(w, "fetch", "-q", "origin", branch)
            _git(w, "checkout", "-q", "-B", branch, "FETCH_HEAD")
        else:
            _git(w, "checkout", "-q", "-B", branch, "main")
            _commit(w, message, writes, authored)
            _git(w, "push", "-q", "origin", branch)
        if existing is None:
            have = _all_issue_numbers(repo)
            if have and max(have) != pr.number - 1:
                raise LiveSeedError(f"{pr.tid}: 다음 번호가 #{pr.number} 가 아니다")
            made = _gh(
                "POST",
                f"repos/{repo}/pulls",
                {"title": pr.title, "body": pr.body, "head": branch, "base": "main"},
            )
            if made["number"] != pr.number:
                raise LiveSeedError(f"{pr.tid} 번호 {made['number']} (기대 {pr.number})")
        # 기본 브랜치를 head 로 빨리감기하면 GitHub 이 PR 을 병합으로 본다(병합 커밋이 안 생긴다)
        _git(w, "checkout", "-q", "main")
        _git(w, "merge", "-q", "--ff-only", branch)
        _git(w, "push", "-q", "origin", "main")
    for _ in range(30):
        got = _gh("GET", f"repos/{repo}/pulls/{pr.number}")
        if got.get("merged_at"):
            break
        time.sleep(2)
    else:
        raise LiveSeedError(f"{pr.tid}: 빨리감기 뒤에도 병합으로 바뀌지 않았다")
    _gh("DELETE", f"repos/{repo}/git/refs/heads/{branch}", ok404=True)


def _to_main(w: Path) -> None:
    try:
        _git(w, "rev-parse", "-q", "--verify", "refs/heads/main")
    except LiveSeedError:
        return  # 아직 커밋이 없다. HEAD 가 main 을 가리키고 있다
    _git(w, "checkout", "-q", "main")


def _ensure_main_commit(w: Path, message: str, writes: dict[str, bytes], authored: str) -> None:
    _to_main(w)
    if message in _subjects(w):
        return
    _commit(w, message, writes, authored)
    _git(w, "push", "-q", "origin", "main")


def _tag_s0(w: Path) -> None:
    if _git(w, "ls-remote", "--tags", "origin", TAG_S0).strip():
        return
    _git(w, "tag", TAG_S0, "main")
    _git(w, "push", "-q", "origin", TAG_S0)


def seed_con1(files_dir: Path) -> None:
    repo = REPOS["TD-CON-1"]
    made = files.make_all(files_dir)
    _ensure_label(repo, REQ_LABEL)
    ms = _ensure_milestones(repo)
    _ensure_issues(repo, d.GITHUB_ISSUES_CON1, ms)
    with _clone(repo) as w:
        _ensure_main_commit(
            w,
            SETUP_MESSAGE,
            {
                "README.md": README_CON1.encode(),
                WBS_PATH: made["TD-DOC-6"].read_bytes(),
                DESIGN_DOC_PATH: made["TD-DOC-R1"].read_bytes(),
            },
            SETUP_DATE,
        )
        c1 = next(c for c in d.COMMITS if c.tid == "TD-CMT-1")
        _ensure_main_commit(w, c1.message, _commit_files("TD-CMT-1"), c1.authored)
        prs = {p.tid: p for p in d.PULL_REQUESTS_CON1}
        _ensure_pr(w, repo, prs["TD-PR-1"])
        c4 = next(c for c in d.COMMITS if c.tid == "TD-CMT-4")
        _ensure_main_commit(w, c4.message, _commit_files("TD-CMT-4"), c4.authored)
        _ensure_pr(w, repo, prs["TD-PR-2"])
        _ensure_pr(w, repo, prs["TD-PR-3"])
        _git(w, "fetch", "-q", "origin")
        _git(w, "reset", "-q", "--hard", "origin/main")
        _tag_s0(w)
    # 닫힘 상태와 마일스톤 닫기(시각은 지금이 된다. 시험은 원천 값과 비교한다)
    have = _all_issue_numbers(repo)
    for issue in d.GITHUB_ISSUES_CON1:
        if issue.closed and have[issue.number]["state"] != "closed":
            _gh(
                "PATCH",
                f"repos/{repo}/issues/{issue.number}",
                {"state": "closed", "state_reason": "completed"},
            )
    for m in (m for m in d.MILESTONES if m.connection == "TD-CON-1" and m.closed):
        cur = _gh("GET", f"repos/{repo}/milestones/{m.number}")
        if cur["state"] != "closed":
            _gh("PATCH", f"repos/{repo}/milestones/{m.number}", {"state": "closed"})


# ---------------------------------------------------------------- TD-CON-3


def seed_con3() -> None:
    repo = REPOS["TD-CON-3"]
    w4 = d.GITHUB_ISSUES_CON3[0]
    have = _all_issue_numbers(repo)
    if w4.number not in have:
        # #1~#3 을 만들었다 지운다. 지운 번호는 다시 쓰이지 않아 W4 가 #4 가 된다
        n = max(have) if have else 0
        while n < w4.number - 1:
            made = _gh(
                "POST", f"repos/{repo}/issues", {"title": "자리 채움(곧 지움)", "body": ""}
            )
            n = made["number"]
            r = subprocess.run(
                ["gh", "issue", "delete", str(n), "--repo", repo, "--yes"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if r.returncode:
                raise LiveSeedError(f"자리 채움 이슈 #{n} 삭제 실패: {r.stderr.strip()[:200]}")
        made = _gh("POST", f"repos/{repo}/issues", {"title": w4.title, "body": w4.body or ""})
        if made["number"] != w4.number:
            raise LiveSeedError(f"TD-ISS-W4 번호 {made['number']} (기대 {w4.number})")
    elif have[w4.number]["title"] != w4.title:
        raise LiveSeedError(f"TD-ISS-W4: #{w4.number} 제목이 다르다")
    with _clone(repo) as w:
        cw = next(c for c in d.COMMITS if c.tid == "TD-CMT-W1")
        _ensure_main_commit(w, cw.message, _commit_files("TD-CMT-W1"), cw.authored)
        _tag_s0(w)


# ---------------------------------------------------------------- 대응표


def build_map() -> dict:
    """원천에서 TD-ID → 실제 번호·SHA 를 읽는다(gh 로그인으로). 토큰·개인정보는 담지 않는다."""
    out: dict[str, Any] = {"repos": dict(REPOS), "tag_s0": TAG_S0}
    for con, repo in REPOS.items():
        with _clone(repo) as w:
            subj = _subjects(w, TAG_S0)
            s0_head = _git(w, "rev-parse", TAG_S0).strip()
            wbs_blob = (
                _git(w, "rev-parse", f"{TAG_S0}:{WBS_PATH}").strip()
                if con == "TD-CON-1"
                else None
            )
        commits = {
            c.tid: subj[c.message]
            for c in d.COMMITS
            if c.connection == con and c.state == "S0"
        }
        entry: dict[str, Any] = {"s0_head": s0_head, "commits": commits}
        issues = d.GITHUB_ISSUES_CON1 if con == "TD-CON-1" else d.GITHUB_ISSUES_CON3
        entry["issues"] = {i.tid: i.number for i in issues}
        if con == "TD-CON-1":
            entry["commits"]["TD-SETUP-1"] = subj[SETUP_MESSAGE]
            for pr_tid, (_, cmt, msg, _a) in PR_HEADS.items():
                if not cmt:
                    entry["commits"][f"{pr_tid}-HEAD"] = subj[msg]
            entry["pulls"] = {p.tid: p.number for p in d.PULL_REQUESTS_CON1}
            entry["milestones"] = {
                m.tid: m.number for m in d.MILESTONES if m.connection == "TD-CON-1"
            }
            entry["wbs_blob_s0"] = wbs_blob
            entry["files_s0"] = [WBS_PATH, DESIGN_DOC_PATH] + sorted(
                {p for c in d.COMMITS if c.connection == con and c.state == "S0" for p in c.files}
                | {p for p in d.PULL_REQUESTS_CON1 for p in p.files}
            )
        out[con] = entry
    return out


def write_map(m: dict) -> Path:
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return MAP_PATH


def load_map() -> dict | None:
    if not MAP_PATH.exists():
        return None
    m = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    return m if m.get("repos") == REPOS else None


def seed() -> dict:
    """두 저장소를 S0 로 채우고 대응표를 쓴다. 이미 있으면 건너뛴다."""
    if not gh_available():
        raise LiveSeedError("gh CLI 로그인이 필요하다(쓰기는 gh 로만 한다)")
    tmp = _files_dir()
    try:
        seed_con1(tmp)
        seed_con3()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    m = build_map()
    write_map(m)
    return m


# ---------------------------------------------------------------- S0 ↔ S1


def _state(w: Path) -> str:
    """S0 = 파일 내용이 td-s0 와 같다. S1 = 설계서 파일이 있고 WBS 가 다르다. 그 밖은 섞임."""
    has_docx = bool(_git(w, "ls-files", "--", DESIGN_FILE_PATH).strip())
    wbs = _git(w, "rev-parse", f"HEAD:{WBS_PATH}").strip()
    wbs0 = _git(w, "rev-parse", f"{TAG_S0}:{WBS_PATH}").strip()
    if not has_docx and wbs == wbs0:
        return "S0"
    if has_docx and wbs != wbs0:
        return "S1"
    return "mixed"


def state() -> str:
    with _clone(REPOS["TD-CON-1"]) as w:
        return _state(w)


def to_s1() -> dict[str, str]:
    """TD-CON-1 을 S1 로: TD-CMT-2(설계서 파일), WBS 3.2 85% 커밋을 push 한다.

    저자 시각은 IM-005A 값, 커미터 시각은 지금이다. 증분 수집의 since 필터는 커미터 시각을 보므로
    지금으로 둬야 다음 회차가 이 커밋을 읽는다."""
    if not gh_available():
        raise LiveSeedError("gh CLI 로그인이 필요하다")
    tmp = _files_dir()
    try:
        made = files.make_all(tmp)
        with _clone(REPOS["TD-CON-1"]) as w:
            st = _state(w)
            if st != "S0":
                raise LiveSeedError(f"저장소가 S0 가 아니다({st}). restore_s0() 를 먼저 돌린다")
            c2 = next(c for c in d.COMMITS if c.tid == "TD-CMT-2")
            now = _now_git()
            sha2 = _commit(
                w, c2.message, {DESIGN_FILE_PATH: made["TD-DOC-3"].read_bytes()}, c2.authored, now
            )
            sha_wbs = _commit(
                w,
                S1_WBS_MESSAGE,
                {WBS_PATH: made["TD-DOC-6-S1"].read_bytes()},
                S1_WBS_AUTHORED,
                now,
            )
            _git(w, "push", "-q", "origin", "main")
            wbs_blob = _git(w, "rev-parse", f"HEAD:{WBS_PATH}").strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"TD-CMT-2": sha2, "TD-WBS-S1": sha_wbs, "head": sha_wbs, "wbs_blob": wbs_blob}


def restore_s0() -> str | None:
    """파일 내용을 td-s0 로 되돌리는 커밋을 push 한다. 이미 S0 면 None."""
    if not gh_available():
        raise LiveSeedError("gh CLI 로그인이 필요하다")
    with _clone(REPOS["TD-CON-1"]) as w:
        if _state(w) == "S0":
            return None
        _git(w, "checkout", "-q", TAG_S0, "--", WBS_PATH)
        if _git(w, "ls-files", "--", DESIGN_FILE_PATH).strip():
            _git(w, "rm", "-q", "--", DESIGN_FILE_PATH)
        now = _now_git()
        _git(
            w,
            "commit", "-q", "-m", RESTORE_MESSAGE,
            env={"GIT_AUTHOR_DATE": now, "GIT_COMMITTER_DATE": now},
        )  # fmt: skip
        _git(w, "push", "-q", "origin", "main")
        return _git(w, "rev-parse", "HEAD").strip()


# ---------------------------------------------------------------- 원천 읽기(읽기 전용 토큰)


def read_token() -> str:
    return os.environ.get(TOKEN_ENV, "")


class Source:
    """원천 비교용 읽기. 시험이 AX Link 와 같은 읽기 전용 토큰으로 GitHub API 를 직접 본다."""

    def __init__(self, token: str) -> None:
        self._c = httpx.Client(
            base_url=API,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def close(self) -> None:
        self._c.close()

    def get(self, path: str, **params: Any) -> Any:
        res = self._c.get(path, params=params or None)
        res.raise_for_status()
        return res.json()

    def pages(self, path: str, **params: Any) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            batch = self.get(path, per_page=100, page=page, **params)
            out += batch
            if len(batch) < 100:
                return out
            page += 1

    def issues(self, repo: str) -> list[dict]:
        rows = self.pages(f"/repos/{repo}/issues", state="all")
        return [r for r in rows if "pull_request" not in r]

    def pulls(self, repo: str) -> list[dict]:
        return self.pages(f"/repos/{repo}/pulls", state="all")

    def commits(self, repo: str) -> list[dict]:
        return self.pages(f"/repos/{repo}/commits")

    def milestones(self, repo: str) -> list[dict]:
        return self.pages(f"/repos/{repo}/milestones", state="all")

    def tree_paths(self, repo: str) -> list[str]:
        body = self.get(f"/repos/{repo}/git/trees/HEAD", recursive="1")
        return sorted(e["path"] for e in body["tree"] if e["type"] == "blob")

    def snapshot(self, repo: str) -> dict:
        """수집 전후 비교용. 원천에 쓰기가 있었으면 이 값이 바뀐다."""
        info = self.get(f"/repos/{repo}")
        return {
            "pushed_at": info.get("pushed_at"),
            "default_branch": info.get("default_branch"),
            "issues": sorted(
                (i["number"], i["state"], i["updated_at"], i["comments"], len(i["labels"]))
                for i in self.issues(repo)
            ),
            "pulls": sorted(
                (p["number"], p["state"], p["updated_at"], p["merged_at"] or "")
                for p in self.pulls(repo)
            ),
            "commits": [c["sha"] for c in self.commits(repo)],
            "milestones": sorted(
                (m["number"], m["state"], m["updated_at"], m["open_issues"], m["closed_issues"])
                for m in self.milestones(repo)
            ),
            "labels": sorted(lb["name"] for lb in self.pages(f"/repos/{repo}/labels")),
            "branches": sorted(b["name"] for b in self.pages(f"/repos/{repo}/branches")),
            "tree": self.tree_paths(repo),
        }


def _main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "seed":
        m = seed()
        print(f"S0 시드 끝. 대응표 {MAP_PATH}")
        print(json.dumps({k: v for k, v in m.items() if k != "repos"}, ensure_ascii=False))
    elif cmd == "s1":
        print(json.dumps(to_s1(), ensure_ascii=False))
    elif cmd == "restore":
        sha = restore_s0()
        print("이미 S0" if sha is None else f"S0 로 되돌림: {sha}")
    elif cmd == "status":
        print(f"TD-CON-1 {REPOS['TD-CON-1']}: {state()}")
    else:
        print("사용: python -m tests.fixtures.im009.live_github seed|s1|restore|status")
        return 2
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv))
