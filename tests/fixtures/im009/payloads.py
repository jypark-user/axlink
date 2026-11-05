"""IM-009 도메인 값(data.py)을 도구 원시 응답 꼴로 바꾼다.

GitHub·Redmine 커넥터가 저장하는 raw_artifact 의 payload 와 같은 키만 쓴다
(app/standard/mapping.py · mapping_redmine.py · trace_rules.py 가 읽는 키 기준).
실연동이 아닐 때 이 재생 자료로 S0 를 만든다. 결과 기록에는 「재생」으로 적는다.
"""

from __future__ import annotations

import base64
from pathlib import Path

from tests.fixtures.im009 import data as d

REDMINE_STATUS = {
    "신규": {"id": 1, "name": "신규", "is_closed": False},
    # IM-009 는 「진행중」으로 적지만 Redmine 기본 상태 이름은 「진행」이다. 원천 어휘를 쓴다
    "진행중": {"id": 2, "name": "진행", "is_closed": False},
    "해결": {"id": 3, "name": "해결", "is_closed": False},
    "종료": {"id": 5, "name": "종료", "is_closed": True},
}
REDMINE_TRACKER_ID = {"일감": 1, "리스크": 2, "결함": 3}
REDMINE_PRIORITY_ID = {"낮음": 1, "보통": 2, "높음": 3, "긴급": 4}
REDMINE_RELATION = {"follows": "follows", "precedes": "precedes"}

GITHUB_UPDATED = "2026-09-10T00:00:00Z"
GITHUB_CREATED = "2026-03-10T00:00:00Z"


def _iso(day) -> str | None:
    return f"{day.isoformat()}T09:00:00Z" if day else None


# ---------------------------------------------------------------- Redmine


def redmine_issue(
    issue: d.RedmineIssue,
    state: str,
    base_url: str,
    by_tid: dict[str, d.RedmineIssue],
    versions: dict[str, int],
) -> tuple[str, dict]:
    status = issue.status_s1 if state == "S1" else issue.status_s0
    custom = []
    if issue.req_id:
        custom.append({"id": 1, "name": "요구사항 ID", "value": issue.req_id})
    relations = []
    if issue.relation:
        target, kind = issue.relation
        relations.append(
            {
                "id": 1000 + issue.number,
                "issue_id": issue.number,
                "issue_to_id": by_tid[target].number,
                "relation_type": REDMINE_RELATION[kind],
            }
        )
    closed_on = _iso(issue.due) if status in ("종료",) else None
    payload = {
        "id": issue.number,
        "project": {"id": 1, "identifier": "citizen-portal"},
        "tracker": {"id": REDMINE_TRACKER_ID[issue.tracker], "name": issue.tracker},
        "status": REDMINE_STATUS[status],
        "priority": {"id": REDMINE_PRIORITY_ID[issue.priority], "name": issue.priority},
        "author": {"id": 10, "name": "박피엠"},
        "assigned_to": {"id": 11, "name": issue.assignee},
        "subject": issue.subject,
        "description": f"{issue.subject} 작업 내용",
        "start_date": issue.start.isoformat() if issue.start else None,
        "due_date": issue.due.isoformat() if issue.due else None,
        "done_ratio": issue.done_ratio if issue.done_ratio is not None else 0,
        "custom_fields": custom,
        "relations": relations,
        "created_on": "2026-03-05T00:00:00Z",
        "updated_on": "2026-09-20T00:00:00Z"
        if state == "S1" and issue.status_s0 != status
        else "2026-09-01T00:00:00Z",
        "closed_on": closed_on,
    }
    if issue.version:
        payload["fixed_version"] = {"id": versions.get(issue.version, 0), "name": issue.version}
    return str(issue.number), payload


def redmine_version(ms: d.Milestone, base_url: str) -> tuple[str, dict]:
    payload = {
        "id": ms.number,
        "name": ms.name,
        "status": "closed" if ms.closed else "open",
        "due_date": ms.due.isoformat() if ms.due else None,
        "created_on": "2026-03-05T00:00:00Z",
        "updated_on": _iso(ms.closed_on) or "2026-09-01T00:00:00Z",
        "project": {"id": 1, "name": "시민포털"},
    }
    return f"version:{ms.number}", payload


