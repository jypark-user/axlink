"""추적관계 생성과 조회 (시험 DB).

GitHub 와 Redmine 연결을 하나씩 붙이고 원본을 넣은 뒤 승격 → 링크 생성 → 조회까지
한 흐름으로 본다. 마지막 시험은 우리 저장소의 실제 커밋과 요구사항정의서로 돈다.
자기참조 원칙(작업 규약 0절)이 성립하는지 확인하는 자리다.
"""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ai.embedding import embedding_port
from app.common import crypto
from app.db import tx
from app.integration import repository as integ_repo
from app.project import repository as project_repo
from app.standard import service as standard
from app.standard import trace_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
ROOT = Path(__file__).resolve().parent.parent


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _gh_issue(number: int, title: str, body: str, labels: list[str], closed: bool = False) -> dict:
    return {
        "number": number, "title": title, "body": body,
        "labels": [{"name": name} for name in labels],
        "state": "closed" if closed else "open",
        "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-02T00:00:00Z",
        "html_url": f"https://github.com/x/y/issues/{number}",
    }


def _gh_commit(sha: str, message: str) -> dict:
    return {
        "sha": sha,
        "commit": {
            "message": message, "author": {"name": "jypark", "date": "2026-09-03T00:00:00Z"},
        },
        "html_url": f"https://github.com/x/y/commit/{sha}",
    }


def _rm_issue(number: int, subject: str, tracker: str, req_id: str | None = None,
              relations: list[dict] | None = None) -> dict:
    return {
        "id": number, "subject": subject, "description": "",
        "tracker": {"name": tracker},
        "status": {"name": "신규", "is_closed": False},
        "custom_fields": [{"name": "REQ ID", "value": req_id}] if req_id else [],
        "relations": relations or [],
        "created_on": "2026-09-01T00:00:00Z", "updated_on": "2026-09-02T00:00:00Z",
    }


class _Fixture:
    """연결 두 개와 그 원본. 끝나면 승격된 표준 엔터티까지 지운다."""

    def __init__(self) -> None:
        self.gh: str | None = None
        self.rm: str | None = None

    def connect(self, cur, tool: str, target: str, base_url: str) -> str:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        conn = integ_repo.insert(
            cur, PID, org, tool, f"trace-{tool}", base_url, target,
            crypto.encrypt("k"), "k***", {},
        )
        return str(conn["id"])

    def load(self, cur, cid: str, items: list[tuple[str, str, dict]]) -> None:
        job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
        for external_id, kind, payload in items:
            integ_repo.upsert_raw_artifact(cur, cid, external_id, kind, payload, job)

    def promote(self, cur) -> None:
        for cid in (self.gh, self.rm):
            if cid:
                cur.execute("select * from tool_connection where id = %s", (cid,))
                standard.promote_connection(cur, cur.fetchone(), embedding_port())

    def cleanup(self, cur) -> None:
        cids = [c for c in (self.gh, self.rm) if c]
        cur.execute("delete from trace_link where project_id = %s and origin = 'AUTO'", (PID,))
        for table in ("requirement", "issue", "risk", "code_change", "work_product"):
            cur.execute(
                f"delete from {table} where tool_connection_id = any(%s::uuid[])", (cids,)
            )
        cur.execute("delete from tool_connection where id = any(%s::uuid[])", (cids,))


