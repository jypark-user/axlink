"""저장소 설계 문서 근거와 변경 분류 정정 (ARC-024, 시험 DB).

GitHub 연결 하나에 요구사항 이슈·설계 문서 원본·커밋·PR 을 넣고 링크를 만든다. 명시적 참조만
잇는지, 초안·미결 표시가 남는지, 정정이 끊김과 구분되는지, 수동 링크와 요구사항 상태를
건드리지 않는지 본다.
"""

import uuid
from datetime import UTC, datetime

import pytest
from psycopg.types.json import Jsonb

from app.ai.embedding import embedding_port
from app.auth.models import AuthPrincipal
from app.common import crypto, errors
from app.common.paging import PageQuery
from app.db import tx
from app.integration import repository as integ_repo
from app.standard import service as standard
from app.standard import trace_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
DESIGN = "docs/20-design/*.md"
SHA = "c" * 40


def _req(number: int, code: str) -> dict:
    return {
        "number": number, "title": f"[{code}] 요구사항", "body": "본문",
        "labels": [{"name": "유형: 요구사항"}], "state": "open",
        "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-02T00:00:00Z",
        "html_url": f"https://github.com/o/r/issues/{number}",
    }


def _doc(path: str, text: str, blob: str = "b" * 40, deleted: bool = False) -> dict:
    return {
        "repo": "o/r", "path": path, "commit_sha": SHA, "blob_sha": blob,
        "html_url": f"https://github.com/o/r/blob/{SHA}/{path}", "text": text, "deleted": deleted,
    }


def _commit(sha: str, message: str, files: list[str] | None = None,
            parents: int = 1) -> dict:
    payload = {
        "sha": sha, "parents": [{"sha": "p"}] * parents,
        "commit": {"message": message, "author": {"name": "jy", "date": "2026-09-03T00:00:00Z"}},
        "html_url": f"https://github.com/o/r/commit/{sha}",
    }
    if files is not None:
        payload["files"] = files
    return payload


def _pr(number: int, title: str, files: list[str] | None = None) -> dict:
    payload = {
        "number": number, "title": title, "body": "", "state": "closed",
        "merged_at": "2026-09-04T00:00:00Z", "created_at": "2026-09-03T00:00:00Z",
        "html_url": f"https://github.com/o/r/pull/{number}", "head": {"ref": "x", "sha": "h"},
        "user": {"login": "jy"},
    }
    if files is not None:
        payload["files"] = files
    return payload


ARC = """# ARC-901 설계 근거 시험

| | |
|---|---|
| 상태 | **확정** |
| 관련 | `SWFR.CON.002` `SWFR.PIP.007`(미결) |

본문에서 `SWFR.RAG.007` 을 지나가듯 말한다.
"""

DRAFT = """# SW 설계서 시험 (IM-903)

> v0.1 초안

### 7.3 근거 게이트 (SWFR.RAG.007)
"""


class _Repo:
    def __init__(self) -> None:
        self.cid = ""
        self.job = ""

    def connect(self, cur) -> None:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        conn = integ_repo.insert(
            cur, PID, org, "GITHUB", "design-trace", "https://api.github.com",
            f"o/design-{uuid.uuid4().hex[:6]}", crypto.encrypt("k"), "k***",
            {"designDocPaths": DESIGN}, requirement_from_issues=True,
        )
        self.cid = str(conn["id"])
        # 수집 잡은 연결마다 하나만 돌 수 있다(uq_sync_job__running). 시험은 한 잡을 같이 쓴다
        self.job = integ_repo.insert_sync_job(cur, self.cid, "BACKFILL", None, datetime.now(UTC))

    def load(self, cur, items: list[tuple[str, str, dict]]) -> None:
        for external_id, kind, payload in items:
            integ_repo.upsert_raw_artifact(cur, self.cid, external_id, kind, payload, self.job)
        cur.execute("select * from tool_connection where id = %s", (self.cid,))
        standard.promote_connection(cur, cur.fetchone(), embedding_port())

    def cleanup(self, cur) -> None:
        cur.execute("delete from trace_link where project_id = %s", (PID,))
        for table in ("requirement", "issue", "code_change", "work_product"):
            cur.execute(f"delete from {table} where tool_connection_id = %s", (self.cid,))
        cur.execute("delete from tool_connection where id = %s", (self.cid,))


