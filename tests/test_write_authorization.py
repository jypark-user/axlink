"""중요 쓰기 API 의 역할·사업 경계 (점검 6절).

다른 파일이 이미 보는 것(산출물 승인·반려, 기준선 확정, 참여사·초대, 수집 일정, 연결 소유 이전,
요구사항 상태 지정, 스냅샷)은 여기서 다시 보지 않는다. 여기는 그 사이에 비어 있던 경로다.
거절되면 아무것도 바뀌지 않았는지도 본다. 시험 계정: r1 관리자, r2 발주기관, r3 용역사.
"""

import uuid

import pytest

from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
OTHER_CLIENT_ORG = "a0000000-0000-4000-8000-000000000001"  # r2·r3 이 속하지 않은 발주기관


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _user(cur, username: str) -> str:
    return str(fetch_one(cur, "select id from app_user where username = %s", (username,))["id"])


@pytest.fixture
def foreign():
    """r2·r3 이 배정되지 않은 사업 하나와 그 사업의 문서·연결·기본 대시보드(만든 사람은 r2)."""
    with tx() as cur:
        pid = str(fetch_one(
            cur,
            "insert into project (client_org_id, name, start_date, end_date, description) "
            "values (%s, %s, '2026-08-01', '2026-11-30', '권한 시험') returning id",
            (OTHER_CLIENT_ORG, f"권한 시험 {uuid.uuid4().hex[:6]}"),
        )["id"])
        doc = str(fetch_one(
            cur,
            """
            insert into document_upload (project_id, uploaded_by_user_id, original_filename,
              stored_path, content_type, file_ext, size_bytes, file_hash)
            values (%s, %s, '남의 문서.txt', 'x/남의 문서.txt', 'text/plain', 'TXT', 1, %s)
            returning id
            """,
            (pid, _user(cur, "r1"), uuid.uuid4().hex * 2),
        )["id"])
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn = str(fetch_one(
            cur,
            """
            insert into tool_connection (project_id, contractor_org_id, tool, name, base_url,
              target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, 'GITHUB', '남의 연결', 'https://api.github.invalid', 'o/r', 'x', 'x',
                    'ACTIVE') returning id
            """,
            (pid, org["id"]),
        )["id"])
        # 예전에 r2 가 이 사업에 있을 때 만든 사업 기본 대시보드. 지금 r2 는 이 사업에 없다
        board = str(fetch_one(
            cur,
            "insert into dashboard (project_id, owner_user_id, name, is_default) "
            "values (%s, %s, '기본', true) returning id",
            (pid, _user(cur, "r2")),
        )["id"])
    yield {"pid": pid, "doc": doc, "conn": conn, "board": board}
    with tx() as cur:
        cur.execute("delete from sync_job where tool_connection_id = %s", (conn,))
        cur.execute("delete from project where id = %s", (pid,))


# ---------------------------------------------------------------- 역할


@requires_db
def test_용역사는_사업_정보를_바꾸거나_지우지_못한다(client, client_token):
    r3 = _auth(client_token("r3"))
    with tx() as cur:
        before = fetch_one(cur, "select name, end_date from project where id = %s", (PID,))
    res = client.patch(f"/api/projects/{PID}", json={"name": "바꿈"}, headers=r3)
    assert res.status_code == 403
    # 삭제는 비밀번호 본문이 있어야 검증을 지나 권한 검사에 닿는다
    res = client.request("DELETE", f"/api/projects/{PID}", json={"password": "x"}, headers=r3)
    assert res.status_code == 403
    with tx() as cur:
        after = fetch_one(cur, "select name, end_date from project where id = %s", (PID,))
    assert after == before


# ---------------------------------------------------------------- 사업 경계


@requires_db
@pytest.mark.parametrize("user", ["r2", "r3"])
def test_다른_사업의_문서는_고치거나_지우지_못한다(client, client_token, foreign, user):
    who = _auth(client_token(user))
    doc = foreign["doc"]
    assert client.patch(f"/api/documents/{doc}", json={"productType": ""},
                        headers=who).status_code in (403, 404)
    assert client.delete(f"/api/documents/{doc}", headers=who).status_code in (403, 404)
    with tx() as cur:
        assert fetch_one(cur, "select id from document_upload where id = %s", (doc,)) is not None


@requires_db
@pytest.mark.parametrize("user", ["r2", "r3"])
def test_다른_사업의_연결은_수집을_돌리거나_지우지_못한다(client, client_token, foreign, user):
    who = _auth(client_token(user))
    conn = foreign["conn"]
    assert client.post(f"/api/connections/{conn}/sync", headers=who).status_code in (403, 404)
    assert client.delete(f"/api/connections/{conn}", headers=who).status_code in (403, 404)
    with tx() as cur:
        assert fetch_one(cur, "select count(*) as n from sync_job where tool_connection_id = %s",
                         (conn,))["n"] == 0
        assert fetch_one(cur, "select id from tool_connection where id = %s", (conn,)) is not None


@requires_db
def test_사업에서_빠진_사람은_예전에_만든_대시보드도_못_고친다(client, client_token, foreign):
    r2 = _auth(client_token("r2"))
    board = foreign["board"]
    assert client.get(f"/api/dashboards/{board}", headers=r2).status_code == 403
    empty = {"layout": {"lg": [], "md": [], "sm": []}}
    res = client.put(f"/api/dashboards/{board}/layout", json=empty, headers=r2)
    assert res.status_code == 403
    # 관리자는 모든 사업을 본다
    admin = _auth(client_token("r1"))
    assert client.get(f"/api/dashboards/{board}", headers=admin).status_code == 200


@requires_db
def test_남의_대화는_지우거나_이어_쓰지_못한다(client, client_token):
    mine = client.post("/api/conversations", json={"title": "r2 대화", "projectScope": [PID]},
                       headers=_auth(client_token("r2")))
    assert mine.status_code in (200, 201), mine.text
    cid = mine.json()["id"]
    try:
        r3 = _auth(client_token("r3"))
        assert client.delete(f"/api/conversations/{cid}", headers=r3).status_code in (403, 404)
        assert client.patch(f"/api/conversations/{cid}", json={"title": "가로챔"},
                            headers=r3).status_code in (403, 404)
        with tx() as cur:
            row = fetch_one(cur, "select title, status from conversation where id = %s", (cid,))
        assert row == {"title": "r2 대화", "status": "ACTIVE"}
    finally:
        with tx() as cur:
            cur.execute("delete from conversation where id = %s", (cid,))