@pytest.fixture
def seeded():
    fx = _Fixture()
    with tx() as cur:
        fx.gh = fx.connect(cur, "GITHUB", f"x/trace-{uuid.uuid4().hex[:6]}", "https://api.github.com")
        fx.rm = fx.connect(cur, "REDMINE", f"trace-{uuid.uuid4().hex[:6]}", "http://redmine")
        fx.load(cur, fx.gh, [
            ("issue:23", "issue", _gh_issue(
                23, "[QUR.WEB.001] 발주기관 화면은 읽기 전용", "본문", ["유형: 요구사항"])),
            ("issue:31", "issue", _gh_issue(
                31, "[SWFR.RAG.007] 근거 게이트", "본문", ["유형: 요구사항"])),
            ("issue:2", "issue", _gh_issue(
                2, "[SWFR.CON.002] 매핑 규칙 설정화", "본문", ["유형: 요구사항"], closed=True)),
            ("issue:44", "issue", _gh_issue(
                44, "D3 조사", "`SWFR.RAG.007` 근거 게이트 임계값을 정한다.", ["유형: 작업"])),
            ("issue:45", "issue", _gh_issue(
                45, "근거 없는 작업", "아무 코드도 안 적었다.", ["유형: 작업"])),
            ("commit:" + "a" * 40, "commit", _gh_commit(
                "a" * 40,
                "feat(integration): 매핑 판별 이름을 연결별 설정으로  [SWFR.CON.002]\n\n"
                "이유.\n\nRefs: GH-2, RM-4")),
            ("commit:" + "b" * 40, "commit", _gh_commit(
                "b" * 40, "test(rag): 게이트 시험  [SWFR.RAG.007]")),
            ("commit:" + "c" * 40, "commit", _gh_commit(
                "c" * 40, "chore(infra): 의존성 정리  [chore]")),
        ])
        fx.load(cur, fx.rm, [
            ("4", "issue", _rm_issue(4, "커넥터 시험", "시험", "SWFR.CON.002", [
                {"id": 1, "issue_id": 4, "issue_to_id": 5, "relation_type": "relates"},
                {"id": 2, "issue_id": 4, "issue_to_id": 99, "relation_type": "relates"},
            ])),
            ("5", "issue", _rm_issue(5, "커넥터 작업", "작업")),
            ("6", "issue", _rm_issue(6, "리스크 하나", "리스크", "QUR.WEB.001")),
        ])
        fx.promote(cur)
    yield fx
    with tx() as cur:
        fx.cleanup(cur)


def _edges(cur) -> dict[tuple[str, str, str], dict]:
    cur.execute(
        """
        select tl.from_type, tl.to_type, tl.link_kind, tl.status, tl.evidence_kind,
               tl.evidence_text, tl.evidence_url,
               coalesce(i.issue_key, k.title, left(c.ref_name, 3), w.title) as from_label,
               coalesce(r.code, i2.issue_key) as to_label
          from trace_link tl
          left join issue i on tl.from_type = 'ISSUE' and i.id = tl.from_id
          left join risk k on tl.from_type = 'RISK' and k.id = tl.from_id
          left join code_change c on tl.from_type = 'CODE_CHANGE' and c.id = tl.from_id
          left join work_product w on tl.from_type = 'WORK_PRODUCT' and w.id = tl.from_id
          left join requirement r on tl.to_type = 'REQUIREMENT' and r.id = tl.to_id
          left join issue i2 on tl.to_type = 'ISSUE' and i2.id = tl.to_id
         where tl.project_id = %s and tl.origin = 'AUTO'
        """,
        (PID,),
    )
    return {(row["from_label"], row["to_label"], row["link_kind"]): row for row in cur.fetchall()}


@requires_db
def test_근거가_있는_것만_링크가_되고_근거가_남는다(seeded):
    with tx() as cur:
        result = trace_service.build_project_links(cur, PID)
        edges = _edges(cur)

    assert set(edges) == {
        ("aaa", "SWFR.CON.002", "IMPLEMENTS"),   # 커밋 대괄호 코드 (Refs: GH-2 도 같은 변)
        ("aaa", "RM-4", "IMPLEMENTS"),           # Refs: RM-4
        ("bbb", "SWFR.RAG.007", "TESTS"),        # test 유형 커밋
        ("GH-44", "SWFR.RAG.007", "IMPLEMENTS"), # 작업 이슈 본문의 코드
        ("RM-4", "SWFR.CON.002", "TESTS"),       # REQ ID 필드, 시험 트래커
        ("RM-4", "RM-5", "TESTS"),               # relations
        ("리스크 하나", "QUR.WEB.001", "IMPLEMENTS"),  # 리스크의 REQ ID
    }
    # 커밋의 Refs: GH-2 는 요구사항 이슈를 가리키므로 대괄호 코드와 같은 변이다.
    # 먼저 찾은 근거(대괄호 코드)가 남는다.
    commit_req = edges[("aaa", "SWFR.CON.002", "IMPLEMENTS")]
    assert commit_req["evidence_kind"] == "TEXT_REQ_CODE"
    assert commit_req["evidence_text"].endswith("[SWFR.CON.002]")
    assert commit_req["evidence_url"] == "https://github.com/x/y/commit/" + "a" * 40

    assert edges[("aaa", "RM-4", "IMPLEMENTS")]["evidence_text"] == "Refs: GH-2, RM-4"
    assert edges[("RM-4", "SWFR.CON.002", "TESTS")]["evidence_kind"] == "CUSTOM_FIELD"
    assert edges[("RM-4", "SWFR.CON.002", "TESTS")]["evidence_url"] == "http://redmine/issues/4"
    assert edges[("RM-4", "RM-5", "TESTS")]["evidence_kind"] == "ISSUE_RELATION"
    assert edges[("GH-44", "SWFR.RAG.007", "IMPLEMENTS")]["evidence_kind"] == "TEXT_REQ_CODE"
    assert all(row["status"] == "ACTIVE" for row in edges.values())

    # RM-99 는 수집된 적이 없다. 근거는 있으나 상대가 없으니 만들지 않는다.
    assert result.active == 7
    assert result.unresolved >= 1
    assert result.broken == 0


