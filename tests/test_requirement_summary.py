"""요구사항 화면 요약과 목록 조건 (SWFR.WEB.002).

요약은 목록 쪽과 상관없이 사업 전체를 서버에서 센다. 원천 이슈 상태는 원천 기록(raw_artifact)
에서 세고 내부 상태에서 짐작하지 않는다. 카드가 거는 조건마다 목록 건수가 요약과 맞아야 한다.
"""

import hashlib
import uuid

import pytest
from psycopg.types.json import Jsonb

from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
STATUSES = ("DEFINED", "DESIGNED", "IMPLEMENTED", "VERIFIED", "ACCEPTED", "REJECTED")
MANY = 130


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _summary(client, token: str, pid: str = PID) -> dict:
    res = client.get(f"/api/projects/{pid}/requirements/summary", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


def _count(client, token: str, **params) -> int:
    qs = "&".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in params.items())
    res = client.get(f"/api/projects/{PID}/traceability?size=1&{qs}", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["totalElements"]


def _connection(cur, org_id, target: str) -> str:
    conn_id = str(uuid.uuid4())
    cur.execute(
        """
        insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                     target_resource, auth_encrypted, auth_hint, status)
        values (%s, %s, %s, 'GITHUB', 'TST', 'https://api.github.invalid/', %s, 'x', 'x',
                'ACTIVE')
        """,
        (conn_id, PID, org_id, target),
    )
    return conn_id


def _requirement(cur, title: str, status: str, conn: str | None, ext: str | None) -> None:
    cur.execute(
        """
        insert into requirement (project_id, code, title, status, tool_connection_id,
                                 external_id, source_kind)
        values (%s, null, %s, %s, %s, %s, %s)
        """,
        (PID, title, status, conn, ext, "TOOL" if conn else "MANUAL"),
    )


def _raw(cur, conn: str, ext: str, state: str) -> None:
    payload = {"number": int(ext), "state": state, "title": f"원천 {ext}"}
    cur.execute(
        """
        insert into raw_artifact (tool_connection_id, external_id, object_kind, payload_jsonb,
                                  content_hash)
        values (%s, %s, 'issue', %s, %s)
        """,
        (conn, ext, Jsonb(payload), hashlib.sha256(repr(payload).encode()).hexdigest()),
    )


@pytest.fixture
def seeded():
    """원천 둘과 수기 요구사항. 원천 상태는 내부 상태와 일부러 엇갈리게 둔다.

    - 원천 A: 120건. 상태 여섯을 돌리고, 원천 state 는 짝수 open·홀수 closed. 그중 5건은 기록 없음
    - 원천 B: 4건. 모두 closed
    - 연결 없음(수기): 6건
    """
    exp = {"by_status": dict.fromkeys(STATUSES, 0), "a": [0, 0, 0], "b": [0, 0, 0], "none": 0}
    with tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn_a = _connection(cur, org["id"], "summary/a")
        conn_b = _connection(cur, org["id"], "summary/b")
        n = 0
        for i in range(120):
            status = STATUSES[i % 6]
            ext = str(50000 + i)
            _requirement(cur, f"요약 시험 A{i}", status, conn_a, ext)
            exp["by_status"][status] += 1
            if i < 5:
                exp["a"][2] += 1  # 원천 기록 없음
            else:
                state = "open" if i % 2 == 0 else "closed"
                _raw(cur, conn_a, ext, state)
                exp["a"][0 if state == "open" else 1] += 1
            n += 1
        for i in range(4):
            ext = str(60000 + i)
            _requirement(cur, f"요약 시험 B{i}", "DEFINED", conn_b, ext)
            _raw(cur, conn_b, ext, "closed")
            exp["by_status"]["DEFINED"] += 1
            exp["b"][1] += 1
            n += 1
        for i in range(6):
            _requirement(cur, f"요약 시험 수기{i}", "IMPLEMENTED", None, None)
            exp["by_status"]["IMPLEMENTED"] += 1
            exp["none"] += 1
            n += 1
    exp["total"] = n
    exp["conn_a"], exp["conn_b"] = conn_a, conn_b
    yield exp
    with tx() as cur:
        cur.execute("delete from requirement where title like '요약 시험 %%' and project_id = %s",
                    (PID,))
        cur.execute("delete from tool_connection where id in (%s, %s)", (conn_a, conn_b))


def _baseline(summary: dict) -> dict:
    return {
        "total": summary["total"],
        "verified": summary["verified"],
        "from_closed": summary["implementedFromSourceClosed"],
        "by_status": {s["status"]: s["count"] for s in summary["byStatus"]},
        "none": next((s["total"] for s in summary["sources"] if s["connectionId"] is None), 0),
    }


@pytest.fixture
def baseline(client, client_token):
    """시험 행을 넣기 전 사업 상태. 시드에 있던 요구사항을 기대값에 더한다."""
    return _baseline(_summary(client, client_token("r2")))


@requires_db
def test_요약은_100건을_넘어도_사업_전체를_센다(client, client_token, baseline, seeded):
    got = _summary(client, client_token("r2"))
    by_status = {s: baseline["by_status"].get(s, 0) + seeded["by_status"][s] for s in STATUSES}
    verified = by_status["VERIFIED"] + by_status["ACCEPTED"]
    total = baseline["total"] + seeded["total"]

    assert total > 100
    assert got["total"] == total
    assert {s["status"]: s["count"] for s in got["byStatus"]} == by_status
    assert [s["status"] for s in got["byStatus"]] == list(STATUSES)
    assert got["verified"] == verified == baseline["verified"] + 40
    assert got["notVerified"] == total - verified
    assert got["verifiedRate"] == pytest.approx(verified / total)
    # GitHub 연결에서 온 IMPLEMENTED 20건만 원천 이슈 닫힘으로 센다. 수기 IMPLEMENTED 6건은 아니다
    assert got["implementedFromSourceClosed"] == baseline["from_closed"] + 20


@requires_db
def test_원천_상태는_원천_기록에서_원천마다_따로_센다(client, client_token, baseline, seeded):
    got = {s["connectionId"]: s for s in _summary(client, client_token("r2"))["sources"]}
    a, b, none = got[seeded["conn_a"]], got[seeded["conn_b"]], got[None]

    assert (a["open"], a["closed"], a["unknown"]) == tuple(seeded["a"])
    assert a["total"] == 120 and a["label"] == "GitHub summary/a"
    assert (b["open"], b["closed"], b["unknown"]) == tuple(seeded["b"])
    assert b["total"] == 4 and b["label"] == "GitHub summary/b"
    assert none["tool"] == "NONE"
    assert none["total"] == baseline["none"] + seeded["none"]
    assert none["open"] == none["closed"] == none["unknown"] == 0

    # 내부 상태에서 역산하지 않았다. 인수까지 됐는데 원천이 열린 것, 구현인데 열린 것,
    # 설계 단계인데 닫힌 것이 그대로 보인다
    token = client_token("r2")
    rows = client.get(
        f"/api/projects/{PID}/traceability?size=200&connectionId={seeded['conn_a']}",
        headers=_auth(token),
    ).json()["content"]
    pairs = {(r["requirementStatus"], r["sourceState"]) for r in rows}
    assert {("ACCEPTED", "OPEN"), ("IMPLEMENTED", "OPEN"), ("DESIGNED", "CLOSED")} <= pairs
    assert ("DEFINED", "UNKNOWN") in pairs


@requires_db
def test_카드마다_목록_건수가_요약과_맞는다(client, client_token, seeded):
    token = client_token("r2")
    got = _summary(client, token)

    assert _count(client, token) == got["total"]
    assert _count(client, token, verified=True) == got["verified"]
    assert _count(client, token, verified=False) == got["notVerified"]
    for s in got["byStatus"]:
        assert _count(client, token, status=s["status"]) == s["count"], s["status"]
    for s in got["sources"]:
        if s["connectionId"] is None:
            assert _count(client, token, sourceState="NONE") == s["total"]
            continue
        for state, key in (("OPEN", "open"), ("CLOSED", "closed"), ("UNKNOWN", "unknown")):
            n = _count(client, token, sourceState=state, connectionId=s["connectionId"])
            assert n == s[key], (s["label"], state)

    # 찾기는 서버에서 한다. 사업 전체 건수는 그대로다
    assert _count(client, token, q="요약 시험 B") == 4
    assert _count(client, token, q="요약 시험 B", status="DEFINED") == 4
    assert _summary(client, token)["total"] == got["total"]


@requires_db
def test_조건을_건_목록도_쪽을_넘기면_모든_행에_닿는다(client, client_token, seeded):
    token = client_token("r2")
    seen: list[str] = []
    page = 0
    while True:
        body = client.get(
            f"/api/projects/{PID}/traceability?status=DEFINED&page={page}&size=7",
            headers=_auth(token),
        ).json()
        seen += [r["requirementId"] for r in body["content"]]
        if not body["hasNext"]:
            break
        page += 1
    assert len(seen) == len(set(seen)) == body["totalElements"]


@requires_db
def test_잘못된_조건은_거절한다(client, client_token):
    token = client_token("r2")
    for qs in ("status=DONE", "sourceState=MAYBE", "verified=perhaps"):
        res = client.get(f"/api/projects/{PID}/traceability?{qs}", headers=_auth(token))
        # 이 앱은 요청 검증 실패를 400 VALIDATION_FAILED 로 돌려준다
        assert res.status_code == 400, qs


@pytest.fixture
def empty_project():
    """요구사항이 하나도 없는 사업. 시드 사업과 같은 발주기관이라 r2 는 보고 r3 는 못 본다."""
    with tx() as cur:
        client_org = fetch_one(cur, "select client_org_id from project where id = %s", (PID,))
        pid = str(
            fetch_one(
                cur,
                """
                insert into project (client_org_id, name, start_date, end_date, description)
                values (%s, %s, '2026-08-01', '2026-11-30', '요약 시험용 빈 사업')
                returning id
                """,
                (client_org["client_org_id"], f"요약 시험 빈 사업 {uuid.uuid4().hex[:6]}"),
            )["id"]
        )
    yield pid
    with tx() as cur:
        cur.execute("delete from project where id = %s", (pid,))


@requires_db
def test_요구사항이_없으면_비율은_산출_불가다(client, client_token, empty_project):
    got = _summary(client, client_token("r2"), empty_project)
    assert got["total"] == got["verified"] == got["notVerified"] == 0
    assert got["implementedFromSourceClosed"] == 0
    assert got["verifiedRate"] is None
    assert all(s["count"] == 0 for s in got["byStatus"])
    assert got["sources"] == []
    token = client_token("r2")
    res = client.get(f"/api/projects/{empty_project}/traceability", headers=_auth(token))
    assert res.json()["totalElements"] == 0


@requires_db
def test_요약도_목록과_같은_권한을_쓴다(client, client_token, empty_project):
    token = client_token("r3")
    for path in ("requirements/summary", "traceability"):
        res = client.get(f"/api/projects/{empty_project}/{path}", headers=_auth(token))
        assert res.status_code == 403, path
    assert client.get(f"/api/projects/{PID}/requirements/summary").status_code == 401
    # 상세 경로가 summary 를 id 로 잡지 않는다
    assert client.get(
        f"/api/projects/{PID}/requirements/summary", headers=_auth(client_token("r2"))
    ).status_code == 200
