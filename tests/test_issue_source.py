"""같은 도구의 연결이 둘일 때 이슈 원천을 구분한다 (GH-140, SWFR.WEB.002).

GitHub 저장소 두 개, Redmine 프로젝트 두 개를 한 사업에 붙이고 번호가 같은 이슈를 넣는다.
키(GH-5, RM-7)가 겹쳐도 연결 단위로 따로 보이고, 추적 링크와 원문 링크가 제 연결을
가리켜야 한다. 종류 충돌(일감·버전 번호가 겹치는 것)은 test_redmine_sync_defects 가 본다.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.ai.embedding import embedding_port
from app.common import crypto
from app.db import fetch_one, tx
from app.integration import repository as integ_repo
from app.standard import repository, trace_service
from app.standard import service as standard
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _gh_issue(repo: str, number: int, title: str, body: str, labels: list[str],
              closed: bool = False) -> dict:
    return {
        "number": number, "title": title, "body": body,
        "labels": [{"name": name} for name in labels],
        "state": "closed" if closed else "open",
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z",
        "html_url": f"https://github.com/{repo}/issues/{number}",
    }


def _gh_commit(repo: str, sha: str, message: str) -> dict:
    return {
        "sha": sha,
        "commit": {"message": message,
                   "author": {"name": "jypark", "date": "2026-10-03T00:00:00Z"}},
        "html_url": f"https://github.com/{repo}/commit/{sha}",
    }


def _rm_issue(number: int, subject: str, tracker: str, closed: bool = False,
              relations: list[dict] | None = None) -> dict:
    return {
        "id": number, "subject": subject, "description": "",
        "tracker": {"name": tracker},
        "status": {"name": "완료" if closed else "신규", "is_closed": closed},
        "custom_fields": [], "relations": relations or [],
        "created_on": "2026-10-01T00:00:00Z", "updated_on": "2026-10-02T00:00:00Z",
    }


class _Sources:
    """연결과 원본. 끝나면 승격된 표준 엔터티와 링크까지 지운다."""

    def __init__(self) -> None:
        self.ids: dict[str, str] = {}
        self.repo: dict[str, str] = {}
        self.extra_projects: list[str] = []

    def connect(self, cur, key: str, tool: str, name: str, target: str, base_url: str,
                project_id: str = PID) -> str:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        conn = integ_repo.insert(
            cur, project_id, org, tool, name, base_url, target,
            crypto.encrypt("k"), "k***", {},
        )
        self.ids[key] = str(conn["id"])
        self.repo[key] = target
        return self.ids[key]

    def load(self, cur, key: str, items: list[tuple[str, str, dict]]) -> None:
        cid = self.ids[key]
        job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
        for external_id, kind, payload in items:
            integ_repo.upsert_raw_artifact(cur, cid, external_id, kind, payload, job)
        now = datetime.now(UTC)
        integ_repo.finish_sync_job(cur, job, "SUCCEEDED", {}, now, now)  # 다시 받을 수 있게

    def promote(self, cur, *keys: str) -> None:
        for key in keys or tuple(self.ids):
            cur.execute("select * from tool_connection where id = %s", (self.ids[key],))
            standard.promote_connection(cur, cur.fetchone(), embedding_port())

    def cleanup(self, cur) -> None:
        cids = list(self.ids.values())
        cur.execute(
            "delete from trace_link where project_id = any(%s::uuid[]) and origin = 'AUTO'",
            ([PID, *self.extra_projects],),
        )
        for table in ("requirement", "issue", "risk", "code_change", "work_product"):
            cur.execute(
                f"delete from {table} where tool_connection_id = any(%s::uuid[])", (cids,)
            )
        cur.execute("delete from tool_connection where id = any(%s::uuid[])", (cids,))
        for pid in self.extra_projects:
            cur.execute("delete from project where id = %s", (pid,))


def _load_first(cur, src: _Sources) -> None:
    """먼저 붙어 있던 연결 하나씩(GitHub A, Redmine A)."""
    tag = uuid.uuid4().hex[:6]
    src.connect(cur, "ghA", "GITHUB", "저장소 A", f"x/a-{tag}", "https://api.github.com")
    src.connect(cur, "rmA", "REDMINE", "레드마인 A", f"pa-{tag}", "http://rm-a")
    a = src.repo["ghA"]
    src.load(cur, "ghA", [
        ("issue:2", "issue", _gh_issue(
            a, 2, "[SWFR.CON.002] 매핑 규칙 설정화", "본문", ["유형: 요구사항"])),
        ("issue:5", "issue", _gh_issue(a, 5, "A 저장소 5번 작업", "", ["유형: 작업"])),
        ("commit:" + "a" * 40, "commit", _gh_commit(
            a, "a" * 40, "fix(integration): A 수정  [chore]\n\n이유.\n\nRefs: GH-5")),
    ])
    src.load(cur, "rmA", [
        ("7", "issue", _rm_issue(7, "레드마인 A 7번", "작업")),
        ("8", "issue", _rm_issue(8, "레드마인 A 8번 시험", "시험", relations=[
            {"id": 1, "issue_id": 8, "issue_to_id": 7, "relation_type": "relates"}])),
    ])
    src.promote(cur, "ghA", "rmA")


def _load_second(cur, src: _Sources) -> None:
    """나중에 붙인 같은 도구의 두 번째 연결. 번호가 앞 연결과 겹친다."""
    tag = uuid.uuid4().hex[:6]
    src.connect(cur, "ghB", "GITHUB", "저장소 B", f"x/b-{tag}", "https://api.github.com")
    src.connect(cur, "rmB", "REDMINE", "레드마인 B", f"pb-{tag}", "http://rm-b")
    b = src.repo["ghB"]
    src.load(cur, "ghB", [
        ("issue:5", "issue", _gh_issue(b, 5, "B 저장소 5번 작업", "", ["유형: 작업"],
                                       closed=True)),
        # 다른 도구 참조(RM-7)는 Redmine 연결이 둘이라 어느 쪽인지 정할 수 없다
        ("commit:" + "b" * 40, "commit", _gh_commit(
            b, "b" * 40, "fix(integration): B 수정  [chore]\n\n이유.\n\nRefs: GH-5, RM-7")),
    ])
    src.load(cur, "rmB", [
        ("7", "issue", _rm_issue(7, "레드마인 B 7번", "작업", closed=True)),
        ("8", "issue", _rm_issue(8, "레드마인 B 8번 시험", "시험", relations=[
            {"id": 1, "issue_id": 8, "issue_to_id": 7, "relation_type": "relates"}])),
    ])
    src.promote(cur, "ghB", "rmB")


@pytest.fixture
def sources():
    src = _Sources()
    with tx() as cur:
        _load_first(cur, src)
        _load_second(cur, src)
    yield src
    with tx() as cur:
        src.cleanup(cur)


def _issue_of(cur, cid: str, key: str) -> dict:
    return fetch_one(
        cur, "select * from issue where tool_connection_id = %s and issue_key = %s", (cid, key)
    )


def _auto_edges(cur) -> set[tuple[str, str, str, str]]:
    """(출발 연결, 출발 원천 id, 도착 연결, 도착 원천 id). 연결이 맞는지 원천 기준으로 본다."""
    cur.execute(
        """
        select coalesce(c.tool_connection_id, i.tool_connection_id)::text as from_conn,
               coalesce(c.external_id, i.external_id) as from_ext,
               i2.tool_connection_id::text as to_conn, i2.external_id as to_ext
          from trace_link tl
          left join code_change c on tl.from_type = 'CODE_CHANGE' and c.id = tl.from_id
          left join issue i on tl.from_type = 'ISSUE' and i.id = tl.from_id
          join issue i2 on tl.to_type = 'ISSUE' and i2.id = tl.to_id
         where tl.project_id = %s and tl.origin = 'AUTO' and tl.status = 'ACTIVE'
        """,
        (PID,),
    )
    return {(r["from_conn"], r["from_ext"], r["to_conn"], r["to_ext"]) for r in cur.fetchall()}


# ---------------------------------------------------------------- 독립 조회


@requires_db
def test_GitHub_연결_두_개의_같은_이슈_번호가_따로_조회된다(client, client_token, sources):
    a, b = sources.ids["ghA"], sources.ids["ghB"]
    with tx() as cur:
        ia, ib = _issue_of(cur, a, "GH-5"), _issue_of(cur, b, "GH-5")
    assert ia["id"] != ib["id"]
    assert (ia["title"], ia["status"]) == ("A 저장소 5번 작업", "OPEN")
    assert (ib["title"], ib["status"]) == ("B 저장소 5번 작업", "CLOSED")

    token = client_token("r2")
    for cid, row, repo in ((a, ia, sources.repo["ghA"]), (b, ib, sources.repo["ghB"])):
        res = client.get(
            f"/api/projects/{PID}/issues?connectionId={cid}&size=200", headers=_auth(token)
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["totalElements"] == 1
        got = body["content"][0]
        assert got["id"] == str(row["id"]) and got["key"] == "GH-5"
        assert got["source"] == {
            "tool": "GITHUB", "connectionId": cid, "externalId": "issue:5",
            "externalUrl": f"https://github.com/{repo}/issues/5",
            "connectionName": "저장소 A" if cid == a else "저장소 B",
            "target": repo, "number": "5",
        }


@requires_db
def test_Redmine_연결_두_개의_같은_이슈_번호가_따로_조회된다(client, client_token, sources):
    a, b = sources.ids["rmA"], sources.ids["rmB"]
    with tx() as cur:
        ia, ib = _issue_of(cur, a, "RM-7"), _issue_of(cur, b, "RM-7")
    assert ia["id"] != ib["id"]
    assert (ia["title"], ia["status"]) == ("레드마인 A 7번", "OPEN")
    assert ib["title"] == "레드마인 B 7번" and ib["status"] in ("RESOLVED", "CLOSED")
    assert ia["external_url"] == "http://rm-a/issues/7"
    assert ib["external_url"] == "http://rm-b/issues/7"

    token = client_token("r2")
    res = client.get(f"/api/projects/{PID}/issues?connectionId={b}&size=200",
                     headers=_auth(token))
    keys = {(r["key"], r["source"]["connectionName"], r["source"]["number"])
            for r in res.json()["content"]}
    assert keys == {("RM-7", "레드마인 B", "7"), ("RM-8", "레드마인 B", "8")}

    summary = client.get(f"/api/projects/{PID}/issues/summary?connectionId={b}",
                         headers=_auth(token)).json()
    assert summary["total"] == 2 and summary["open"] == 1
    counts = {s["connectionId"]: s["count"] for s in summary["sources"]}
    # 연결을 골라 물어도 고르기 목록은 사업 전체 연결을 낸다
    assert counts[a] == 2 and counts[b] == 2
    assert counts[sources.ids["ghA"]] == 1 and counts[sources.ids["ghB"]] == 1


# ---------------------------------------------------------------- 추적 링크


@requires_db
def test_추적_링크와_원문_링크가_제_연결을_가리킨다(sources):
    ids = sources.ids
    with tx() as cur:
        result = trace_service.build_project_links(cur, PID)
        edges = _auto_edges(cur)
        ia, ib = _issue_of(cur, ids["ghA"], "GH-5"), _issue_of(cur, ids["ghB"], "GH-5")
        labels = repository.entity_labels(
            cur, {("ISSUE", str(ia["id"])), ("ISSUE", str(ib["id"]))}
        )

    assert (ids["ghA"], "commit:" + "a" * 40, ids["ghA"], "issue:5") in edges
    assert (ids["ghB"], "commit:" + "b" * 40, ids["ghB"], "issue:5") in edges
    assert (ids["rmA"], "8", ids["rmA"], "7") in edges
    assert (ids["rmB"], "8", ids["rmB"], "7") in edges
    # 연결을 건너가는 변은 하나도 없다
    assert all(f == t for f, _, t, _ in edges), edges
    # B 커밋의 RM-7 은 Redmine 연결이 둘이라 고르지 않는다. 미해결로 남는다
    assert not any(e[1] == "commit:" + "b" * 40 and e[3] == "7" for e in edges)
    assert result.ambiguous == 1

    # 추적 셀 이름에 연결이 붙고, 원문 링크는 각자의 저장소다
    assert labels[("ISSUE", str(ia["id"]))] == (
        "GH-5 · 저장소 A", f"https://github.com/{sources.repo['ghA']}/issues/5")
    assert labels[("ISSUE", str(ib["id"]))] == (
        "GH-5 · 저장소 B", f"https://github.com/{sources.repo['ghB']}/issues/5")


@requires_db
def test_다시_수집해도_중복_덮어쓰기_상태_혼입이_없다(sources):
    ids = sources.ids
    with tx() as cur:
        trace_service.build_project_links(cur, PID)
        before = _auto_edges(cur)
        ia = _issue_of(cur, ids["ghA"], "GH-5")

        # B 의 5번만 다시 열렸다. A 의 5번은 그대로여야 한다
        b = sources.repo["ghB"]
        sources.load(cur, "ghB", [("issue:5", "issue", _gh_issue(
            b, 5, "B 저장소 5번 작업 (재오픈)", "", ["유형: 작업"]))])
        sources.promote(cur)
        sources.promote(cur)
        trace_service.build_project_links(cur, PID)
        after = _auto_edges(cur)

        cur.execute(
            "select tool_connection_id::text as cid, external_id, count(*) as n from issue "
            "where tool_connection_id = any(%s::uuid[]) group by 1, 2",
            (list(ids.values()),),
        )
        per_source = {(r["cid"], r["external_id"]): r["n"] for r in cur.fetchall()}
        ia2 = _issue_of(cur, ids["ghA"], "GH-5")
        ib2 = _issue_of(cur, ids["ghB"], "GH-5")

    assert set(per_source.values()) == {1}
    assert len(per_source) == 6  # GH A 5 · GH B 5 · RM A 7·8 · RM B 7·8. 요구사항 이슈는 제외
    assert (ia2["id"], ia2["title"], ia2["status"]) == (ia["id"], ia["title"], "OPEN")
    assert (ib2["title"], ib2["status"]) == ("B 저장소 5번 작업 (재오픈)", "OPEN")
    assert after == before


# ---------------------------------------------------------------- 권한


@requires_db
def test_연결_필터가_사업_접근_권한을_우회하지_않는다(client, client_token, sources):
    with tx() as cur:
        client_org = fetch_one(cur, "select client_org_id from project where id = %s",
                               (PID,))["client_org_id"]
        other = str(fetch_one(
            cur,
            """
            insert into project (client_org_id, name, start_date, end_date, description)
            values (%s, %s, '2026-08-01', '2026-11-30', '연결 필터 권한 시험')
            returning id
            """,
            (client_org, f"연결필터-{uuid.uuid4().hex[:6]}"),
        )["id"])
        sources.extra_projects.append(other)
        foreign = sources.connect(cur, "ghX", "GITHUB", "다른 사업 저장소",
                                  f"x/other-{uuid.uuid4().hex[:6]}",
                                  "https://api.github.com", project_id=other)
        sources.load(cur, "ghX", [("issue:5", "issue", _gh_issue(
            sources.repo["ghX"], 5, "다른 사업 5번", "", ["유형: 작업"]))])
        sources.promote(cur, "ghX")

    token = _auth(client_token("r3"))
    # 다른 사업의 연결 id 를 내 사업 목록에 넣어도 그 사업 이슈는 안 나온다
    res = client.get(f"/api/projects/{PID}/issues?connectionId={foreign}", headers=token)
    assert res.status_code == 200 and res.json()["totalElements"] == 0
    summary = client.get(f"/api/projects/{PID}/issues/summary?connectionId={foreign}",
                         headers=token).json()
    assert summary["total"] == 0
    assert foreign not in {s["connectionId"] for s in summary["sources"]}
    # 배정되지 않은 사업은 연결 id 를 붙여도 거절이다
    assert client.get(f"/api/projects/{other}/issues?connectionId={foreign}",
                      headers=token).status_code == 403
    assert client.get(f"/api/projects/{other}/issues/summary?connectionId={foreign}",
                      headers=token).status_code == 403
    # 형식이 틀린 id 는 DB 까지 가지 않는다
    assert client.get(f"/api/projects/{PID}/issues?connectionId=x' or 1=1",
                      headers=token).status_code == 400


# ---------------------------------------------------------------- 기존 데이터


@requires_db
def test_두_번째_연결을_붙여도_기존_이슈_링크_수동_링크가_남는다():
    src = _Sources()
    try:
        with tx() as cur:
            _load_first(cur, src)
            trace_service.build_project_links(cur, PID)
            cur.execute(
                "select id, from_id, to_id from trace_link "
                "where project_id = %s and origin = 'AUTO' and status = 'ACTIVE'",
                (PID,),
            )
            links_before = {str(r["id"]): (r["from_id"], r["to_id"]) for r in cur.fetchall()}
            issue_ids = {
                key: _issue_of(cur, src.ids[conn], key)["id"]
                for conn, key in (("ghA", "GH-5"), ("rmA", "RM-7"), ("rmA", "RM-8"))
            }
            req = fetch_one(cur, "select id from requirement where code = 'SWFR.CON.002' "
                                 "and tool_connection_id = %s", (src.ids["ghA"],))
            manual = fetch_one(
                cur,
                """
                insert into trace_link
                  (project_id, from_type, from_id, to_type, to_id, link_kind, origin)
                values (%s, 'ISSUE', %s, 'REQUIREMENT', %s, 'IMPLEMENTS', 'MANUAL')
                returning id
                """,
                (PID, issue_ids["RM-7"], req["id"]),
            )["id"]

        with tx() as cur:
            _load_second(cur, src)
            trace_service.build_project_links(cur, PID)
            cur.execute(
                "select id, from_id, to_id, status from trace_link where id = any(%s::uuid[])",
                (list(links_before),),
            )
            links_after = {str(r["id"]): (r["from_id"], r["to_id"], r["status"])
                           for r in cur.fetchall()}
            manual_after = fetch_one(cur, "select origin, status from trace_link where id = %s",
                                     (manual,))
            ids_after = {
                key: _issue_of(cur, src.ids[conn], key)["id"]
                for conn, key in (("ghA", "GH-5"), ("rmA", "RM-7"), ("rmA", "RM-8"))
            }
            cur.execute("delete from trace_link where id = %s", (manual,))

        assert len(links_before) >= 2
        # 같은 링크가 같은 id 로 같은 양 끝을 잇고 살아 있다
        assert links_after == {k: (*v, "ACTIVE") for k, v in links_before.items()}
        assert manual_after == {"origin": "MANUAL", "status": "ACTIVE"}
        assert ids_after == issue_ids
    finally:
        with tx() as cur:
            src.cleanup(cur)