def redmine_trackers() -> list[tuple[str, dict]]:
    return [(f"tracker:{i}", {"id": i, "name": n}) for n, i in REDMINE_TRACKER_ID.items()]


# ---------------------------------------------------------------- GitHub


def github_issue(
    issue: d.GithubIssue, repo: str, milestones: dict[str, d.Milestone]
) -> tuple[str, dict]:
    ms = None
    if issue.milestone:
        m = milestones[issue.milestone]
        ms = _github_milestone_body(m, repo)
    payload = {
        "number": issue.number,
        "title": issue.title,
        "body": issue.body,
        "labels": [{"name": n} for n in issue.labels],
        "state": "closed" if issue.closed else "open",
        "assignee": {"login": "parkpm"},
        "milestone": ms,
        "created_at": GITHUB_CREATED,
        "updated_at": GITHUB_UPDATED,
        "closed_at": "2026-06-01T00:00:00Z" if issue.closed else None,
        "html_url": f"https://github.com/{repo}/issues/{issue.number}",
    }
    return f"issue:{issue.number}", payload


def _github_milestone_body(ms: d.Milestone, repo: str) -> dict:
    return {
        "number": ms.number,
        "title": ms.name,
        "state": "closed" if ms.closed else "open",
        "due_on": f"{ms.due.isoformat()}T07:00:00Z" if ms.due else None,
        "closed_at": _iso(ms.closed_on),
        "updated_at": GITHUB_UPDATED,
        "html_url": f"https://github.com/{repo}/milestone/{ms.number}",
    }


def github_milestone(ms: d.Milestone, repo: str) -> tuple[str, dict]:
    return f"milestone:{ms.number}", _github_milestone_body(ms, repo)


def github_commit(c: d.Commit, repo: str) -> tuple[str, dict]:
    payload = {
        "sha": c.sha,
        "commit": {
            "message": c.message,
            "author": {"name": "박피엠", "date": c.authored},
            "committer": {"name": "박피엠", "date": c.authored},
        },
        "author": {"login": "parkpm"},
        "parents": [{"sha": "0" * 40}],
        "files": [{"filename": f} for f in c.files],
        "html_url": f"https://github.com/{repo}/commit/{c.sha}",
    }
    return f"commit:{c.sha}", payload


def github_pull_request(pr: d.PullRequest, repo: str) -> tuple[str, dict]:
    payload = {
        "number": pr.number,
        "title": pr.title,
        "body": pr.body,
        "state": "closed" if pr.merged else "open",
        "merged_at": "2026-08-20T00:00:00Z" if pr.merged else None,
        "created_at": "2026-08-15T00:00:00Z",
        "updated_at": GITHUB_UPDATED,
        "user": {"login": "parkpm"},
        "head": {"ref": f"feature/pr-{pr.number}"},
        "files": [{"filename": f} for f in pr.files],
        "html_url": f"https://github.com/{repo}/pull/{pr.number}",
    }
    return f"pull_request:{pr.number}", payload


def github_file(path: str, content: bytes, sha: str, repo: str) -> tuple[str, dict]:
    payload = {
        "path": path,
        "sha": sha,
        "size": len(content),
        "htmlUrl": f"https://github.com/{repo}/blob/main/{path}",
        "content": base64.b64encode(content).decode("ascii"),
    }
    return f"file:{path}", payload


def github_tree(paths: list[str], head_sha: str, repo: str) -> tuple[str, dict]:
    payload = {
        "sha": head_sha,
        "commit": head_sha,
        "truncated": False,
        "paths": paths,
        "blobs": {p: f"blob{abs(hash(p)) % 10**8:08d}" for p in paths},
        "html_url": f"https://github.com/{repo}/tree/{head_sha}",
    }
    return "tree:HEAD", payload


def github_design_doc(path: str, text: str, head_sha: str, repo: str) -> tuple[str, dict]:
    payload = {
        "repo": repo,
        "path": path,
        "commit_sha": head_sha,
        "blob_sha": f"blob{abs(hash(path)) % 10**8:08d}",
        "html_url": f"https://github.com/{repo}/blob/{head_sha}/{path}",
        "text": text,
        "deleted": False,
    }
    return f"doc:{path}", payload


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
