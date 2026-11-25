"""도구 원천 재생 서버. IM-005A 자료를 GitHub·Redmine REST 응답 꼴로 HTTP 에 낸다.

프로세스 안 재생기(replay.install)는 시험 프로세스의 어댑터 함수를 바꾼다. 원격 서버(5174)에
시나리오를 돌리면 그 서버의 어댑터는 바뀌지 않는다. 이 서버는 같은 자료(ReplaySource)를 HTTP 로
내서, 5174 의 실제 어댑터 코드가 연결 주소로 이 서버를 부르게 한다.

연결 주소:
- GitHub:  http://<host>:<port>/github   (대상 = owner/repo)
- Redmine: http://<host>:<port>/redmine  (대상 = 프로젝트 식별자)

장애 주입과 상태(S0·S1)는 /_replay/* 로 바꾼다. 재생이므로 기록 모드는 `replay` 다.
실연동 검증을 대신하지 않는다(Goal 2절).

흉내가 실제와 다를 수 있는 곳:
- unreachable 은 연결 끊김이 아니라 502 응답이다. 어댑터는 둘 다 TOOL_UNREACHABLE 로 읽는다.
- rest_disabled 는 REST 를 끈 Redmine 의 모든 API 가 403 이라고 가정한다(DEF-V014, 실연동 확인 전).
- cut_after 는 끊긴 쪽을 502 로 낸다. 쪽 크기가 n 이하면 앞쪽은 받고 끊긴 쪽부터 실패한다.

실행: python -m tests.fixtures.im009.replay_server --port 18099 [--files <자료 폴더>]
"""

from __future__ import annotations

import argparse
import tempfile
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.common import errors
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import embed_proxy, replay_ollama
from tests.fixtures.im009 import files as fixture_files
from tests.fixtures.im009.replay import Faults, ReplaySource

GITHUB_KINDS = {"issues": "issue", "pulls": "pull_request", "commits": "commit",
                "milestones": "milestone"}