@pytest.fixture
def repo():
    r = _Repo()
    with tx() as cur:
        r.connect(cur)
        r.load(cur, [
            ("issue:2", "issue", _req(2, "SWFR.CON.002")),
            ("issue:17", "issue", _req(17, "SWFR.PIP.007")),
            ("issue:36", "issue", _req(36, "SWFR.RAG.007")),
            ("doc:docs/20-design/ARC-901.md", "design_doc", _doc("docs/20-design/ARC-901.md", ARC)),
            ("doc:docs/20-design/IM-903.md", "design_doc", _doc("docs/20-design/IM-903.md", DRAFT)),
        ])
    yield r
    with tx() as cur:
        r.cleanup(cur)


def _links(cur, kind: str | None = None) -> list[dict]:
    cur.execute(
        """
        select tl.*, r.code from trace_link tl
          left join requirement r on r.id = tl.to_id
         where tl.project_id = %s and (%s::text is null or tl.link_kind = %s)
         order by r.code, tl.from_type
        """,
        (PID, kind, kind),
    )
    return cur.fetchall()


@requires_db
def test_명시적_참조만_설계_근거가_되고_위치와_상태가_남는다(repo):
    with tx() as cur:
        result = trace_service.build_project_links(cur, PID)
        designs = _links(cur, "DESIGNS")
        cur.execute("select code, status from requirement where tool_connection_id = %s",
                    (repo.cid,))
        statuses = {r["code"]: r["status"] for r in cur.fetchall()}

    got = {(d["code"], d["evidence_meta"]["docId"]) for d in designs}
    # ARC-901 의 본문 언급(SWFR.RAG.007)은 근거가 아니다. RAG.007 은 초안 문서의 절 제목에서만 온다
    assert got == {("SWFR.CON.002", "ARC-901"), ("SWFR.PIP.007", "ARC-901"),
                   ("SWFR.RAG.007", "IM-903")}
    by = {(d["code"], d["evidence_meta"]["docId"]): d for d in designs}
    con = by[("SWFR.CON.002", "ARC-901")]
    assert con["from_type"] == "REPO_DOCUMENT" and con["evidence_kind"] == "DOC_REQ_REF"
    assert con["evidence_meta"]["path"] == "docs/20-design/ARC-901.md"
    assert con["evidence_meta"]["commitSha"] == SHA and con["evidence_meta"]["line"] == 6
    assert con["evidence_url"].endswith(f"{SHA}/docs/20-design/ARC-901.md#L6")
    assert con["evidence_meta"]["docStatus"] == "CONFIRMED"
    assert by[("SWFR.PIP.007", "ARC-901")]["evidence_meta"]["qualifier"] == "미결"
    assert by[("SWFR.RAG.007", "IM-903")]["evidence_meta"]["docStatus"] == "DRAFT"
    assert result.superseded == 0 and result.broken == 0
    # 설계 근거가 생겨도 요구사항 상태는 원천 그대로다
    assert set(statuses.values()) == {"DEFINED"}


@requires_db
def test_다시_돌리고_같은_원본을_또_넣어도_링크는_하나다(repo):
    with tx() as cur:
        trace_service.build_project_links(cur, PID)
        repo.load(cur, [("doc:docs/20-design/ARC-901.md", "design_doc",
                         _doc("docs/20-design/ARC-901.md", ARC))])
        again = trace_service.build_project_links(cur, PID)
        designs = _links(cur, "DESIGNS")
    assert len(designs) == 3 and again.broken == 0 and again.superseded == 0