@requires_db
def test_다시_돌려도_같고_근거가_사라지면_끊긴_것으로_남는다(seeded):
    with tx() as cur:
        first = trace_service.build_project_links(cur, PID)
        cur.execute("select id from trace_link where project_id = %s order by id", (PID,))
        ids_first = [str(r["id"]) for r in cur.fetchall()]

        second = trace_service.build_project_links(cur, PID)
        cur.execute("select id from trace_link where project_id = %s order by id", (PID,))
        ids_second = [str(r["id"]) for r in cur.fetchall()]

    assert first.active == second.active
    assert ids_first == ids_second  # 행이 새로 생기지도 지워지지도 않는다

    # 작업 이슈에서 코드를 지웠다. 다음 생성에서 그 링크는 끊긴다. 행은 남는다.
    with tx() as cur:
        cur.execute(
            """
            update raw_artifact set payload_jsonb = payload_jsonb || '{"body": "코드를 지웠다"}'
             where tool_connection_id = %s and external_id = 'issue:44'
            """,
            (seeded.gh,),
        )
        third = trace_service.build_project_links(cur, PID)
        edges = _edges(cur)

    assert third.broken == 1
    assert edges[("GH-44", "SWFR.RAG.007", "IMPLEMENTS")]["status"] == "BROKEN"
    assert len(edges) == 7


@requires_db
def test_사람이_만든_링크는_자동_생성이_덮지_않는다(seeded):
    with tx() as cur:
        cur.execute(
            "select id from issue where tool_connection_id = %s and issue_key = 'GH-44'",
            (seeded.gh,),
        )
        issue_id = cur.fetchone()["id"]
        cur.execute(
            "select id from requirement where code = 'SWFR.RAG.007' and project_id = %s", (PID,)
        )
        req_id = cur.fetchone()["id"]
        cur.execute(
            """
            insert into trace_link
              (project_id, from_type, from_id, to_type, to_id, link_kind, origin)
            values (%s, 'ISSUE', %s, 'REQUIREMENT', %s, 'IMPLEMENTS', 'MANUAL') returning id
            """,
            (PID, issue_id, req_id),
        )
        manual_id = cur.fetchone()["id"]
        try:
            result = trace_service.build_project_links(cur, PID)
            cur.execute(
                "select origin, evidence_kind, status from trace_link where id = %s",
                (manual_id,),
            )
            row = cur.fetchone()
        finally:
            cur.execute("delete from trace_link where id = %s", (manual_id,))

    assert row == {"origin": "MANUAL", "evidence_kind": None, "status": "ACTIVE"}
    assert result.active == 6  # 수기 변 하나만큼 자동 건수가 준다


