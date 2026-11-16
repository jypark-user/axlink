"""도구 원천 재생기. GitHub·Redmine 어댑터의 모듈 함수(verify·fetch_items·fetch_file)를 바꿔
IM-009 자료를 「원천」처럼 돌려준다. 실연동이 없을 때 수집 시나리오(UC-010·011·012)를 돈다.

장애 주입(Faults)으로 인증 실패·권한 결손·네트워크 오류·중간 끊김을 흉내 낸다. 재생이므로
기록 모드는 `replay` 다. 실연동 검증을 대신하지 않는다(Goal 2절).
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.common import errors
from app.integration.adapter import github_connector as gh
from app.integration.adapter import redmine_connector as rm
from app.integration.port import PageResult, ProbeResult
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import payloads

# 원격 대상(5174)을 시험할 때 그 서버가 부를 재생 서버(replay_server). 없으면 프로세스 안 재생
REPLAY_URL = os.environ.get("AXLINK_REPLAY_URL")
WBS_PATH = "docs/00-management/WBS.xlsx"


def tool_base(tool: str, default: str) -> str:
    """시험이 만드는 연결의 주소. 원격 대상이면 재생 서버, 아니면 원래 주소(어댑터를 바꿔 쓴다)."""
    return f"{REPLAY_URL.rstrip('/')}/{tool.lower()}" if REPLAY_URL else default
DESIGN_DOC_PATH = "docs/20-design/설계-민원조회.md"
# 대량 이슈 변형(UC-011-S08)을 내는 저장소. 이슈마다 갱신 시각이 1분씩 늘어난다
BULK_TARGET = "replay/bulk-issues"
BULK_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _bulk_issue(n: int, target: str) -> tuple[str, dict]:
    stamp = (BULK_BASE + timedelta(minutes=n)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"issue:{n}", {
        "number": n, "title": f"대량 이슈 {n}", "body": "", "labels": [], "state": "open",
        "assignee": None, "milestone": None, "created_at": "2026-01-01T00:00:00Z",
        "updated_at": stamp, "closed_at": None,
        "html_url": f"https://github.com/{target}/issues/{n}",
    }


@dataclass
class Faults:
    auth_fail: bool = False  # 토큰 무효: 모든 호출 TOOL_AUTH
    denied_kinds: set[str] = field(default_factory=set)  # 이 종류만 TOOL_AUTH
    unreachable: bool = False  # 네트워크 오류: TOOL_UNREACHABLE
    rest_disabled: bool = False  # Redmine REST 비활성(403 과 같게 처리됨)
    cut_after: int | None = None  # 이슈 N건 뒤 응답 끊김(TOOL_UNREACHABLE)
    drop_issue_numbers: set[int] = field(default_factory=set)  # 원천에서 사라진 이슈
    tracker_rename: dict[str, str] = field(default_factory=dict)  # 트래커 이름 변형(UC-012-S01)
    extra_commits: list[d.Commit] = field(default_factory=list)  # 변형 커밋 추가(UC-021-S08)
    commit_message: dict[str, str] = field(default_factory=dict)  # sha → 바뀐 메시지(UC-022-S02)
    wbs_variant: str | None = None  # 저장소 WBS 를 다른 파일로(TD-WBS-SUM·NOHEAD·V2·L2·MISS)
    wbs_sha: str = "ab01ab01ab01ab01ab01ab01ab01ab01ab01ab01"  # 변형 파일을 담은 커밋 해시
    wbs_targets: set[str] = field(default_factory=set)  # WBS 를 서빙할 추가 저장소(TD-PRJ-9 연결)
    extra_tree_paths: list[str] = field(default_factory=list)  # 트리에 더할 경로(UC-031-S03)
    serve_design_file: bool = False  # 설정 경로 설계서 파일(DESIGN_FILE_PATH) 제공(UC-031-S02)
    delay_seconds: float = 0.0  # 이슈 목록 응답을 이만큼 늦춘다(장시간 응답, UC-011-S06)
    bulk_issues: int = 0  # BULK_TARGET 의 이슈 건수(상한 초과 변형, UC-011-S08)
    drop_done_ratio: bool = False  # Redmine 이슈가 진척도를 하나도 주지 않는다(DEC-17 경계)
    calls: list[tuple[str, str, str]] = field(default_factory=list)  # (tool, kind, since)




def restore_faults(state: str = "S0") -> Faults:
    """원천 WBS 를 그 상태의 내용으로 되돌린다. 실제 되돌림 커밋처럼 같은 blob(같은 sha)으로 낸다.

    예전에는 제품 결함 DEF-V033(예전 버전 행에 다시 insert → 500)을 피하려고 새 해시로 냈다.
    고친 뒤로는 되돌림이 그 판을 현행으로 되살리는지 시나리오의 상태 복원이 같이 확인한다.
    """
    if state == "S1":
        return Faults(wbs_variant="TD-DOC-6-S1", wbs_sha=d.WBS_FILE_COMMIT_S1)
    return Faults(wbs_variant="TD-DOC-6", wbs_sha=d.WBS_FILE_COMMIT_S0)


@dataclass
class ReplaySource:
    state: str = "S0"
    files: dict[str, Path] = field(default_factory=dict)
    faults: Faults = field(default_factory=Faults)
    # 마지막으로 복원한 WBS(자료 키, 커밋 해시). 변형이 없을 때 이것을 낸다
    wbs_current: tuple[str, str] | None = None

    def calls(self) -> list[tuple[str, str, str]]:
        """수집 호출(도구, 종류, since). 원격이면 서버가 받은 것이다."""
        return list(self.faults.calls)

    # ------------------------------------------------------------ 자료
    def _github_items(self, target: str, kind: str) -> list[tuple[str, dict]]:
        if target == BULK_TARGET:
            if kind == "issue":
                return [_bulk_issue(n, target) for n in range(1, self.faults.bulk_issues + 1)]
            return []
        ms = {m.name: m for m in d.MILESTONES if m.connection == "TD-CON-1"}
        if target == d.CONNECTIONS["TD-CON-1"].target:
            issues = [
                i for i in d.GITHUB_ISSUES_CON1 if i.number not in self.faults.drop_issue_numbers
            ]
            if kind == "issue":
                return [payloads.github_issue(i, target, ms) for i in issues]
            if kind == "milestone":
                return [payloads.github_milestone(m, target) for m in ms.values()]
            if kind == "commit":
                commits = [
                    c
                    for c in d.COMMITS
                    if c.connection == "TD-CON-1" and (self.state == "S1" or c.state == "S0")
                ]
                commits += [c for c in self.faults.extra_commits if c.connection == "TD-CON-1"]
                out = []
                for c in commits:
                    eid, payload = payloads.github_commit(c, target)
                    if c.sha in self.faults.commit_message:
                        payload["commit"]["message"] = self.faults.commit_message[c.sha]
                    out.append((eid, payload))
                return out
            if kind == "pull_request":
                return [payloads.github_pull_request(p, target) for p in d.PULL_REQUESTS_CON1]
            if kind == "tree":
                head = (
                    "1b2c3d4e5f6a70811b2c3d4e5f6a70811b2c3d4e"
                    if self.state == "S1"
                    else "9a8b7c6d5e4f30219a8b7c6d5e4f30219a8b7c6d"
                )
                paths = [WBS_PATH, DESIGN_DOC_PATH, "src/auth/login.py"]
                if self.state == "S1":
                    paths.append("docs/20-design/SW설계서_v0.9.docx")
                paths += self.faults.extra_tree_paths
                return [payloads.github_tree(paths, head, target)]
        if target in self.faults.wbs_targets:
            if kind == "tree":
                return [payloads.github_tree([WBS_PATH], "9" * 40, target)]
            return []
        if target == d.CONNECTIONS["TD-CON-3"].target:
            if kind == "issue":
                return [payloads.github_issue(i, target, {}) for i in d.GITHUB_ISSUES_CON3]
            if kind == "commit":
                return [
                    payloads.github_commit(c, target)
                    for c in d.COMMITS
                    if c.connection == "TD-CON-3"
                ]
            if kind == "tree":
                return [payloads.github_tree(["web/bundle.js"], "e" * 40, target)]
        return []

    def _redmine_items(self, target: str, kind: str) -> list[tuple[str, dict]]:
        if target == d.CONNECTIONS["TD-CON-2"].target:
            issues, mss = (
                d.REDMINE_ISSUES_PRJ1,
                [m for m in d.MILESTONES if m.connection == "TD-CON-2"],
            )
            base = d.CONNECTIONS["TD-CON-2"].base_url
        elif target == d.CONNECTIONS["TD-CON-4"].target:
            issues, mss = d.REDMINE_ISSUES_PRJ2, d.MILESTONES_PRJ2
            base = d.CONNECTIONS["TD-CON-4"].base_url
        else:
            return []
        by_tid = {i.tid: i for i in issues}
        ver = {m.name: m.number for m in mss}
        if kind == "issue":
            out = []
            for i in issues:
                eid, p = payloads.redmine_issue(i, self.state, base, by_tid, ver)
                if self.faults.drop_done_ratio:
                    p.pop("done_ratio", None)
                name = p["tracker"]["name"]
                if name in self.faults.tracker_rename:
                    p["tracker"] = {**p["tracker"], "name": self.faults.tracker_rename[name]}
                out.append((eid, p))
            return out
        if kind == "version":
            return [payloads.redmine_version(m, base) for m in mss]
        if kind == "tracker":
            trackers = payloads.redmine_trackers()
            if self.faults.tracker_rename:
                trackers = [
                    (e, {**p, "name": self.faults.tracker_rename.get(p["name"], p["name"])})
                    for e, p in trackers
                ]
            return trackers
        return []

    # ------------------------------------------------------------ 어댑터 흉내
    def _check(self, tool: str, kind: str | None) -> None:
        f = self.faults
        if f.unreachable:
            raise errors.ApiError(502, "TOOL_UNREACHABLE", f"{tool} 서버에 연결할 수 없습니다.")
        if f.auth_fail:
            raise errors.ApiError(401, "TOOL_AUTH", "토큰이 유효하지 않습니다.")
        if f.rest_disabled and tool == "REDMINE":
            # 실제 Redmine 은 REST 가 꺼져 있으면 어느 API 든 403 이다. 어댑터는 자기 정보 조회까지
            # 403 이면 REST 비활성으로 읽는다(DEF-V014). 프로세스 안 재생기는 그 결과를 낸다
            raise errors.ApiError(403, "TOOL_REST_DISABLED", rm.REST_DISABLED)
        if kind and kind in f.denied_kinds:
            raise errors.ApiError(403, "TOOL_AUTH", f"{kind} 읽기 권한이 없습니다.")

    def verify(self, tool: str, kinds: tuple[str, ...]):
        def _verify(base_url: str, target: str, secret: str) -> ProbeResult:
            self._check(tool, None)
            readable = [k for k in kinds if k not in self.faults.denied_kinds]
            denied = [k for k in kinds if k in self.faults.denied_kinds]
            return ProbeResult(target, readable, denied)

        return _verify

    def fetch_items(self, tool: str, emulate_cap: bool = False):
        """emulate_cap: 프로세스 안 재생은 어댑터의 쪽 넘김을 거치지 않으니, 대량 변형에 한해
        회차 상한(per_page × max_pages)과 이어 읽을 자리를 어댑터처럼 돌려준다. 재생 서버는
        실제 어댑터가 쪽을 넘기므로 쓰지 않는다."""
        def _fetch(
            base_url, target, secret, kind, per_page, max_pages, since=None, until=None
        ) -> Generator[tuple[str, dict], None, PageResult | None]:
            self.faults.calls.append(
                (tool, kind, since.isoformat() if isinstance(since, datetime) else "")
            )
            self._check(tool, kind)
            if kind == "issue" and self.faults.delay_seconds:
                time.sleep(self.faults.delay_seconds)
            items = (
                self._github_items(target, kind)
                if tool == "GITHUB"
                else self._redmine_items(target, kind)
            )
            if target == BULK_TARGET and kind == "issue":
                # GitHub 처럼 since(이상)로 거르고 갱신 오름차순으로 낸다
                if isinstance(since, datetime):
                    edge = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                    items = [(e, p) for e, p in items if p["updated_at"] >= edge]
                cap = per_page * max_pages
                if emulate_cap and len(items) > cap:
                    yield from items[:cap]
                    last = items[cap - 1][1]["updated_at"]
                    return PageResult(
                        truncated=True,
                        resume_since=datetime.fromisoformat(last.replace("Z", "+00:00")),
                    )
            for n, (eid, payload) in enumerate(items, 1):
                if (
                    kind == "issue"
                    and self.faults.cut_after is not None
                    and n > self.faults.cut_after
                ):
                    raise errors.ApiError(502, "TOOL_UNREACHABLE", "응답이 끊어졌습니다.")
                yield eid, payload
            return None

        return _fetch

    def fetch_file(self, tool: str):
        def _fetch_file(base_url, target, secret, path, ref=None):
            self._check(tool, None)
            allowed = {d.CONNECTIONS["TD-CON-1"].target, *self.faults.wbs_targets}
            if tool != "GITHUB" or target not in allowed:
                return None
            if path == "docs/20-design/SW설계서_v0.9.docx" and (
                self.state == "S1" or self.faults.serve_design_file
            ):
                return payloads.github_file(
                    path, self.files["TD-DOC-3"].read_bytes(), "d3d3d3d3" + "0" * 32, target
                )[1]
            if path == WBS_PATH:
                key = "TD-DOC-6-S1" if self.state == "S1" else "TD-DOC-6"
                sha = d.WBS_FILE_COMMIT_S1 if self.state == "S1" else d.WBS_FILE_COMMIT_S0
                if self.faults.wbs_variant:
                    key, sha = self.faults.wbs_variant, self.faults.wbs_sha
                elif self.wbs_current:
                    key, sha = self.wbs_current
                return payloads.github_file(path, self.files[key].read_bytes(), sha, target)[1]
            if path == DESIGN_DOC_PATH:
                text = self.files["TD-DOC-R1"].read_bytes()
                return payloads.github_file(path, text, "blob" + "0" * 36, target)[1]
            return None

        return _fetch_file


class RemoteReplay(ReplaySource):
    """재생 서버의 상태를 바꾸는 대역. 시험이 faults·state·wbs_current 를 바꾸면 서버에 보낸다.

    시험 쪽에서 만든 변형 파일(WBS 변형 등)은 서버에 없으니, 참조되는 자료 키를 먼저 올린다.
    """

    def __init__(self, url: str, source: ReplaySource) -> None:
        object.__setattr__(self, "_url", url.rstrip("/"))
        object.__setattr__(self, "_sent", set())
        object.__setattr__(self, "_ready", False)
        super().__init__(source.state, source.files, source.faults, source.wbs_current)
        object.__setattr__(self, "_ready", True)
        self._push()

    def __setattr__(self, name, value) -> None:
        object.__setattr__(self, name, value)
        if name in ("faults", "state", "wbs_current") and self._ready:
            self._push()

    def _upload(self, key: str | None) -> None:
        if not key or key in self._sent or key not in self.files:
            return
        res = httpx.put(f"{self._url}/_replay/files/{key}", content=self.files[key].read_bytes())
        res.raise_for_status()
        self._sent.add(key)

    def _push(self) -> None:
        f = self.faults
        self._upload(f.wbs_variant)
        self._upload(self.wbs_current[0] if self.wbs_current else None)
        body = asdict(f)
        body.pop("calls")
        for name in ("denied_kinds", "drop_issue_numbers", "wbs_targets"):
            body[name] = sorted(body[name]) if isinstance(body[name], set) else body[name]
        httpx.put(f"{self._url}/_replay/faults", json=body).raise_for_status()
        state = {"state": self.state, "wbs_current": list(self.wbs_current or []) or None}
        httpx.put(f"{self._url}/_replay/state", json=state).raise_for_status()

    def calls(self) -> list[tuple[str, str, str]]:
        """서버가 받은 수집 호출(도구, 종류, since)."""
        return [tuple(c) for c in httpx.get(f"{self._url}/_replay/calls").json()]


def install(monkeypatch, source: ReplaySource) -> ReplaySource:
    """두 어댑터의 모듈 함수를 재생기로 바꾼다. 클래스 메서드가 모듈 함수를 부르므로 이것으로 충분하다.

    AXLINK_REPLAY_URL 이 있으면 원격 대상이다. 어댑터를 바꾸지 않고 재생 서버의 상태를 맞춘다.
    """  # noqa: E501
    if REPLAY_URL:
        return RemoteReplay(REPLAY_URL, source)
    monkeypatch.setattr(gh, "verify", source.verify("GITHUB", tuple(gh.ITEM_PATHS)))
    monkeypatch.setattr(gh, "fetch_items", source.fetch_items("GITHUB", emulate_cap=True))
    monkeypatch.setattr(gh, "fetch_file", source.fetch_file("GITHUB"))
    monkeypatch.setattr(rm, "verify", source.verify("REDMINE", rm.ITEM_KINDS))
    monkeypatch.setattr(rm, "fetch_items", source.fetch_items("REDMINE"))
    monkeypatch.setattr(rm, "fetch_file", source.fetch_file("REDMINE"))
    return source
