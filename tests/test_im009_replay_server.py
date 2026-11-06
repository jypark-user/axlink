"""원천 재생 서버가 프로세스 안 재생기와 같은 자료를 실제 어댑터에 내는지 본다.

5174 같은 원격 서버에 시나리오를 돌릴 때 그 서버의 어댑터가 이 서버를 부른다. 같은 자료가
HTTP 를 거쳐도 같은 항목·같은 파일로 읽혀야 재생 결과를 서로 견줄 수 있다.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from app.common import errors
from app.integration.adapter import github_connector as gh
from app.integration.adapter import redmine_connector as rm
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import files as fixture_files
from tests.fixtures.im009.replay import WBS_PATH, ReplaySource
from tests.fixtures.im009.replay_server import create_app

GH_REPO = d.CONNECTIONS["TD-CON-1"].target
RM_PRJ = d.CONNECTIONS["TD-CON-2"].target


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def made(tmp_path_factory) -> dict[str, Path]:
    return fixture_files.make_all(tmp_path_factory.mktemp("im009"))


@pytest.fixture(scope="module")
def server(made):
    source = ReplaySource(state="S0", files=made)
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(source), host="127.0.0.1", port=port,
                                        log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(f"{base}/github/repos/{GH_REPO}", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    yield base, source
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _reset(server):
    base, _ = server
    httpx.put(f"{base}/_replay/faults", json={})
    httpx.put(f"{base}/_replay/state", json={"state": "S0", "wbs_current": None})


def _ids(gen) -> list[str]:
    return [eid for eid, _ in gen]


def test_github_항목은_재생기와_같다(server, made):
    base, _ = server
    local = ReplaySource(state="S0", files=made)
    for kind in ("issue", "milestone", "commit", "pull_request"):
        over_http = _ids(gh.fetch_items(f"{base}/github", GH_REPO, "t", kind, 100, 5))
        in_proc = _ids(local.fetch_items("GITHUB")("", GH_REPO, "", kind, 100, 5))
        assert over_http == in_proc, kind
    tree = dict(gh.fetch_items(f"{base}/github", GH_REPO, "t", "tree", 100, 5))["tree:HEAD"]
    assert WBS_PATH in tree["paths"] and len(tree["commit"]) == 40


def test_github_확인과_파일(server, made):
    base, _ = server
    probe = gh.verify(f"{base}/github", GH_REPO, "t")
    assert sorted(probe.readable) == sorted(gh.ITEM_PATHS) and probe.denied == []
    got = gh.fetch_file(f"{base}/github", GH_REPO, "t", WBS_PATH)
    assert got is not None and got["sha"] == d.WBS_FILE_COMMIT_S0
    import base64

    assert base64.b64decode(got["content"]) == made["TD-DOC-6"].read_bytes()
    assert gh.fetch_file(f"{base}/github", GH_REPO, "t", "없는/파일.txt") is None


def test_redmine_항목은_재생기와_같다(server, made):
    base, _ = server
    local = ReplaySource(state="S0", files=made)
    for kind in rm.ITEM_KINDS:
        over_http = _ids(rm.fetch_items(f"{base}/redmine", RM_PRJ, "k", kind, 2, 50))
        in_proc = _ids(local.fetch_items("REDMINE")("", RM_PRJ, "", kind, 2, 50))
        assert over_http == in_proc and over_http, kind
    assert rm.verify(f"{base}/redmine", RM_PRJ, "k").denied == []


def test_장애_주입(server):
    base, _ = server
    httpx.put(f"{base}/_replay/faults", json={"auth_fail": True})
    with pytest.raises(errors.ApiError) as exc:
        gh.verify(f"{base}/github", GH_REPO, "t")
    assert exc.value.code == "TOOL_AUTH"

    httpx.put(f"{base}/_replay/faults", json={"denied_kinds": ["issue"]})
    assert gh.verify(f"{base}/github", GH_REPO, "t").denied == ["issue"]

    httpx.put(f"{base}/_replay/faults", json={"unreachable": True})
    with pytest.raises(errors.ApiError) as exc:
        rm.verify(f"{base}/redmine", RM_PRJ, "k")
    assert exc.value.code == "TOOL_UNREACHABLE"

    httpx.put(f"{base}/_replay/faults", json={"cut_after": 2})
    got: list[str] = []
    with pytest.raises(errors.ApiError) as exc:
        for eid, _ in rm.fetch_items(f"{base}/redmine", RM_PRJ, "k", "issue", 2, 50):
            got.append(eid)
    assert exc.value.code == "TOOL_UNREACHABLE" and len(got) == 2


def test_상태_S1_로_바꾸면_S1_자료를_낸다(server, made):
    base, _ = server
    httpx.put(f"{base}/_replay/state", json={"state": "S1"})
    got = gh.fetch_file(f"{base}/github", GH_REPO, "t", WBS_PATH)
    assert got is not None and got["sha"] == d.WBS_FILE_COMMIT_S1


def test_원격_재생기가_장애와_변형_파일을_서버에_보낸다(server, made, tmp_path):
    from tests.fixtures.im009.replay import Faults, RemoteReplay

    base, _ = server
    files = dict(made)
    variant = tmp_path / "WBS-변형.xlsx"
    variant.write_bytes(b"variant-bytes")
    files["TD-WBS-TEST"] = variant
    remote = RemoteReplay(base, ReplaySource(state="S0", files=files))

    remote.faults = Faults(denied_kinds={"milestone"})
    assert gh.verify(f"{base}/github", GH_REPO, "t").denied == ["milestone"]

    remote.faults = Faults(wbs_variant="TD-WBS-TEST", wbs_sha="ab" * 20)
    got = gh.fetch_file(f"{base}/github", GH_REPO, "t", WBS_PATH)
    import base64

    assert got["sha"] == "ab" * 20 and base64.b64decode(got["content"]) == b"variant-bytes"

    remote.faults = Faults()
    list(gh.fetch_items(f"{base}/github", GH_REPO, "t", "issue", 100, 5))
    assert any(c[0] == "GITHUB" and c[1] == "issue" for c in remote.calls())
