"""도구 원천 재생기. GitHub·Redmine 어댑터의 모듈 함수(verify·fetch_items·fetch_file)를 바꿔
IM-009 자료를 「원천」처럼 돌려준다. 실연동이 없을 때 수집 시나리오(UC-010·011·012)를 돈다.

장애 주입(Faults)으로 인증 실패·권한 결손·네트워크 오류·중간 끊김을 흉내 낸다. 재생이므로
기록 모드는 `replay` 다. 실연동 검증을 대신하지 않는다(Goal 2절).
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.common import errors
from app.integration.adapter import github_connector as gh
from app.integration.adapter import redmine_connector as rm
from app.integration.port import ProbeResult
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import payloads

WBS_PATH = "docs/00-management/WBS.xlsx"
DESIGN_DOC_PATH = "docs/20-design/설계-민원조회.md"


@dataclass
class Faults:
    auth_fail: bool = False  # 토큰 무효: 모든 호출 TOOL_AUTH
    denied_kinds: set[str] = field(default_factory=set)  # 이 종류만 TOOL_AUTH
    unreachable: bool = False  # 네트워크 오류: TOOL_UNREACHABLE
    rest_disabled: bool = False  # Redmine REST 비활성(403 과 같게 처리됨)
    cut_after: int | None = None  # 이슈 N건 뒤 응답 끊김(TOOL_UNREACHABLE)
    drop_issue_numbers: set[int] = field(default_factory=set)  # 원천에서 사라진 이슈
    tracker_rename: dict[str, str] = field(default_factory=dict)  # 트래커 이름 변형(UC-012-S01)
    calls: list[tuple[str, str, str]] = field(default_factory=list)  # (tool, kind, since)


@dataclass
class ReplaySource:
    state: str = "S0"
    files: dict[str, Path] = field(default_factory=dict)
    faults: Faults = field(default_factory=Faults)

    # ------------------------------------------------------------ 자료
    def _github_items(self, target: str, kind: str) -> list[tuple[str, dict]]:
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
                return [
                    payloads.github_commit(c, target)
                    for c in d.COMMITS
                    if c.connection == "TD-CON-1" and (self.state == "S1" or c.state == "S0")
                ]
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
                return [payloads.github_tree(paths, head, target)]
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
            # 실제 Redmine 은 REST 가 꺼져 있으면 403 을 준다. 어댑터는 이를 TOOL_NOT_FOUND 로 읽는다  # noqa: E501
            raise errors.ApiError(
                404, "TOOL_NOT_FOUND", "프로젝트를 찾을 수 없거나 API 키에 접근 권한이 없습니다."
            )
        if kind and kind in f.denied_kinds:
            raise errors.ApiError(403, "TOOL_AUTH", f"{kind} 읽기 권한이 없습니다.")

    def verify(self, tool: str, kinds: tuple[str, ...]):
        def _verify(base_url: str, target: str, secret: str) -> ProbeResult:
            self._check(tool, None)
            readable = [k for k in kinds if k not in self.faults.denied_kinds]
            denied = [k for k in kinds if k in self.faults.denied_kinds]
            return ProbeResult(target, readable, denied)

        return _verify

    def fetch_items(self, tool: str):
        def _fetch(
            base_url, target, secret, kind, per_page, max_pages, since=None, until=None
        ) -> Generator[tuple[str, dict], None, None]:
            self.faults.calls.append(
                (tool, kind, since.isoformat() if isinstance(since, datetime) else "")
            )
            self._check(tool, kind)
            items = (
                self._github_items(target, kind)
                if tool == "GITHUB"
                else self._redmine_items(target, kind)
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
            if tool != "GITHUB" or target != d.CONNECTIONS["TD-CON-1"].target:
                return None
            if path == WBS_PATH:
                key = "TD-DOC-6-S1" if self.state == "S1" else "TD-DOC-6"
                sha = d.WBS_FILE_COMMIT_S1 if self.state == "S1" else d.WBS_FILE_COMMIT_S0
                return payloads.github_file(path, self.files[key].read_bytes(), sha, target)[1]
            if path == DESIGN_DOC_PATH:
                text = self.files["TD-DOC-R1"].read_bytes()
                return payloads.github_file(path, text, "blob" + "0" * 36, target)[1]
            return None

        return _fetch_file


def install(monkeypatch, source: ReplaySource) -> ReplaySource:
    """두 어댑터의 모듈 함수를 재생기로 바꾼다. 클래스 메서드가 모듈 함수를 부르므로 이것으로 충분하다."""  # noqa: E501
    monkeypatch.setattr(gh, "verify", source.verify("GITHUB", tuple(gh.ITEM_PATHS)))
    monkeypatch.setattr(gh, "fetch_items", source.fetch_items("GITHUB"))
    monkeypatch.setattr(gh, "fetch_file", source.fetch_file("GITHUB"))
    monkeypatch.setattr(rm, "verify", source.verify("REDMINE", rm.ITEM_KINDS))
    monkeypatch.setattr(rm, "fetch_items", source.fetch_items("REDMINE"))
    monkeypatch.setattr(rm, "fetch_file", source.fetch_file("REDMINE"))
    return source
