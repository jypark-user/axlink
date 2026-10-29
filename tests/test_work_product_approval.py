"""산출물 승인·반려 (SWFR.WEB.004 · ARC-016).

승인은 문서 확정과 다른 행위다. 발주기관 역할과 그 사업 접근을 둘 다 갖춰야 하고,
현행 버전 하나에만 붙는다. 용역사는 확정으로도 승인으로도 APPROVED 를 만들 수 없다.
"""

import uuid

import pytest

from app.common import errors
from app.db import fetch_one, tx
from app.standard import repository as standard_repo
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
OTHER_CLIENT_ORG = "a0000000-0000-4000-8000-000000000001"  # r2 가 속하지 않은 발주기관
TYPE = "TEST_REPORT"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _row(wp_id: str) -> dict:
    with tx() as cur:
        return fetch_one(
            cur,
            """
            select status, version, is_current, approved_by_user_id, approved_at, reject_reason
              from work_product where id = %s
            """,
            (wp_id,),
        )


@pytest.fixture
def submitted():
    """시드 사업의 시험결과서 자리를 제출 상태 버전 T1 로 두고, 끝나면 원래대로 돌린다."""
    with tx() as cur:
        before = fetch_one(
            cur,
            """
            select id, status, version, title, approved_by_user_id, approved_at, reject_reason
              from work_product where project_id = %s and type = %s and is_current
            """,
            (PID, TYPE),
        )
        cur.execute(
            """
            update work_product set status = 'SUBMITTED', version = 'T1', title = '승인 시험',
                   approved_by_user_id = null, approved_at = null, reject_reason = null
             where id = %s
            """,
            (before["id"],),
        )
    yield str(before["id"])
    with tx() as cur:
        cur.execute(
            """
            update work_product set status = %s, version = %s, title = %s,
                   approved_by_user_id = %s, approved_at = %s, reject_reason = %s
             where id = %s
            """,
            (
                before["status"], before["version"], before["title"],
                before["approved_by_user_id"], before["approved_at"], before["reject_reason"],
                before["id"],
            ),
        )


def _post(client, token, wp_id, action, body=None, pid=PID):
    return client.post(
        f"/api/projects/{pid}/work-products/{wp_id}/{action}", json=body or {}, headers=_auth(token)
    )


@requires_db
def test_용역사는_승인도_반려도_못_한다(client, client_token, submitted):
    token = client_token("r3")
    assert _post(client, token, submitted, "approve").status_code == 403
    assert _post(client, token, submitted, "reject", {"reason": "x"}).status_code == 403
    assert _row(submitted)["status"] == "SUBMITTED"


@requires_db
def test_발주기관이_승인하면_그_버전에_승인자와_시각이_붙는다(client, client_token, submitted):
    res = _post(client, client_token("r2"), submitted, "approve")
    assert res.status_code == 204, res.text
    row = _row(submitted)
    assert row["status"] == "APPROVED" and row["approved_at"] is not None
    with tx() as cur:
        r2 = fetch_one(cur, "select id from app_user where username = 'r2'")
    assert str(row["approved_by_user_id"]) == str(r2["id"])

    # 이미 승인된 것을 다시 승인하지 않는다
    again = _post(client, client_token("r2"), submitted, "approve")
    assert again.status_code == 409 and again.json()["code"] == "NOT_SUBMITTED"


@requires_db
def test_반려는_사유가_있어야_하고_승인을_지운다(client, client_token, submitted):
    token = client_token("r2")
    assert _post(client, token, submitted, "approve").status_code == 204
    assert _post(client, token, submitted, "reject", {"reason": "  "}).status_code == 400
    assert _post(client, token, submitted, "reject", {"reason": "표지 누락"}).status_code == 204
    row = _row(submitted)
    assert row["status"] == "REJECTED" and row["reject_reason"] == "표지 누락"
    assert row["approved_at"] is None and row["approved_by_user_id"] is None
    # 반려된 버전은 다시 제출(새 버전)되기 전에는 승인할 수 없다
    assert _post(client, token, submitted, "approve").status_code == 409


@pytest.fixture
def foreign_project():
    """r2 가 속하지 않은 발주기관의 사업. 역할이 발주기관이어도 이 사업은 못 본다."""
    with tx() as cur:
        pid = str(
            fetch_one(
                cur,
                """
                insert into project (client_org_id, name, start_date, end_date, description)
                values (%s, %s, '2026-08-01', '2026-11-30', '승인 권한 시험')
                returning id
                """,
                (OTHER_CLIENT_ORG, f"승인 권한 시험 {uuid.uuid4().hex[:6]}"),
            )["id"]
        )
        standard_repo.create_checklist(cur, pid)
        wp = fetch_one(
            cur,
            "select id from work_product where project_id = %s and type = %s and is_current",
            (pid, TYPE),
        )
        cur.execute(
            "update work_product set status = 'SUBMITTED', version = 'X1' where id = %s",
            (wp["id"],),
        )
    yield pid, str(wp["id"])
    with tx() as cur:
        cur.execute("delete from project where id = %s", (pid,))


@requires_db
def test_발주기관이라도_자기_사업이_아니면_못_한다(
    client, client_token, foreign_project, submitted
):
    pid, wp_id = foreign_project
    token = client_token("r2")
    assert _post(client, token, wp_id, "approve", pid=pid).status_code == 403
    # 남의 사업 산출물 id 를 내 사업 경로로 불러도 승인되지 않는다
    res = _post(client, token, wp_id, "approve", pid=PID)
    assert res.status_code == 404
    assert _row(wp_id)["status"] == "SUBMITTED"
    # 최고관리자는 모든 사업에 접근한다
    assert _post(client, client_token("r1"), wp_id, "approve", pid=pid).status_code == 204


@requires_db
def test_현행이_아닌_버전은_승인하지_않는다(client, client_token, submitted):
    with tx() as cur:
        cur.execute("update work_product set is_current = false where id = %s", (submitted,))
    try:
        res = _post(client, client_token("r2"), submitted, "approve")
        assert res.status_code == 409 and res.json()["code"] == "NOT_CURRENT_VERSION"
    finally:
        with tx() as cur:
            cur.execute("update work_product set is_current = true where id = %s", (submitted,))


@requires_db
def test_승인된_버전을_같은_버전_표기로_고쳐_쓰지_않는다(client, client_token, submitted):
    assert _post(client, client_token("r2"), submitted, "approve").status_code == 204
    rec = {
        "type": TYPE, "title": "덮어쓰기", "version": "T1", "status": "SUBMITTED",
        "authored_at": None, "file_uri": "x",
    }
    with tx() as cur, pytest.raises(errors.ApiError) as caught:
        standard_repo.place_document_work_product(cur, PID, None, None, rec)
    assert caught.value.code == "APPROVED_VERSION_LOCKED"
    assert _row(submitted)["status"] == "APPROVED"
