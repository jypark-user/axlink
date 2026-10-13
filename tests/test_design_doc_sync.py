"""설계 문서·변경 파일 수집 (ARC-024 2-6, 시험 DB). GitHub 는 가짜 커넥터로 바꾼다.

이미 받은 것은 다시 부르지 않는지, 조회 실패를 삭제로 읽지 않는지, 트리가 잘렸을 때 삭제를
판단하지 않는지, 레이트리밋에서 멈추는지, 증분 원본에 변경 파일을 이어 붙이는지 본다.
"""

import base64
import uuid
from datetime import UTC, datetime

import pytest

from app.common import crypto, errors
from app.config import settings
from app.db import tx
from app.integration import repository as integ_repo
from app.integration import sync
from app.standard.mapping_rules import MappingRules
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
SHA = "c" * 40
RULES = MappingRules(design_doc_paths="docs/20-design/*.md")


class FakeGitHub:
    def __init__(self, files: dict[str, str] | None = None, fail: set[str] | None = None,
                 limit_after: int | None = None) -> None:
        self.files = files or {}
        self.fail = fail or set()
        self.calls: list[str] = []
        self.limit_after = limit_after

    def fetch_file(self, base, target, token, path, ref=None):
        self.calls.append(path)
        if self.limit_after is not None and len(self.calls) > self.limit_after:
            raise errors.ApiError(429, "TOOL_RATE_LIMITED", "레이트리밋")
        if path in self.fail:
            raise errors.ApiError(502, "TOOL_UNREACHABLE", "일시 오류")
        text = self.files[path]
        return {"path": path, "sha": f"blob-{path}-{len(text)}",
                "content": base64.b64encode(text.encode()).decode()}

    def fetch_change_files(self, base, target, token, kind, ident):
        self.calls.append(f"{kind}:{ident}")
        return ([f"app/{ident}.py"], 4999 if ident != "low" else 10)


@pytest.fixture
def conn():
    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        row = integ_repo.insert(cur, PID, org, "GITHUB", "doc-sync", "https://api.github.com",
                                f"o/sync-{uuid.uuid4().hex[:6]}", crypto.encrypt("k"), "k***",
                                {"designDocPaths": "docs/20-design/*.md"})
        cid = str(row["id"])
        job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
    yield cid, job
    with tx() as cur:
        cur.execute("delete from tool_connection where id = %s", (cid,))


def _tree(cur, cid: str, job: str, blobs: dict[str, str], truncated: bool = False) -> None:
    integ_repo.upsert_raw_artifact(cur, cid, "tree:HEAD", "tree", {
        "sha": "t", "commit": SHA, "truncated": truncated, "paths": list(blobs), "blobs": blobs,
        "html_url": f"https://github.com/o/r/blob/{SHA}/",
    }, job)


def _stats() -> dict[str, int]:
    return {"fetched": 0}


def _docs(cur, cid: str) -> dict[str, dict]:
    return integ_repo.raw_payloads_by_kind(cur, cid, "design_doc")


@requires_db
def test_바뀐_문서만_받고_위치를_남긴다(conn):
    cid, job = conn
    gh = FakeGitHub({"docs/20-design/A.md": "# ARC-001 A", "docs/20-design/B.md": "# ARC-002 B"})
    with tx() as cur:
        _tree(cur, cid, job, {"docs/20-design/A.md": "a1", "docs/20-design/B.md": "b1",
                              "app/x.py": "x1"})
        stats = _stats()
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, stats, RULES)
        first = _docs(cur, cid)
        # 같은 blob 이면 다시 부르지 않는다
        gh.calls.clear()
        _tree(cur, cid, job, {"docs/20-design/A.md": "a1", "docs/20-design/B.md": "b2"})
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, stats2 := _stats(), RULES)
    assert sorted(first) == ["doc:docs/20-design/A.md", "doc:docs/20-design/B.md"]
    a = first["doc:docs/20-design/A.md"]
    assert a["commit_sha"] == SHA and a["text"] == "# ARC-001 A" and not a["deleted"]
    assert a["html_url"] == f"https://github.com/o/r/blob/{SHA}/docs/20-design/A.md"
    assert stats["docCalls"] == 2
    assert gh.calls == ["docs/20-design/B.md"] and stats2["docUnchanged"] == 1


