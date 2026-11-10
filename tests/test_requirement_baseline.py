"""요구사항 기준선 1단계 (GH-139, SWFR.PIP.002, ARC-028, ARC-030).

명세서 등록 → 추출 결과 정리 → 용역사 제출 → 발주기관 확정. 확정 전 목록은 요구사항으로
보이지 않고, 확정은 기존 요구사항을 코드로 이어 ID·링크·지정·이력을 그대로 둔다. 이슈 수집은
요구사항을 만들거나 정의를 덮지 않는다.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.ai.embedding import embedding_port
from app.common import crypto
from app.db import fetch_all, fetch_one, tx
from app.integration import repository as integ_repo
from app.standard import service as standard
from app.standard import trace_service
from tests.conftest import requires_db, seed_issue_requirements

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _gh_issue(number: int, title: str, labels: list[str], closed: bool = False,
              body: str = "| 중요도 | 필수 |") -> dict:
    return {
        "number": number, "title": title, "body": body,
        "labels": [{"name": n} for n in labels],
        "state": "closed" if closed else "open",
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z",
        "html_url": f"https://github.com/x/base/issues/{number}",
    }


def _connect(cur, name: str = "기준선 시험 저장소", project_id: str = PID) -> dict:
    cur.execute("select organization_id from app_user where username = 'r3'")
    org = str(cur.fetchone()["organization_id"])
    conn = integ_repo.insert(
        cur, project_id, org, "GITHUB", name, "https://api.github.com",
        f"x/base-{uuid.uuid4().hex[:6]}", crypto.encrypt("k"), "k***", {},
    )
    return conn


def _load(cur, conn: dict, items: list[tuple[str, dict]]) -> None:
    cid = str(conn["id"])
    job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
    for external_id, payload in items:
        integ_repo.upsert_raw_artifact(cur, cid, external_id, "issue", payload, job)
    now = datetime.now(UTC)
    integ_repo.finish_sync_job(cur, job, "SUCCEEDED", {}, now, now)


def _promote(cur, conn_id: str):
    cur.execute("select * from tool_connection where id = %s", (conn_id,))
    return standard.promote_connection(cur, cur.fetchone(), embedding_port())


def _cleanup(cur, conn_ids: list[str], codes: list[str], project_id: str = PID) -> None:
    cur.execute("delete from requirement_baseline where project_id = %s", (project_id,))
    cur.execute("delete from requirement_unresolved_ref where project_id = %s", (project_id,))
    cur.execute(
        "delete from trace_link where project_id = %s and origin = 'AUTO'", (project_id,)
    )
    cur.execute(
        "delete from entity_history where entity_type = 'REQUIREMENT' and entity_id in "
        "(select id from requirement where project_id = %s and "
        "(code = any(%s) or tool_connection_id = any(%s::uuid[])))",
        (project_id, codes, conn_ids),
    )
    cur.execute(
        "delete from requirement where project_id = %s and "
        "(code = any(%s) or tool_connection_id = any(%s::uuid[]))",
        (project_id, codes, conn_ids),
    )
    cur.execute("delete from issue where tool_connection_id = any(%s::uuid[])", (conn_ids,))
    cur.execute("delete from tool_connection where id = any(%s::uuid[])", (conn_ids,))


# ---------------------------------------------------------------- 잠재 결함 재현


@requires_db
def test_명세서_요구사항과_같은_코드의_이슈는_일반_이슈로_들어와_추적으로_이어진다():
    """요구사항은 명세서로만 만든다(ARC-030). 같은 코드를 제목에 단 이슈가 들어와도 요구사항의
    정의와 원천은 그대로고, 이슈는 일반 이슈가 되어 그 코드로 이어진다. 다시 수집해도 같다.
    (10-14 결함 GH-139: 전에는 이 경우 uq_requirement__code 위반으로 수집 전체가 실패했다)"""
    code = "SWFR.TST.901"
    with tx() as cur:
        conn = _connect(cur)
        cid = str(conn["id"])
    try:
        for _ in range(2):
            with tx() as cur:
                doc_req = fetch_one(cur, "select id from requirement where project_id = %s "
                                         "and code = %s", (PID, code))
                if doc_req is None:
                    doc_req = fetch_one(
                        cur,
                        """
                        insert into requirement (project_id, code, title, body, priority,
                                                 status, evidence_status, source_kind)
                        values (%s, %s, '명세서 제목', '명세서 본문', 'MUST', 'DEFINED',
                                'DEFINED', 'DOCUMENT')
                        returning id
                        """,
                        (PID, code),
                    )
                _load(cur, conn, [("issue:31", _gh_issue(
                    31, f"[{code}] 이슈 제목", ["유형: 요구사항"], closed=True,
                    body="이슈 본문"))])
                _promote(cur, cid)
                trace_service.build_project_links(cur, PID)
                rows = fetch_all(
                    cur, "select * from requirement where project_id = %s and code = %s",
                    (PID, code),
                )
                issue = fetch_one(cur, "select id, issue_key from issue "
                                       "where tool_connection_id = %s", (cid,))
                link = fetch_one(
                    cur, "select status from trace_link where from_type = 'ISSUE' "
                         "and from_id = %s and to_type = 'REQUIREMENT' and to_id = %s",
                    (issue["id"], doc_req["id"]),
                )
            assert len(rows) == 1
            row = rows[0]
            assert row["id"] == doc_req["id"]
            assert (row["title"], row["body"]) == ("명세서 제목", "명세서 본문")
            assert row["tool_connection_id"] is None and row["evidence_status"] == "DEFINED"
            assert issue["issue_key"] == "GH-31"
            assert link == {"status": "ACTIVE"}
    finally:
        with tx() as cur:
            _cleanup(cur, [cid], [code])


# ---------------------------------------------------------------- 공통


def _spec_table(rows: list[tuple[str, str, str]]) -> str:
    lines = ["# 요구사항 명세서 v1.0", "", "| 요구사항 ID | 요구사항 명칭 | 중요도 |",
             "|---|---|---|"]
    lines += [f"| {c} | {t} | {p} |" for c, t, p in rows]
    return "\n".join(lines) + "\n"


def _document(cur, text: str, project_id: str = PID) -> str:
    user = fetch_one(cur, "select id from app_user where username = 'r3'")["id"]
    return str(fetch_one(
        cur,
        """
        insert into document_upload (project_id, uploaded_by_user_id, original_filename,
                                     stored_path, content_type, file_ext, size_bytes, file_hash,
                                     extracted_text, status)
        values (%s, %s, '요구사항명세서.docx', 'x/spec.docx', 'application/octet-stream',
                'DOCX', 10, %s, %s, 'STRUCTURED')
        returning id
        """,
        (project_id, user, uuid.uuid4().hex + uuid.uuid4().hex, text),
    )["id"])


def _base(project_id: str = PID) -> str:
    return f"/api/projects/{project_id}/requirement-baseline"


def _req_codes(cur, project_id: str = PID) -> dict[str, dict]:
    rows = fetch_all(cur, "select * from requirement where project_id = %s and code is not null",
                     (project_id,))
    return {r["code"]: r for r in rows}


@pytest.fixture
def clean():
    """시험이 쓴 기준선·요구사항·연결·문서를 지운다."""
    made: dict[str, list[str]] = {"conns": [], "codes": [], "docs": [], "projects": [],
                                  "orgs": []}
    yield made
    with tx() as cur:
        for pid in [PID, *made["projects"]]:
            _cleanup(cur, made["conns"], made["codes"], pid)
        cur.execute("delete from code_change where tool_connection_id = any(%s::uuid[])",
                    (made["conns"],))
        cur.execute("delete from document_upload where id = any(%s::uuid[])", (made["docs"],))
        for pid in made["projects"]:
            cur.execute("delete from project where id = %s", (pid,))
        for oid in made["orgs"]:
            cur.execute("delete from organization where id = %s", (oid,))


# ---------------------------------------------------------------- 신규 사업 흐름


@requires_db
def test_신규_사업은_등록_정리_제출_확정을_거쳐서만_요구사항이_생긴다(client, client_token, clean):
    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    codes = ["SWFR.TST.101", "SWFR.TST.102", "SWFR.TST.103", "REQ-104"]
    clean["codes"] += codes
    with tx() as cur:
        doc = _document(cur, _spec_table([
            ("SWFR.TST.101", "로그인한다", "필수"),
            ("SWFR.TST.102", "목록을 본다", "필수"),
            ("SWFR.TST.102", "목록을 본다(중복)", "필수"),
            ("SWFR-TST", "코드 꼴이 아닌 행", "권장"),
            ("REQ-104", "다른 사업 표기", "선택"),
        ]))
        clean["docs"].append(doc)

    assert client.get(_base(), headers=po).json()["state"] == "NONE"
    # 발주기관은 명세서를 등록하지 않는다
    assert client.post(_base(), json={"documentId": doc}, headers=po).status_code == 403

    created = client.post(_base(), json={"documentId": doc}, headers=pm)
    assert created.status_code == 201, created.text
    b = created.json()
    bid = b["id"]
    assert b["status"] == "DRAFT" and b["sourceFilename"] == "요구사항명세서.docx"
    assert b["sourceDocVersion"] == "1.0"
    problems = {(i["code"], i["location"]): i["problems"] for i in b["items"]}
    # 버리는 행이 없다. 중복·꼴 문제는 위치와 함께 남는다
    assert problems == {
        ("SWFR.TST.101", "표 1 · 2행"): [],
        ("SWFR.TST.102", "표 1 · 3행"): ["DUPLICATE_CODE"],
        ("SWFR.TST.102", "표 1 · 4행"): ["DUPLICATE_CODE"],
        ("SWFR-TST", "표 1 · 5행"): ["INVALID_CODE"],
        ("REQ-104", "표 1 · 6행"): ["UNTRACEABLE_CODE"],
    }
    assert b["blockingCount"] == 3
    assert {i["match"] for i in b["items"] if i["code"] == "SWFR.TST.101"} == {"NEW"}

    # 작성 중 목록은 요구사항이 아니다. 요구사항 목록·건수에 안 나온다
    listed = client.get(f"/api/projects/{PID}/requirements?size=200", headers=po).json()
    assert not {r["code"] for r in listed["content"]} & set(codes)
    # 발주기관에게는 작성 중 목록 자체가 보이지 않는다
    seen = client.get(_base(), headers=po).json()
    assert seen["state"] == "DRAFT" and seen["working"] is None
    assert client.get(f"{_base()}/{bid}", headers=po).status_code == 403
    # 같은 사업에 두 번째 작성 중 기준선은 없다
    assert client.post(_base(), json={"documentId": doc}, headers=pm).status_code == 409

    # 고칠 것이 남아 있으면 제출되지 않는다
    blocked = client.post(f"{_base()}/{bid}/submit", headers=pm)
    assert blocked.status_code == 400 and "3건" in blocked.json()["message"]

    by_loc = {i["location"]: i["id"] for i in b["items"]}
    client.delete(f"{_base()}/{bid}/items/{by_loc['표 1 · 4행']}", headers=pm)
    fixed = client.put(f"{_base()}/{bid}/items/{by_loc['표 1 · 5행']}", headers=pm, json={
        "code": "SWFR.TST.103", "title": "코드를 바로잡은 행", "priority": "SHOULD"})
    assert fixed.status_code == 200
    item = next(i for i in fixed.json()["items"] if i["code"] == "SWFR.TST.103")
    assert item["edited"] is True and item["location"] == "표 1 · 5행"
    assert fixed.json()["blockingCount"] == 0

    submitted = client.post(f"{_base()}/{bid}/submit", headers=pm)
    assert submitted.status_code == 200 and submitted.json()["status"] == "SUBMITTED"
    # 제출 뒤에는 고칠 수 없다
    assert client.put(f"{_base()}/{bid}/items/{by_loc['표 1 · 2행']}", headers=pm, json={
        "code": "SWFR.TST.101", "title": "x"}).status_code == 409
    with tx() as cur:
        assert not set(_req_codes(cur)) & set(codes)

    # 발주기관이 보고 돌려보낸다. 용역사는 확정할 수 없다
    assert client.get(f"{_base()}/{bid}", headers=po).status_code == 200
    assert client.post(f"{_base()}/{bid}/confirm", json={}, headers=pm).status_code == 403
    returned = client.post(f"{_base()}/{bid}/return", json={"reason": "중요도 다시"},
                           headers=po)
    assert returned.json()["status"] == "DRAFT"
    assert returned.json()["returnedReason"] == "중요도 다시"
    assert client.post(f"{_base()}/{bid}/submit", headers=pm).status_code == 200

    confirmed = client.post(f"{_base()}/{bid}/confirm", json={}, headers=po)
    assert confirmed.status_code == 200, confirmed.text
    c = confirmed.json()
    assert c["status"] == "CONFIRMED" and c["confirmedByRole"] == "CLIENT"
    assert c["counts"] == {"NEW": 4, "SAME": 0, "CHANGED": 0}

    with tx() as cur:
        rows = _req_codes(cur)
    assert {k: rows[k]["source_kind"] for k in codes} == dict.fromkeys(codes, "DOCUMENT")
    assert all(rows[k]["baseline_id"] is not None for k in codes)
    assert rows["SWFR.TST.103"]["title"] == "코드를 바로잡은 행"
    listed = client.get(f"/api/projects/{PID}/requirements?size=200", headers=po).json()
    mine = {r["code"]: r for r in listed["content"] if r["code"] in codes}
    assert len(mine) == 4 and all(r["inBaseline"] for r in mine.values())

    state = client.get(_base(), headers=po).json()
    assert state["state"] == "CONFIRMED" and state["confirmed"]["version"] == 1

    # 등록·제출·돌려보냄(사유)·확정이 활동 기록에 남는다(AC-020-9·AC-021-8, DEF-V034).
    # 상대 역할 알림은 DEC-08 이라 활동 탭에만(LOG) 둔다
    with tx() as cur:
        acts = fetch_all(cur, """
            select kind, audience, summary from activity_event
             where target_type = 'REQUIREMENT_BASELINE' and target_key = %s
             order by occurred_at, id""", (bid,))
        cur.execute("delete from activity_event where target_key = %s", (bid,))
    assert [a["kind"] for a in acts] == [
        "BASELINE_REGISTERED", "BASELINE_SUBMITTED", "BASELINE_RETURNED",
        "BASELINE_SUBMITTED", "BASELINE_CONFIRMED",
    ]
    assert {a["audience"] for a in acts} == {"LOG"}
    assert "사유: 중요도 다시" in acts[2]["summary"]
    shown = client.get(f"/api/projects/{PID}/activity?size=50", headers=pm)
    assert shown.status_code == 200

    # 요구사항 상세에서 명세서 판본과 원문 위치로 바로 간다(GH-158)
    detail = client.get(
        f"/api/projects/{PID}/requirements/{mine['SWFR.TST.103']['id']}", headers=po
    ).json()
    src = detail["baselineSource"]
    assert src["baselineId"] == bid and src["version"] == 1 and src["status"] == "CONFIRMED"
    assert src["sourceFilename"] == "요구사항명세서.docx" and src["sourceDocVersion"] == "1.0"
    assert src["location"] == "표 1 · 5행" and src["match"] == "NEW"
    assert src["documentId"] == doc and src["confirmedAt"] is not None
    assert any(h["field"] == "baseline" for h in detail["history"])

    # 같은 확정을 또 보내거나, 확정 뒤 새 명세서를 올려도 기준선은 그대로다
    assert client.post(f"{_base()}/{bid}/confirm", json={}, headers=po).status_code == 409
    again = client.post(_base(), json={"documentId": doc}, headers=pm)
    assert again.status_code == 409 and again.json()["code"] == "BASELINE_CONFIRMED"


@requires_db
def test_명세서로_등록된_문서는_등록이_살아_있는_동안_지우지_못한다(client, client_token, clean):
    """AC-020-8 (GH-218). 등록을 취소하면 지울 수 있다."""
    pm = _auth(client_token("r3"))
    with tx() as cur:
        doc = _document(cur, _spec_table([("SWFR.TST.301", "삭제 보호", "필수")]))
        clean["docs"].append(doc)
        clean["codes"].append("SWFR.TST.301")
    bid = client.post(_base(), json={"documentId": doc}, headers=pm).json()["id"]
    blocked = client.delete(f"/api/documents/{doc}", headers=pm)
    assert blocked.status_code == 409 and blocked.json()["code"] == "DOCUMENT_IN_BASELINE"
    assert client.get(f"/api/documents/{doc}", headers=pm).status_code == 200
    assert client.delete(f"{_base()}/{bid}", headers=pm).status_code == 204
    assert client.delete(f"/api/documents/{doc}", headers=pm).status_code == 204


@requires_db
def test_요구사항_라벨이_붙은_이슈도_일반_이슈로_들어온다(client, client_token, clean):
    """예전 요구사항 라벨·제목 꼴의 이슈를 받아도 요구사항이 되지 않는다."""
    pm = _auth(client_token("r3"))
    res = client.post(f"/api/projects/{PID}/connections", headers=pm, json={
        "tool": "GITHUB", "name": "새 저장소", "baseUrl": "https://api.github.com",
        "targetResource": f"x/new-{uuid.uuid4().hex[:6]}",
        "credential": {"accessToken": "ghp_x"},
    })
    assert res.status_code == 201, res.text
    cid = res.json()["id"]
    clean["conns"].append(cid)
    clean["codes"].append("SWFR.TST.501")
    with tx() as cur:
        conn = integ_repo.find_by_id(cur, cid)
        _load(cur, conn, [("issue:7", _gh_issue(7, "[SWFR.TST.501] 요구사항 라벨",
                                                 ["유형: 요구사항"]))])
        _promote(cur, cid)
        assert "SWFR.TST.501" not in _req_codes(cur)
        issue = fetch_one(cur, "select issue_key from issue where tool_connection_id = %s",
                          (cid,))
    assert issue["issue_key"] == "GH-7"


# ---------------------------------------------------------------- 기존 사업 전환


def _legacy_project(cur, clean) -> dict:
    """ARC-030 전처럼 GitHub 이슈로 요구사항을 만들어 온 사업. 지정·수동 링크·이력이 있다."""
    conn = _connect(cur)
    cid = str(conn["id"])
    clean["conns"].append(cid)
    clean["codes"] += ["SWFR.TST.201", "SWFR.TST.202", "SWFR.TST.203", "SWFR.TST.204",
                       "SWFR.TST.205"]
    items = [
        ("issue:1", _gh_issue(1, "[SWFR.TST.201] 같은 제목", ["유형: 요구사항"])),
        ("issue:2", _gh_issue(2, "[SWFR.TST.202] 이슈 쪽 제목", ["유형: 요구사항"])),
        ("issue:3", _gh_issue(3, "[SWFR.TST.203] 명세서에 없는 요구사항", ["유형: 요구사항"])),
        ("issue:9", _gh_issue(9, "작업 이슈", ["유형: 작업"])),
    ]
    _load(cur, conn, items)
    seed_issue_requirements(cur, PID, cid, items)
    _promote(cur, cid)
    rows = _req_codes(cur)
    a, b = rows["SWFR.TST.201"], rows["SWFR.TST.202"]
    cur.execute(
        "update requirement set decided_status = 'VERIFIED', decided_reason = '시험 결과 확인', "
        "decided_at = now(), status = 'VERIFIED' where id = %s", (a["id"],))
    issue = fetch_one(cur, "select id from issue where tool_connection_id = %s", (cid,))
    manual = fetch_one(
        cur,
        """
        insert into trace_link (project_id, from_type, from_id, to_type, to_id, link_kind, origin)
        values (%s, 'ISSUE', %s, 'REQUIREMENT', %s, 'IMPLEMENTS', 'MANUAL') returning id
        """,
        (PID, issue["id"], b["id"]),
    )["id"]
    cur.execute(
        "insert into entity_history (entity_type, entity_id, project_id, field, from_value, "
        "to_value, actor) values ('REQUIREMENT', %s, %s, 'status', 'DEFINED', 'VERIFIED', "
        "'발주 담당')", (a["id"], PID))
    doc = _document(cur, _spec_table([
        ("SWFR.TST.201", "같은 제목", "필수"),
        ("SWFR.TST.202", "명세서 쪽 제목", "필수"),
        ("SWFR.TST.204", "명세서에만 있는 요구사항", "권장"),
    ]))
    clean["docs"].append(doc)
    return {"conn": conn, "cid": cid, "a": a, "b": b, "c": rows["SWFR.TST.203"],
            "manual": str(manual), "doc": doc}


def _submitted(client, pm, doc) -> dict:
    b = client.post(_base(), json={"documentId": doc}, headers=pm).json()
    res = client.post(f"{_base()}/{b['id']}/submit", headers=pm)
    assert res.status_code == 200, res.text
    return res.json()


@requires_db
def test_기존_요구사항은_ID_링크_지정_이력을_그대로_두고_기준선에_붙는다(
    client, client_token, clean
):
    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    with tx() as cur:
        legacy = _legacy_project(cur, clean)
    sub = _submitted(client, pm, legacy["doc"])

    # 확정 전 미리보기: 같은 코드 둘(같음·다름), 새 코드 하나, 명세서에 없는 기존 코드 하나
    assert sub["counts"] == {"NEW": 1, "SAME": 1, "CHANGED": 1}
    changed = next(i for i in sub["items"] if i["code"] == "SWFR.TST.202")
    assert changed["match"] == "CHANGED"
    assert changed["existing"]["title"] == "이슈 쪽 제목"
    assert changed["existing"]["source"] == "기준선 시험 저장소"
    assert "SWFR.TST.203" in {m["code"] for m in sub["missing"]}

    # 내용이 같은 코드는 명세서로 바꿀 대상이 아니다. 거절되고 아무것도 안 바뀐다
    bad = client.post(f"{_base()}/{sub['id']}/confirm",
                      json={"applySpecCodes": ["SWFR.TST.201"]}, headers=po)
    assert bad.status_code == 400
    assert client.get(_base(), headers=po).json()["state"] == "SUBMITTED"

    done = client.post(f"{_base()}/{sub['id']}/confirm", json={}, headers=po)
    assert done.status_code == 200, done.text
    assert {m["code"] for m in done.json()["missing"]} >= {"SWFR.TST.203"}

    with tx() as cur:
        rows = _req_codes(cur)
        a, b, c = rows["SWFR.TST.201"], rows["SWFR.TST.202"], rows["SWFR.TST.203"]
        manual = fetch_one(cur, "select status, origin from trace_link where id = %s",
                           (legacy["manual"],))
        history = fetch_all(
            cur, "select field, to_value from entity_history where entity_id = %s "
            "order by changed_at", (a["id"],))
    # ID 그대로, 원천 연결 그대로, 지정 그대로
    assert (a["id"], b["id"], c["id"]) == (
        legacy["a"]["id"], legacy["b"]["id"], legacy["c"]["id"])
    assert str(a["tool_connection_id"]) == legacy["cid"]
    assert (a["decided_status"], a["status"]) == ("VERIFIED", "VERIFIED")
    # 내용이 달라도 기본으로 기존 정의를 둔다
    assert b["title"] == "이슈 쪽 제목"
    # 명세서에 없던 기존 코드는 지우지 않고 기준선 밖으로 남는다
    assert c["baseline_id"] is None and a["baseline_id"] is not None
    assert rows["SWFR.TST.204"]["source_kind"] == "DOCUMENT"
    assert manual == {"status": "ACTIVE", "origin": "MANUAL"}
    assert [h["field"] for h in history] == ["status", "baseline"]
    assert history[1]["to_value"] == "v1 SAME"


@requires_db
def test_발주기관이_고른_코드만_명세서_내용으로_바뀌고_이력이_남는다(client, client_token, clean):
    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    with tx() as cur:
        legacy = _legacy_project(cur, clean)
    sub = _submitted(client, pm, legacy["doc"])
    done = client.post(f"{_base()}/{sub['id']}/confirm",
                       json={"applySpecCodes": ["SWFR.TST.202"]}, headers=po)
    assert done.status_code == 200, done.text
    item = next(i for i in done.json()["items"] if i["code"] == "SWFR.TST.202")
    assert item["specApplied"] is True and item["existing"]["title"] == "이슈 쪽 제목"
    with tx() as cur:
        b = _req_codes(cur)["SWFR.TST.202"]
        history = fetch_all(
            cur, "select field, from_value, to_value from entity_history "
            "where entity_id = %s order by changed_at, field desc", (b["id"],))
    assert b["id"] == legacy["b"]["id"] and b["title"] == "명세서 쪽 제목"
    assert {"field": "title", "from_value": "이슈 쪽 제목", "to_value": "명세서 쪽 제목"} in history


@requires_db
def test_확정_뒤_재수집은_요구사항을_만들거나_정의_지정을_덮지_않는다(client, client_token, clean):
    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    with tx() as cur:
        legacy = _legacy_project(cur, clean)
    sub = _submitted(client, pm, legacy["doc"])
    assert client.post(f"{_base()}/{sub['id']}/confirm", json={}, headers=po).status_code == 200

    with tx() as cur:
        _load(cur, legacy["conn"], [
            # 요구사항 이슈의 제목이 바뀌고 닫혔다
            ("issue:1", _gh_issue(1, "[SWFR.TST.201] 이슈에서 바꾼 제목", ["유형: 요구사항"],
                                  closed=True)),
            ("issue:2", _gh_issue(2, "[SWFR.TST.202] 또 바꾼 제목", ["유형: 요구사항"],
                                  closed=True)),
            # 확정 뒤 새로 단 요구사항 라벨. 요구사항이 되지 않는다
            ("issue:5", _gh_issue(5, "[SWFR.TST.205] 새 요구사항 이슈", ["유형: 요구사항"])),
        ])
        _promote(cur, legacy["cid"])
        rows = _req_codes(cur)
        new_issue = fetch_one(cur, "select issue_key from issue where tool_connection_id = %s "
                                   "and external_id = 'issue:5'", (legacy["cid"],))
    a, b = rows["SWFR.TST.201"], rows["SWFR.TST.202"]
    assert "SWFR.TST.205" not in rows and new_issue["issue_key"] == "GH-5"
    assert a["title"] == "같은 제목" and b["title"] == "이슈 쪽 제목"
    # 근거 상태는 원천을 따르고, 지정은 그대로다
    assert (a["evidence_status"], a["status"]) == ("IMPLEMENTED", "VERIFIED")
    assert (b["evidence_status"], b["status"]) == ("IMPLEMENTED", "IMPLEMENTED")


def _principal(cur, username: str):
    from app.auth.models import AuthPrincipal

    row = fetch_one(
        cur,
        "select u.id, u.organization_id, u.role, o.type from app_user u "
        "join organization o on o.id = u.organization_id where u.username = %s",
        (username,),
    )
    return AuthPrincipal(user_id=str(row["id"]), org_id=str(row["organization_id"]),
                         org_type=row["type"], role=row["role"])


@requires_db
def test_확정_중_실패하면_아무것도_바뀌지_않는다(client, client_token, clean, monkeypatch):
    from app.standard import baseline as baseline_service

    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    with tx() as cur:
        legacy = _legacy_project(cur, clean)
    sub = _submitted(client, pm, legacy["doc"])

    def broken(*args, **kwargs):
        raise RuntimeError("확정을 적다 실패")

    monkeypatch.setattr(baseline_service.repo, "set_confirmed", broken)
    with pytest.raises(RuntimeError), tx() as cur:
        baseline_service.confirm(cur, _principal(cur, "r2"), PID, sub["id"], [])
    monkeypatch.undo()

    with tx() as cur:
        rows = _req_codes(cur)
        status = fetch_one(cur, "select status from requirement_baseline where id = %s",
                           (sub["id"],))["status"]
        items = fetch_all(cur, "select match_result from requirement_baseline_item "
                               "where baseline_id = %s", (sub["id"],))
    assert status == "SUBMITTED"
    assert "SWFR.TST.204" not in rows
    assert all(r["baseline_id"] is None for k, r in rows.items() if k.startswith("SWFR.TST."))
    assert {i["match_result"] for i in items} == {None}
    # 다시 확정하면 된다
    assert client.post(f"{_base()}/{sub['id']}/confirm", json={}, headers=po).status_code == 200


# ---------------------------------------------------------------- 미해결 참조


@requires_db
def test_없는_요구사항_ID_참조는_잇지_않고_미해결로_보인다(client, client_token, clean):
    from app.standard import trace_service

    po = _auth(client_token("r2"))
    with tx() as cur:
        conn = _connect(cur)
        cid = str(conn["id"])
        clean["conns"].append(cid)
        clean["codes"].append("SWFR.TST.301")
        job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
        integ_repo.upsert_raw_artifact(cur, cid, "commit:" + "e" * 40, "commit", {
            "sha": "e" * 40,
            "commit": {"message": "feat(standard): 아직 없는 요구사항  [SWFR.TST.301]",
                       "author": {"name": "x", "date": "2026-10-03T00:00:00Z"}},
            "html_url": "https://github.com/x/base/commit/" + "e" * 40,
        }, job)
        now = datetime.now(UTC)
        integ_repo.finish_sync_job(cur, job, "SUCCEEDED", {}, now, now)
        _promote(cur, cid)
        result = trace_service.build_project_links(cur, PID)
        links = fetch_one(cur, "select count(*) as n from trace_link tl join code_change c "
                               "on c.id = tl.from_id where c.tool_connection_id = %s", (cid,))
        doc = _document(cur, _spec_table([("SWFR.TST.301", "나중에 생긴 요구사항", "필수")]))
        clean["docs"].append(doc)

    assert links["n"] == 0 and result.unknown_codes >= 1
    refs = client.get(f"/api/projects/{PID}/requirements/unresolved-refs", headers=po).json()
    mine = [r for r in refs if r["code"] == "SWFR.TST.301"]
    assert len(mine) == 1
    assert mine[0]["sourceType"] == "CODE_CHANGE"
    assert mine[0]["evidenceText"].endswith("[SWFR.TST.301]")
    assert client.get(_base(), headers=po).json()["unresolvedCodeCount"] >= 1

    # 기준선에 그 코드가 들어오면 확정과 함께 이어지고 미해결에서 빠진다
    pm = _auth(client_token("r3"))
    sub = _submitted(client, pm, doc)
    assert client.post(f"{_base()}/{sub['id']}/confirm", json={}, headers=po).status_code == 200
    refs = client.get(f"/api/projects/{PID}/requirements/unresolved-refs", headers=po).json()
    assert not [r for r in refs if r["code"] == "SWFR.TST.301"]
    with tx() as cur:
        linked = fetch_one(cur, "select count(*) as n from trace_link tl join code_change c "
                                "on c.id = tl.from_id where c.tool_connection_id = %s "
                                "and tl.status = 'ACTIVE'", (cid,))
    assert linked["n"] == 1


@requires_db
def test_명세서의_상위_요구사항을_가리킨_참조는_없는_ID로_세지_않는다(client, client_token, clean):
    """명세서 절 제목의 상위 코드(SFR)는 요구사항이 아니다. 이슈가 그 코드를 적어도 잇지 않고,
    '목록에 없는 ID' 에서 빼서 상위 참조로 보인다. 진짜 없는 코드는 그대로 남는다."""
    from app.standard import trace_service

    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    clean["codes"] += ["SWFR.TST.401", "SWFR.TST.402"]
    spec = (
        "# 요구사항 명세서 v1.0\n\nSFR.TST.001 상위 기능 묶음\n\n"
        "| 요구사항 ID | 요구사항 명칭 | 요구사항 설명 | 중요도 |\n|---|---|---|---|\n"
        "| SWFR.TST.401 | 첫 항목 | 첫 항목 (상위 SFR.TST.001) | 필수 |\n"
        "| SWFR.TST.402 | 둘째 항목 | 상위를 적지 않았다 | 필수 |\n"
    )
    with tx() as cur:
        conn = _connect(cur)
        cid = str(conn["id"])
        clean["conns"].append(cid)
        _load(cur, conn, [("issue:41", _gh_issue(
            41, "커넥터 작업", [], body="**SFR.TST.001** 상위 기능 묶음 · 관련 SFR.TST.999"))])
        _promote(cur, cid)
        trace_service.build_project_links(cur, PID)
        doc = _document(cur, spec)
        clean["docs"].append(doc)

    sub = _submitted(client, pm, doc)
    assert sub["parents"] == [{"code": "SFR.TST.001", "title": "상위 기능 묶음",
                               "location": "3번째 줄", "children": ["SWFR.TST.401"]}]
    assert len(sub["items"]) == 2  # 상위 코드는 요구사항 항목이 아니다
    res = client.post(f"{_base()}/{sub['id']}/confirm", json={}, headers=po)
    assert res.status_code == 200, res.text

    refs = client.get(f"/api/projects/{PID}/requirements/unresolved-refs", headers=po).json()
    by_code = {r["code"]: r for r in refs}
    assert by_code["SFR.TST.001"]["parentTitle"] == "상위 기능 묶음"
    assert by_code["SFR.TST.999"]["parentTitle"] is None
    assert client.get(_base(), headers=po).json()["unresolvedCodeCount"] == 1
    with tx() as cur:
        assert "SFR.TST.001" not in _req_codes(cur)
        stored = fetch_one(cur, "select parents_json from requirement_baseline where id = %s",
                           (sub["id"],))["parents_json"]
    assert [p["code"] for p in stored] == ["SFR.TST.001"]


@requires_db
def test_상위_요구사항을_적기_전에_등록한_기준선은_명세서_글에서_다시_읽는다(
    client, client_token, clean
):
    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    clean["codes"] += ["SWFR.TST.411"]
    with tx() as cur:
        doc = _document(cur, (
            "SFR.TST.011 옛 상위\n\n| 요구사항 ID | 요구사항 명칭 | 요구사항 설명 | 중요도 |\n"
            "|---|---|---|---|\n| SWFR.TST.411 | 항목 | 항목 (상위 SFR.TST.011) | 필수 |\n"
        ))
        clean["docs"].append(doc)
    sub = _submitted(client, pm, doc)
    with tx() as cur:
        cur.execute("update requirement_baseline set parents_json = null where id = %s",
                    (sub["id"],))
    again = client.get(f"{_base()}/{sub['id']}", headers=po).json()
    assert [(p["code"], p["children"]) for p in again["parents"]] == [
        ("SFR.TST.011", ["SWFR.TST.411"])
    ]
    # 확정하면 확정본에 적어 둔다
    assert client.post(f"{_base()}/{sub['id']}/confirm", json={}, headers=po).status_code == 200
    with tx() as cur:
        stored = fetch_one(cur, "select parents_json from requirement_baseline where id = %s",
                           (sub["id"],))["parents_json"]
    assert stored and stored[0]["code"] == "SFR.TST.011"


# ---------------------------------------------------------------- 권한


@requires_db
def test_다른_사업의_기준선은_보거나_바꿀_수_없다(client, client_token, clean):
    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    with tx() as cur:
        org = str(fetch_one(
            cur, "insert into organization (name, type) values (%s, 'CLIENT') returning id",
            (f"다른 발주기관 {uuid.uuid4().hex[:6]}",))["id"])
        clean["orgs"].append(org)
        other = str(fetch_one(
            cur,
            """
            insert into project (client_org_id, name, start_date, end_date, description)
            values (%s, '다른 사업', '2026-08-01', '2026-11-30', '기준선 권한 시험') returning id
            """,
            (org,),
        )["id"])
        clean["projects"].append(other)
        doc = _document(cur, _spec_table([("SWFR.TST.401", "다른 사업 요구사항", "필수")]),
                        project_id=other)
        clean["docs"].append(doc)

    for who in (pm, po):
        assert client.get(_base(other), headers=who).status_code == 403
        assert client.post(_base(other), json={"documentId": doc},
                           headers=who).status_code == 403
        assert client.get(f"/api/projects/{other}/requirements/unresolved-refs",
                          headers=who).status_code == 403
    # 다른 사업의 문서로 우리 사업 기준선을 만들 수 없다
    assert client.post(_base(), json={"documentId": doc}, headers=pm).status_code == 404
    assert client.get(_base()).status_code == 401


# ---------------------------------------------------------------- 검색 색인 (점검 DATA-02)


def _indexed(cur, requirement_id: str) -> str:
    rows = fetch_all(
        cur, "select source_title, content from doc_chunk where source_type = 'REQUIREMENT' "
        "and source_id = %s order by chunk_index", (requirement_id,))
    return "\n".join(f"{r['source_title']}\n{r['content']}" for r in rows)


@requires_db
def test_요구사항_색인은_출처_이슈가_아니라_정의를_따른다(client, client_token, clean):
    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    with tx() as cur:
        legacy = _legacy_project(cur, clean)
    sub = _submitted(client, pm, legacy["doc"])
    done = client.post(f"{_base()}/{sub['id']}/confirm",
                       json={"applySpecCodes": ["SWFR.TST.202"]}, headers=po)
    assert done.status_code == 200, done.text

    with tx() as cur:
        rows = _req_codes(cur)
        a, b, new = rows["SWFR.TST.201"], rows["SWFR.TST.202"], rows["SWFR.TST.204"]
        # 명세서 내용을 적용한 기존 요구사항은 확정하면서 새 정의로 색인한다
        assert "명세서 쪽 제목" in _indexed(cur, str(b["id"]))
        assert "이슈 쪽 제목" not in _indexed(cur, str(b["id"]))
        assert "명세서에만 있는 요구사항" in _indexed(cur, str(new["id"]))

        # 확정 뒤 출처 이슈의 제목이 바뀌어도 요구사항 색인은 정의 그대로다
        _load(cur, legacy["conn"], [
            ("issue:1", _gh_issue(1, "[SWFR.TST.201] 이슈에서 바꾼 제목", ["유형: 요구사항"])),
            ("issue:2", _gh_issue(2, "[SWFR.TST.202] 또 바꾼 제목", ["유형: 요구사항"])),
        ])
        _promote(cur, legacy["cid"])
        assert "같은 제목" in _indexed(cur, str(a["id"]))
        assert "이슈에서 바꾼 제목" not in _indexed(cur, str(a["id"]))
        assert "명세서 쪽 제목" in _indexed(cur, str(b["id"]))
        assert "또 바꾼 제목" not in _indexed(cur, str(b["id"]))


@requires_db
def test_확정_때_색인이_실패해도_다음_수집이_채운다(client, client_token, clean, monkeypatch):
    from app.common import errors
    from app.rag import indexing

    pm, po = _auth(client_token("r3")), _auth(client_token("r2"))
    with tx() as cur:
        legacy = _legacy_project(cur, clean)
    sub = _submitted(client, pm, legacy["doc"])

    real = indexing.reindex

    def down(*_a, **_k):
        raise errors.ApiError(503, "AI_UNAVAILABLE", "임베딩 모델이 응답하지 않습니다.")
    monkeypatch.setattr(indexing, "reindex", down)
    done = client.post(f"{_base()}/{sub['id']}/confirm",
                       json={"applySpecCodes": ["SWFR.TST.202"]}, headers=po)
    assert done.status_code == 200, done.text  # 색인은 못 했어도 확정은 남는다
    monkeypatch.setattr(indexing, "reindex", real)

    with tx() as cur:
        b = _req_codes(cur)["SWFR.TST.202"]
        _promote(cur, legacy["cid"])
        assert "명세서 쪽 제목" in _indexed(cur, str(b["id"]))