@requires_db
def test_추적표와_상세_조회(client, client_token, seeded):
    with tx() as cur:
        trace_service.build_project_links(cur, PID)

    body = client.get(
        f"/api/projects/{PID}/traceability?page=0&size=100", headers=_auth(client_token("r3"))
    ).json()
    rows = {r["requirementCode"]: r for r in body["content"]}

    con2 = rows["SWFR.CON.002"]
    assert [c["label"][:3] for c in con2["implementsList"]] == ["aaa"]
    assert con2["implementsList"][0]["externalUrl"].endswith("/commit/" + "a" * 40)
    assert [c["label"] for c in con2["tests"]] == ["RM-4"]
    assert con2["designs"] == [] and con2["brokenAt"] == []

    rag7 = rows["SWFR.RAG.007"]
    assert {c["label"] for c in rag7["implementsList"]} == {"GH-44"}
    assert [c["label"][:3] for c in rag7["tests"]] == ["bbb"]

    detail = client.get(
        f"/api/projects/{PID}/requirements/{con2['requirementId']}",
        headers=_auth(client_token("r3")),
    ).json()
    assert detail["code"] == "SWFR.CON.002" and detail["traceComplete"] is True
    kinds = {
        (lk["fromLabel"], lk["evidenceKind"], lk["externalUrl"]) for lk in detail["traceLinks"]
    }
    assert ("RM-4", "CUSTOM_FIELD", "http://redmine/issues/4") in kinds
    assert all(lk["evidenceText"] for lk in detail["traceLinks"])

    missing = client.get(
        f"/api/projects/{PID}/requirements/{uuid.uuid4()}", headers=_auth(client_token("r3"))
    )
    assert missing.status_code == 404

    # 사업 지표의 추적 커버리지는 시험 링크가 있는 요구사항의 비율이다. 3건 중 2건.
    with tx() as cur:
        metrics = project_repo.full_metrics(cur, PID)
    cur_total = metrics["requirementTotal"]
    assert metrics["traceabilityCoverage"] == round(100 * 2 / cur_total)


# ── 우리 저장소 자체 데이터로 (자기참조)

def _load_script():
    spec = importlib.util.spec_from_file_location(
        "build_traceability", ROOT / "scripts" / "build_traceability.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@requires_db
def test_우리_저장소의_커밋과_요구사항으로_링크가_생긴다():
    """요구사항정의서 41건을 요구사항 이슈로, git log 를 커밋 원본으로 넣는다.

    네트워크 없이 도는 자기참조 시험이다. 규약대로 적힌 커밋이 있는 한 링크는 반드시 생긴다.
    """
    script = _load_script()
    titles, _ = script.scan_requirements()
    raw = script.git("log", "--no-merges", "--pretty=format:%H%x1f%s%x1f%b%x1e")
    commits = []
    for rec in filter(None, (r.strip() for r in raw.split("\x1e"))):
        parts = rec.split("\x1f")
        if len(parts) >= 2:
            commits.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    assert len(titles) == 41 and commits

    fx = _Fixture()
    with tx() as cur:
        fx.gh = fx.connect(cur, "GITHUB", f"jypark-user/axlink-{uuid.uuid4().hex[:6]}",
                           "https://api.github.com")
        # 이슈 번호는 실제 GH-n 참조와 겹치지 않게 1001 부터 매긴다. 여기서 보려는 것은
        # 코드 표기이지 이슈 번호가 아니다.
        items = [
            (f"issue:{n}", "issue",
             _gh_issue(n, f"[{code}] {title}", "본문", ["유형: 요구사항"]))
            for n, (code, title) in enumerate(sorted(titles.items()), start=1001)
        ]
        items += [
            (f"commit:{sha}", "commit", _gh_commit(sha, f"{subject}\n\n{body}"))
            for sha, subject, body in commits
        ]
        fx.load(cur, fx.gh, items)
        fx.promote(cur)
        try:
            result = trace_service.build_project_links(cur, PID)
            edges = _edges(cur)
            cur.execute(
                """
                select count(distinct c.id) as n from code_change c
                 where c.tool_connection_id = %s
                   and exists (select 1 from trace_link tl
                                where tl.from_type = 'CODE_CHANGE' and tl.from_id = c.id
                                  and tl.to_type = 'REQUIREMENT')
                """,
                (fx.gh,),
            )
            linked_commits = cur.fetchone()["n"]
        finally:
            fx.cleanup(cur)

    # 제목이든 본문이든 요구사항 코드를 적은 커밋은 전부 이어져야 한다. 하나도 빠지면
    # 규칙이 실제 데이터를 못 읽는 것이다.
    expected = {
        sha for sha, subject, body in commits
        if set(script.REQ_RE.findall(f"{subject}\n{body}")) & set(titles)
    }
    assert linked_commits == len(expected)
    assert result.active >= len(expected)

    # 이 브랜치의 첫 커밋 이전, 규약대로 들어간 커밋 하나를 짚어 본다.
    con2 = edges.get(("523", "SWFR.CON.002", "IMPLEMENTS"))
    assert con2 is not None and con2["evidence_kind"] == "TEXT_REQ_CODE"
    assert con2["evidence_text"].endswith("[SWFR.CON.002]")