@requires_db
def test_조회_실패는_삭제가_아니고_트리에서_빠져야_삭제다(conn):
    cid, job = conn
    gh = FakeGitHub({"docs/20-design/A.md": "# ARC-001 A"})
    with tx() as cur:
        _tree(cur, cid, job, {"docs/20-design/A.md": "a1"})
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, _stats(), RULES)
        # 내용이 바뀌었는데 조회가 실패했다 → 옛 원본 유지
        _tree(cur, cid, job, {"docs/20-design/A.md": "a2"})
        failed = FakeGitHub(fail={"docs/20-design/A.md"})
        s1 = _stats()
        sync._collect_details(cur, cid, failed, "", "o/r", "k", job, s1, RULES)
        kept = _docs(cur, cid)["doc:docs/20-design/A.md"]
        # 트리가 잘렸으면 경로가 없어도 삭제로 보지 않는다
        _tree(cur, cid, job, {}, truncated=True)
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, _stats(), RULES)
        still = _docs(cur, cid)["doc:docs/20-design/A.md"]
        # 잘리지 않은 트리에서 빠지면 삭제
        _tree(cur, cid, job, {"app/x.py": "x"})
        s3 = _stats()
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, s3, RULES)
        gone = _docs(cur, cid)["doc:docs/20-design/A.md"]
    assert s1["docFailed"] == 1 and not kept["deleted"] and kept["text"] == "# ARC-001 A"
    assert not still["deleted"]
    assert gone["deleted"] and gone["text"] == "# ARC-001 A" and s3["docDeleted"] == 1


@requires_db
def test_레이트리밋이면_받은_데까지만_쓰고_멈춘다(conn):
    cid, job = conn
    files = {f"docs/20-design/{i}.md": f"# ARC-00{i}" for i in range(4)}
    gh = FakeGitHub(files, limit_after=2)
    with tx() as cur:
        _tree(cur, cid, job, {p: "s" for p in files})
        stats = _stats()
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, stats, RULES)
        got = _docs(cur, cid)
    assert stats["rateLimitStop"] == 1 and len(got) == 2


@requires_db
def test_설정이_없으면_설계_문서를_받지_않는다(conn):
    cid, job = conn
    gh = FakeGitHub({"docs/20-design/A.md": "# ARC-001 A"})
    with tx() as cur:
        _tree(cur, cid, job, {"docs/20-design/A.md": "a1"})
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, _stats(), MappingRules())
    assert gh.calls == []


@requires_db
def test_변경_파일은_없는_것만_받고_증분_원본에_이어_붙인다(conn, monkeypatch):
    cid, job = conn
    monkeypatch.setattr(settings, "collect_change_files", True)
    gh = FakeGitHub()
    commit = {"sha": "s1", "commit": {"message": "feat: x"}}
    with tx() as cur:
        integ_repo.upsert_raw_artifact(cur, cid, "commit:s1", "commit", dict(commit), job)
        integ_repo.upsert_raw_artifact(cur, cid, "commit:s2", "commit",
                                       {"sha": "s2", "files": ["app/old.py"]}, job)
        stats = _stats()
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, stats, MappingRules())
        after = integ_repo.raw_payload(cur, cid, "commit:s1")
        # 증분 수집이 목록 응답(변경 파일 없음)으로 다시 받아도 이어 붙인다
        again = dict(commit)
        sync._carry_files(cur, cid, "commit:s1", "commit", again)
    assert gh.calls == ["commit:s1"] and stats["fileCalls"] == 1 and stats["fileCached"] == 1
    assert after["files"] == ["app/s1.py"]
    assert again["files"] == ["app/s1.py"]


@requires_db
def test_남은_호출이_적으면_변경_파일_조회를_멈춘다(conn, monkeypatch):
    cid, job = conn
    monkeypatch.setattr(settings, "collect_change_files", True)
    gh = FakeGitHub()
    with tx() as cur:
        for ident in ("low", "z1", "z2"):
            integ_repo.upsert_raw_artifact(cur, cid, f"commit:{ident}", "commit",
                                           {"sha": ident}, job)
        stats = _stats()
        sync._collect_details(cur, cid, gh, "", "o/r", "k", job, stats, MappingRules())
    assert stats["rateLimitStop"] == 1 and len(gh.calls) <= 3