def _since(value: str | None) -> datetime | None:
    """요청의 since(ISO 8601, Z 포함)를 시각으로. 없거나 못 읽으면 None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _error(exc: errors.ApiError) -> Response:
    """재생기의 장애를 실제 도구가 줄 HTTP 상태로 옮긴다."""
    status = {
        "TOOL_AUTH": 401, "TOOL_NOT_FOUND": 403, "TOOL_REST_DISABLED": 403,
        "TOOL_UNREACHABLE": 502,
    }.get(exc.code, 500)
    if exc.code == "TOOL_AUTH" and exc.status == 403:
        status = 403  # 종류별 권한 결손
    return JSONResponse({"message": exc.message}, status_code=status)


def _faults_from(body: dict[str, Any]) -> Faults:
    known = {f.name for f in fields(Faults)}
    unknown = set(body) - known
    if unknown:
        raise ValueError(f"모르는 장애 항목: {sorted(unknown)}")
    args = dict(body)
    for name in ("denied_kinds", "drop_issue_numbers", "wbs_targets"):
        if name in args:
            args[name] = set(args[name])
    if "extra_commits" in args:
        args["extra_commits"] = [d.Commit(**{**c, "files": tuple(c["files"])})
                                 for c in args["extra_commits"]]
    args.pop("calls", None)
    return Faults(**args)


def create_app(source: ReplaySource) -> FastAPI:
    app = FastAPI(title="IM-005A 원천 재생")
    embed_proxy.mount(app)  # 5174 전용 임베딩 장애 주입(UC-070-S05·S07)
    app.include_router(replay_ollama.router)  # 대본 모델(원격 대상의 llm 시나리오)
    gh_items = source.fetch_items("GITHUB")
    rm_items = source.fetch_items("REDMINE")
    gh_file = source.fetch_file("GITHUB")

    def _list(fetch, target: str, kind: str) -> list[dict]:
        return [p for _, p in fetch("", target, "", kind, 10_000, 1)]

    # 프로세스 안 재생기와 같게 어느 대상이든 있다고 본다. 자료가 없는 대상은 빈 목록이다
    def _known_github(target: str) -> bool:
        return bool(target)

    def _known_redmine(target: str) -> bool:
        return bool(target)

    def _tree(target: str) -> dict | None:
        items = _list(gh_items, target, "tree")
        return items[0] if items else None

    # ------------------------------------------------------------ 조작
    @app.put("/_replay/state")
    def put_state(body: dict) -> dict:
        source.state = body.get("state", source.state)
        if "wbs_current" in body:
            cur = body["wbs_current"]
            source.wbs_current = tuple(cur) if cur else None
        return {"state": source.state, "wbs_current": source.wbs_current}

    @app.put("/_replay/faults")
    def put_faults(body: dict) -> Response:
        try:
            source.faults = _faults_from(body)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"message": str(exc)}, status_code=400)
        return JSONResponse({"ok": True})

    @app.put("/_replay/files/{key}")
    async def put_file(key: str, request: Request) -> dict:
        """시험 쪽에서 만든 변형 자료(WBS 변형 등)를 같은 키로 둔다."""
        folder = Path(tempfile.gettempdir()) / "im009-replay-upload"
        folder.mkdir(exist_ok=True)
        path = folder / f"{key}.bin"
        path.write_bytes(await request.body())
        source.files[key] = path
        return {"key": key, "size": path.stat().st_size}

    @app.get("/_replay/calls")
    def get_calls() -> list:
        return [list(c) for c in source.faults.calls]

    # ------------------------------------------------------------ GitHub
    @app.get("/github/repos/{owner}/{repo}")
    def gh_repo(owner: str, repo: str) -> Response:
        target = f"{owner}/{repo}"
        try:
            source._check("GITHUB", None)
        except errors.ApiError as exc:
            return _error(exc)
        if not _known_github(target):
            return JSONResponse({"message": "Not Found"}, status_code=404)
        return JSONResponse({"full_name": target})

    @app.get("/github/repos/{owner}/{repo}/git/trees/{ref}")
    def gh_tree(owner: str, repo: str, ref: str) -> Response:
        try:
            source._check("GITHUB", "tree")
            tree = _tree(f"{owner}/{repo}")
        except errors.ApiError as exc:
            return _error(exc)
        if tree is None:
            return JSONResponse({"message": "Git Repository is empty."}, status_code=409)
        return JSONResponse({
            "sha": tree["sha"],
            "truncated": tree["truncated"],
            "tree": [{"path": p, "type": "blob", "sha": tree["blobs"].get(p, "")}
                     for p in tree["paths"]],
        })

    @app.get("/github/repos/{owner}/{repo}/commits/{ident}")
    def gh_commit(owner: str, repo: str, ident: str, request: Request) -> Response:
        target = f"{owner}/{repo}"
        try:
            source._check("GITHUB", "commit")
            if ident == "HEAD" and "sha" in request.headers.get("accept", ""):
                tree = _tree(target)
                if tree is None:
                    return PlainTextResponse("", status_code=409)
                return PlainTextResponse(tree["commit"])
            found = next((c for c in _list(gh_items, target, "commit") if c["sha"] == ident), None)
        except errors.ApiError as exc:
            return _error(exc)
        if found is None:
            return JSONResponse({"message": "No commit found"}, status_code=404)
        return JSONResponse(found)

    @app.get("/github/repos/{owner}/{repo}/pulls/{number}/files")
    def gh_pull_files(owner: str, repo: str, number: int, page: int = 1) -> Response:
        try:
            source._check("GITHUB", "pull_request")
            prs = _list(gh_items, f"{owner}/{repo}", "pull_request")
        except errors.ApiError as exc:
            return _error(exc)
        pr = next((p for p in prs if p["number"] == number), None)
        if pr is None:
            return JSONResponse({"message": "Not Found"}, status_code=404)
        return JSONResponse(pr["files"] if page == 1 else [])

    @app.get("/github/repos/{owner}/{repo}/contents/{path:path}")
    def gh_contents(owner: str, repo: str, path: str, ref: str | None = None) -> Response:
        try:
            got = gh_file("", f"{owner}/{repo}", "", path, ref)
        except errors.ApiError as exc:
            return _error(exc)
        if got is None:
            return JSONResponse({"message": "Not Found"}, status_code=404)
        return JSONResponse({
            "type": "file", "path": got["path"], "sha": got["sha"], "size": got["size"],
            "html_url": got["htmlUrl"], "content": got["content"], "encoding": "base64",
        })

    @app.get("/github/repos/{owner}/{repo}/{kind}")
    def gh_list(owner: str, repo: str, kind: str, page: int = 1, per_page: int = 30,
                since: str | None = None) -> Response:
        if kind not in GITHUB_KINDS:
            return JSONResponse({"message": "Not Found"}, status_code=404)
        return _paged(gh_items, f"{owner}/{repo}", GITHUB_KINDS[kind], page - 1, per_page,
                      lambda batch: batch, _since(since))

    # ------------------------------------------------------------ Redmine
    @app.get("/redmine/users/current.json")
    def rm_current_user() -> Response:
        """키 주인 조회. REST 가 꺼져 있으면 실제 Redmine 처럼 403 이다(DEF-V014)."""
        try:
            source._check("REDMINE", None)
        except errors.ApiError as exc:
            return _error(exc)
        return JSONResponse({"user": {"id": 1, "login": "replay"}})

    @app.get("/redmine/projects/{target}.json")
    def rm_project(target: str) -> Response:
        try:
            source._check("REDMINE", None)
        except errors.ApiError as exc:
            return _error(exc)
        if not _known_redmine(target):
            return JSONResponse({}, status_code=404)
        return JSONResponse({"project": {"identifier": target, "name": target}})

    def _rm_list(target: str, kind: str, offset: int, limit: int,
                 since: datetime | None = None) -> Response:
        return _paged(rm_items, target, kind, offset // max(limit, 1), limit,
                      lambda batch: {f"{kind}s": batch, "total_count": len(batch),
                                     "offset": offset, "limit": limit}, since)

    @app.get("/redmine/issues.json")
    def rm_issues(project_id: str, offset: int = 0, limit: int = 25,
                  updated_on: str | None = None) -> Response:
        # 증분은 updated_on=>=<시각> 으로 온다
        return _rm_list(project_id, "issue", offset, limit, _since((updated_on or "").lstrip(">=")))

    @app.get("/redmine/projects/{target}/versions.json")
    def rm_versions(target: str, offset: int = 0, limit: int = 25) -> Response:
        return _rm_list(target, "version", offset, limit)

    @app.get("/redmine/trackers.json")
    def rm_trackers(offset: int = 0, limit: int = 25) -> Response:
        # 트래커는 전역이다. 재생 자료는 대상과 무관하게 같은 목록을 낸다
        return _rm_list(d.CONNECTIONS["TD-CON-2"].target, "tracker", offset, limit)

    def _paged(fetch, target: str, kind: str, page: int, size: int, wrap,
               since: datetime | None = None) -> Response:
        """재생기가 낸 순서대로 page 번째 쪽을 준다. 재생기의 장애는 그 쪽에서 난다.

        받은 since 는 호출 기록에만 남긴다. 프로세스 안 재생기처럼 목록을 거르지는 않는다."""
        out: list[dict] = []
        try:
            for n, (_, payload) in enumerate(fetch("", target, "", kind, size, 1, since)):
                if n >= (page + 1) * size:
                    break
                if n >= page * size:
                    out.append(payload)
        except errors.ApiError as exc:
            if not out or exc.code != "TOOL_UNREACHABLE" or len(out) < size:
                # 쪽 가운데서 끊긴 응답은 실패다. 받은 만큼만 내면 마지막 쪽처럼 보여 성공으로
                # 끝난다(UC-011-S10). 쪽을 다 채운 뒤 끊겼을 때만 그 쪽을 내고 다음 쪽이 실패한다
                return _error(exc)
        return JSONResponse(wrap(out))

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18099)
    parser.add_argument("--files", type=Path, default=None, help="시험 자료 폴더(없으면 새로)")
    args = parser.parse_args()
    folder = args.files or Path(tempfile.mkdtemp(prefix="im009-replay-"))
    made = fixture_files.make_all(folder)
    import uvicorn

    uvicorn.run(create_app(ReplaySource(state="S0", files=made)), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
