"""업무 판단 권한표 (DEC-05 2026-11-16, ARC-032, SER.SEC.003).

플랫폼 관리자(SUPER_ADMIN)는 모든 사업을 보지만, 발주기관의 판단과 용역사의 행위는 대신하지
않는다. 역할 검사는 대상 조회보다 먼저라 없는 id 로도 거절이 확인된다. 예전에 관리자가 남긴
처리 기록은 지우거나 고치지 않고 「(관리자)」로 구분해 보인다.
"""

import uuid

import pytest

from app.auth import duties
from app.auth.models import AuthPrincipal
from app.common import errors
from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
NOWHERE = "00000000-0000-4000-8000-00000000dead"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _principal(role: str) -> AuthPrincipal:
    return AuthPrincipal(user_id=NOWHERE, org_id=NOWHERE, org_type="PLATFORM", role=role)


def test_관리자는_어떤_업무_판단에도_들지_않는다():
    for duty, (roles, _) in duties.DUTIES.items():
        assert duties.SUPER_ADMIN not in roles, duty
        assert len(roles) == 1, duty  # 발주기관 또는 용역사 한쪽만


@pytest.mark.parametrize("duty", sorted(duties.DUTIES))
def test_관리자_거절에는_대신하지_않는다는_말이_붙는다(duty):
    with pytest.raises(errors.ApiError) as raised:
        duties.require(_principal("SUPER_ADMIN"), duty)
    assert raised.value.status == 403
    assert raised.value.message.endswith(duties.ADMIN_NOTE.strip())


def test_허용_역할은_통과하고_반대편은_거절된다():
    duties.require(_principal("CLIENT"), "PRODUCT_APPROVE")
    duties.require(_principal("CONTRACTOR"), "BASELINE_AUTHOR")
    with pytest.raises(errors.ApiError) as raised:
        duties.require(_principal("CONTRACTOR"), "PRODUCT_APPROVE")
    assert duties.ADMIN_NOTE.strip() not in raised.value.message


# (메서드, 경로, 본문). 관리자는 모든 사업에 접근하므로 거절은 사업 접근이 아니라 권한표에서 난다
_ADMIN_DENIED = [
    ("post", f"/api/projects/{PID}/requirement-baseline", {"documentId": NOWHERE}),  # UC-020
    ("post", f"/api/projects/{PID}/requirement-baseline/{NOWHERE}/submit", None),  # UC-020
    ("post", f"/api/projects/{PID}/requirement-baseline/{NOWHERE}/confirm", {}),  # UC-021
    ("post", f"/api/projects/{PID}/requirement-baseline/{NOWHERE}/return",
     {"reason": "시험"}),  # UC-021
    ("put", f"/api/projects/{PID}/requirements/{NOWHERE}/status",
     {"status": "VERIFIED", "reason": "시험"}),  # UC-023
    ("post", f"/api/projects/{PID}/work-products/{NOWHERE}/approve", None),  # UC-031
    ("post", f"/api/projects/{PID}/work-products/{NOWHERE}/reject", {"reason": "시험"}),
    ("post", f"/api/projects/{PID}/review-requests",
     {"purpose": "GENERAL", "targetType": "METRIC", "targetKey": "REPRESENTATIVE",
      "title": "시험", "body": "시험"}),  # UC-050
]


@requires_db
@pytest.mark.parametrize(("method", "path", "body"), _ADMIN_DENIED)
def test_관리자는_판단_API_에서_거절된다(client, client_token, method, path, body):
    res = getattr(client, method)(
        path, headers=_auth(client_token("r1")), **({"json": body} if body is not None else {})
    )
    assert res.status_code == 403, res.text
    assert "플랫폼 관리자는" in res.json()["message"]


@pytest.fixture
def admin_decided_requirement():
    """DEC-05 전에 관리자가 상태를 지정해 둔 요구사항(5173·5174 에 실제로 1건씩 있다)."""
    with tx() as cur:
        admin = fetch_one(cur, "select id from app_user where username = 'r1'")
        rid = str(uuid.uuid4())
        cur.execute(
            """
            insert into requirement (id, project_id, title, body, priority, status,
                                     evidence_status, source_kind, decided_status,
                                     decided_reason, decided_by_user_id, decided_at)
            values (%s, %s, '관리자 지정 시험', '', 'MUST', 'VERIFIED', 'DEFINED', 'MANUAL',
                    'VERIFIED', '운영 지원', %s, now())
            """,
            (rid, PID, admin["id"]),
        )
    yield rid
    with tx() as cur:
        cur.execute("delete from requirement where id = %s", (rid,))


@requires_db
def test_예전_관리자_지정은_그대로_남고_관리자로_보인다(
    client, client_token, admin_decided_requirement
):
    rid = admin_decided_requirement
    res = client.get(f"/api/projects/{PID}/requirements/{rid}", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    decision = res.json()["decision"]
    assert decision["status"] == "VERIFIED" and decision["reason"] == "운영 지원"
    assert decision["decidedByRole"] == "SUPER_ADMIN"
    with tx() as cur:
        row = fetch_one(cur, "select decided_status from requirement where id = %s", (rid,))
    assert row["decided_status"] == "VERIFIED"  # 권한이 바뀌어도 기록은 고치지 않는다