@requires_db
def test_참조_행을_지우면_끊김_문서를_지우면_삭제로_남는다(repo):
    with tx() as cur:
        trace_service.build_project_links(cur, PID)
        revised = ARC.replace("`SWFR.CON.002` ", "")
        repo.load(cur, [
            ("doc:docs/20-design/ARC-901.md", "design_doc",
             _doc("docs/20-design/ARC-901.md", revised, blob="d" * 40)),
            ("doc:docs/20-design/IM-903.md", "design_doc",
             _doc("docs/20-design/IM-903.md", DRAFT, deleted=True)),
        ])
        result = trace_service.build_project_links(cur, PID)
        rows = {(d["code"], d["status"]): d for d in _links(cur, "DESIGNS")}
    assert result.broken == 2 and result.superseded == 0
    assert rows[("SWFR.CON.002", "BROKEN")]["status_reason"] == "원천 근거가 다시 확인되지 않음"
    assert rows[("SWFR.RAG.007", "BROKEN")]["status_reason"] == "원천 문서가 저장소에서 삭제됨"
    assert rows[("SWFR.CON.002", "BROKEN")]["status_changed_at"] is not None
    assert ("SWFR.PIP.007", "ACTIVE") in rows


@requires_db
def test_분류_정정은_끊김이_아니라_대체_제외로_남고_전후가_보존된다(repo):
    a, b = "a" * 40, "e" * 40
    with tx() as cur:
        # 변경 파일을 모를 때는 지금 규칙: docs 커밋도 구현으로 잡힌다
        repo.load(cur, [
            ("commit:" + a, "commit", _commit(a, "docs: 대장 갱신  [SWFR.CON.002]")),
            ("commit:" + b, "commit", _commit(b, "docs: 설계 보완  [SWFR.PIP.007]")),
        ])
        trace_service.build_project_links(cur, PID)
        before = {(d["code"], d["link_kind"]): d for d in _links(cur)
                  if d["from_type"] == "CODE_CHANGE"}
        assert set(before) == {("SWFR.CON.002", "IMPLEMENTS"), ("SWFR.PIP.007", "IMPLEMENTS")}

        # 변경 파일을 알게 되면: 관리 문서만 바꾼 a 는 제외, 설계 문서만 바꾼 b 는 설계로 대체
        repo.load(cur, [
            ("commit:" + a, "commit", _commit(a, "docs: 대장 갱신  [SWFR.CON.002]",
                                              ["docs/00-management/a.md"])),
            ("commit:" + b, "commit", _commit(b, "docs: 설계 보완  [SWFR.PIP.007]",
                                              ["docs/20-design/ARC-901.md"])),
        ])
        result = trace_service.build_project_links(cur, PID)
        after = {(d["code"], d["link_kind"]): d for d in _links(cur)
                 if d["from_type"] == "CODE_CHANGE"}

    assert result.superseded == 2 and result.broken == 0
    old_a = after[("SWFR.CON.002", "IMPLEMENTS")]
    assert old_a["status"] == "SUPERSEDED" and old_a["superseded_by"] is None
    assert old_a["status_reason"].startswith("분류 정정으로 제외")
    old_b = after[("SWFR.PIP.007", "IMPLEMENTS")]
    new_b = after[("SWFR.PIP.007", "DESIGNS")]
    assert old_b["status"] == "SUPERSEDED" and old_b["superseded_by"] == new_b["id"]
    assert old_b["status_reason"] == "분류 정정으로 대체: IMPLEMENTS → DESIGNS"
    # 옛 링크의 관계·근거·만든 시각은 그대로 남는다
    assert old_b["evidence_text"] == before[("SWFR.PIP.007", "IMPLEMENTS")]["evidence_text"]
    assert old_b["created_at"] == before[("SWFR.PIP.007", "IMPLEMENTS")]["created_at"]
    assert new_b["status"] == "ACTIVE"


@requires_db
def test_섞인_변경은_관계가_여럿이다(repo):
    sha = "f" * 40
    with tx() as cur:
        repo.load(cur, [("commit:" + sha, "commit", _commit(
            sha, "feat: 게이트  [SWFR.RAG.007]",
            ["app/rag/answer.py", "tests/test_answer.py", "docs/20-design/ARC-901.md"]))])
        trace_service.build_project_links(cur, PID)
        kinds = {d["link_kind"] for d in _links(cur)
                 if d["from_type"] == "CODE_CHANGE" and d["code"] == "SWFR.RAG.007"}
    assert kinds == {"IMPLEMENTS", "TESTS", "DESIGNS"}


@requires_db
def test_병합_커밋은_PR_과_겹치는_근거만_뺀다(repo):
    m = "9" * 40
    with tx() as cur:
        repo.load(cur, [
            ("pull_request:7", "pull_request", _pr(7, "feat: 매핑  [SWFR.CON.002]", ["app/a.py"])),
            ("commit:" + m, "commit", _commit(
                m, "Merge pull request #7 from o/x\n\nfeat: 매핑  [SWFR.CON.002]\n"
                   "그리고 SWFR.RAG.007 도 고쳤다", ["app/a.py"], parents=2)),
        ])
        trace_service.build_project_links(cur, PID)
        cur.execute(
            """
            select r.code, c.kind from trace_link tl
              join code_change c on c.id = tl.from_id
              join requirement r on r.id = tl.to_id
             where tl.project_id = %s and tl.status = 'ACTIVE' and tl.from_type = 'CODE_CHANGE'
            """,
            (PID,),
        )
        got = sorted((r["code"], r["kind"]) for r in cur.fetchall())
    # PR 이 가진 CON.002 는 병합 커밋에서 빠지고, PR 에 없는 RAG.007 은 남는다
    assert got == [("SWFR.CON.002", "MERGE_REQUEST"), ("SWFR.RAG.007", "COMMIT")]


@requires_db
def test_수동_링크는_자동_정정이_건드리지_않는다(repo):
    with tx() as cur:
        trace_service.build_project_links(cur, PID)
        cur.execute(
            "select id, from_id, to_id from trace_link where project_id = %s "
            "and link_kind = 'DESIGNS' limit 1", (PID,),
        )
        auto = cur.fetchone()
        cur.execute(
            """
            insert into trace_link (project_id, from_type, from_id, to_type, to_id, link_kind,
                                    origin, status, evidence_text)
            values (%s, 'REPO_DOCUMENT', %s, 'REQUIREMENT', %s, 'IMPLEMENTS', 'MANUAL', 'ACTIVE',
                    '사람이 이었다')
            returning id
            """,
            (PID, auto["from_id"], auto["to_id"]),
        )
        manual = cur.fetchone()["id"]
        # 문서를 지워도 수동 링크는 그대로다
        cur.execute("update raw_artifact set payload_jsonb = payload_jsonb || %s "
                    "where tool_connection_id = %s and object_kind = 'design_doc'",
                    (Jsonb({"deleted": True}), repo.cid))
        trace_service.build_project_links(cur, PID)
        cur.execute("select origin, status, evidence_text, status_reason from trace_link "
                    "where id = %s", (manual,))
        row = cur.fetchone()
    assert (row["origin"], row["status"], row["evidence_text"], row["status_reason"]) == (
        "MANUAL", "ACTIVE", "사람이 이었다", None)


@requires_db
def test_추적표_칸은_대체된_링크를_빼고_문서_상태를_보인다_권한도_본다(repo):
    with tx() as cur:
        trace_service.build_project_links(cur, PID)
        cur.execute("select id from app_user where username = 'r1'")
        admin = str(cur.fetchone()["id"])
        cur.execute("select organization_id from app_user where username = 'r1'")
        org = str(cur.fetchone()["organization_id"])
        page = trace_service.traceability_rows(
            cur, AuthPrincipal(user_id=admin, org_id=org, org_type="CONTRACTOR",
                               role="SUPER_ADMIN"),
            PID, PageQuery(page=0, size=100),
        )
        outsider = AuthPrincipal(user_id=str(uuid.uuid4()), org_id=str(uuid.uuid4()),
                                 org_type="CONTRACTOR", role="CONTRACTOR")
        with pytest.raises(errors.ApiError):
            trace_service.traceability_rows(cur, outsider, PID, PageQuery(page=0, size=10))

    rows = {r.requirementCode: r for r in page.content}
    rag = rows["SWFR.RAG.007"].designs
    assert [(c.sourceType, c.label, c.docStatus) for c in rag] == [
        ("REPO_DOCUMENT", "IM-903", "DRAFT")]
    assert rag[0].section == "7.3 근거 게이트 (SWFR.RAG.007)"
    pip = rows["SWFR.PIP.007"].designs
    assert pip[0].qualifier == "미결"
