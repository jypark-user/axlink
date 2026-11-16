"""이슈 기반 추정 진척률 (DEC-17 2026-11-16, 진척률-산정체계 §4, SWFR.PIP.006).

WBS 가 없는 사업(L3)의 대표 진척률은 대상 일반 이슈의 진척도를 같은 가중치로 평균한 값이다.
진척도가 없는 이슈는 0 으로 세고 건수를 밝힌다. 대상 이슈가 없거나 모두 진척도가 없으면 산출
불가다. 일반 이슈 해결률은 별도 지표로 남는다. 스냅샷에는 산식을 함께 적어 옛 L3(해결률) 행과
섞지 않는다.
"""

from datetime import UTC, date, datetime

import pytest

from app.ai.embedding import embedding_port
from app.common import crypto
from app.dashboard import service as progress
from app.dashboard import snapshot
from app.dashboard.repository import issue_progress
from app.db import tx
from app.integration import repository as integ_repo
from app.standard import service as standard
from app.standard.mapping_rules import MappingRules
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------- 산식 경계


def test_IM009_TD_ISS_N1_N7_은_54_3퍼센트다():
    """100·100·50·30·0·결측·100 → 380 / 7 = 54.2857. 결측 1건은 0 으로 센다."""
    m = progress.issue_estimate_measure(380.0, 7, 6, defect_mapped=True)
    assert m.value == 0.5429
    assert round(m.value * 100, 1) == 54.3
    assert (m.denominator, m.missing) == (7, 1)
    assert m.label == "이슈 기반 추정 진척률"
    assert "같은 가중치" in m.note and "0으로 셉니다(결측 1건)" in m.note
    assert "리스크·결함" in m.note


def test_결측이_없어도_결측_처리_규칙을_밝힌다():
    m = progress.issue_estimate_measure(150.0, 2, 2, defect_mapped=True)
    assert m.value == 0.75 and m.missing == 0
    assert "결측 0건" in m.note


def test_대상_이슈가_없으면_산출_불가():
    m = progress.issue_estimate_measure(0.0, 0, 0, defect_mapped=True)
    assert m.value is None and m.missing is None
    assert m.note.startswith("산출 불가")


def test_진척도가_모두_없으면_산출_불가이고_0퍼센트가_아니다():
    m = progress.issue_estimate_measure(0.0, 4, 0, defect_mapped=False)
    assert m.value is None and m.missing == 4
    assert m.note == "산출 불가: 대상 일반 이슈 4건 모두 진척도가 없습니다"


def test_진척도가_모두_0이면_0퍼센트다():
    """결측과 0 은 다르다. 진척도를 0 으로 적은 이슈뿐이면 값은 0% 다."""
    m = progress.issue_estimate_measure(0.0, 3, 3, defect_mapped=True)
    assert m.value == 0.0


def _measure(value, denominator, missing=None):
    return progress.ProgressMeasure(
        value=value, numerator=None, denominator=denominator, label="x", unit="x",
        kind="x", note=None, missing=missing,
    )


def test_L3_는_이슈_추정값을_쓰고_해결률을_쓰지_않는다():
    estimate = _measure(0.5429, 7, 1)
    product = _measure(0.9, 10)
    level, basis, rep = progress._representative(None, estimate, product)
    assert (level, basis, rep) == ("L3", "ISSUE_PROGRESS", 0.5429)


def test_대상_이슈가_있으면_진척도가_없어도_L3_에_머문다():
    """산출물로 내려가지 않는다. 값만 산출 불가다(WBS 가 있으면 아래로 내려가지 않는 것과 같다)."""
    level, basis, rep = progress._representative(None, _measure(None, 4, 4), _measure(0.5, 2))
    assert (level, basis, rep) == ("L3", "ISSUE_PROGRESS", None)


def test_대상_이슈가_없으면_L4_로_내려간다():
    product = progress.ProgressMeasure(
        value=0.5, numerator=1, denominator=2, label="x", unit="x", kind="x", note=None
    )
    level, basis, _ = progress._representative(None, _measure(None, 0), product)
    assert (level, basis) == ("L4", "WORK_PRODUCT")


def test_산출_근거_문장은_가중치와_결측과_해결률_구분을_밝힌다():
    issue = _measure(0.2857, 7)
    issue.numerator = 2
    note = progress._basis_note("L3", None, issue, _measure(None, 0), _measure(0.5429, 7, 1))
    assert note.startswith("추정: WBS 가 없어 이슈 기반 추정 진척률로 산정했습니다")
    assert "같은 가중치" in note and "1건은 0으로 셌습니다" in note
    assert "L1" in note and "해결률은 별도 지표" in note
    off = progress._basis_note("L3", None, issue, _measure(None, 0), _measure(None, 7, 7))
    assert off.startswith("산출 불가") and "해결 2 / 전체 7건" in off


# ---------------------------------------------------------------- 스냅샷의 산식 칸


def test_옛_L3_행은_해결률로_읽고_새_행과_구분한다():
    assert snapshot.effective_basis("L3", None) == "ISSUE"
    assert snapshot.basis_label("L3", None) == "일반 이슈 해결률(옛 L3 산식)"
    assert snapshot.basis_label("L3", "ISSUE_PROGRESS") == "이슈 기반 추정 진척률"
    # 다른 수준의 옛 행은 산식을 짐작하지 않는다
    assert snapshot.effective_basis("L1", None) is None


# ---------------------------------------------------------------- 원천 진척도 읽기


def _payload(n: int, tracker: str, done: int | None, version: str | None) -> dict:
    body = {
        "id": 970 + n, "subject": f"DEC-17 시험 {n}", "description": "",
        "tracker": {"name": tracker}, "status": {"name": "신규", "is_closed": False},
        "created_on": "2026-09-01T00:00:00Z", "updated_on": "2026-09-02T00:00:00Z",
    }
    if done is not None:  # 결측은 키가 없다
        body["done_ratio"] = done
    if version:
        body["fixed_version"] = {"id": 1, "name": version}
    return body


# TD-ISS-N1~N7 과 같은 진척도. 마지막 결함은 대상이 아니다(DEC-02)
_ISSUES = [
    ("일감", 100, "V-A"), ("일감", 100, "V-A"), ("일감", 50, "V-A"),
    ("일감", 30, "V-B"), ("일감", 0, "V-B"), ("일감", None, "V-B"), ("일감", 100, None),
    ("결함", 80, "V-B"),
]


@pytest.fixture
def l3_connection():
    with tx() as cur:
        before = issue_progress(cur, PID)
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        rules = MappingRules.from_json({"defectTracker": "결함"})
        conn = integ_repo.insert(
            cur, PID, org, "REDMINE", "DEC-17 시험", "http://localhost:3000",
            "dec17", crypto.encrypt("k"), "k***", rules.to_json(),
        )
        cid = str(conn["id"])
        job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
        for n, (tracker, done, version) in enumerate(_ISSUES):
            integ_repo.upsert_raw_artifact(
                cur, cid, str(970 + n), "issue", _payload(n, tracker, done, version), job
            )
        standard.promote_connection(cur, conn, embedding_port())
    yield before
    with tx() as cur:
        cur.execute("delete from issue where tool_connection_id = %s", (cid,))
        cur.execute("delete from raw_artifact where tool_connection_id = %s", (cid,))
        cur.execute("delete from sync_job where tool_connection_id = %s", (cid,))
        cur.execute("delete from tool_connection where id = %s", (cid,))


@requires_db
def test_원천_진척도를_읽고_결함과_결측을_가른다(l3_connection):
    """늘어난 만큼만 본다: 대상 7(결함 제외), 진척도 있음 6, 합 380."""
    base_sum, base_total, base_reported = l3_connection
    with tx() as cur:
        done_sum, total, reported = issue_progress(cur, PID)
    assert total - base_total == 7
    assert reported - base_reported == 6
    assert done_sum - base_sum == 380.0


@requires_db
def test_스냅샷이_산식과_이슈_추정값을_적는다(client, client_token, l3_connection):
    """시드 사업에는 WBS 가 있을 수도 있다. 산식 칸은 어느 수준이든 채워진다."""
    token = client_token("r2")
    res = client.post(
        f"/api/projects/{PID}/snapshots", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    expected = {"L1": "WBS", "L2": "WBS_ESTIMATED", "L3": "ISSUE_PROGRESS", "L4": "WORK_PRODUCT"}
    assert body["representativeBasis"] == expected.get(body["level"], "NONE")
    with tx() as cur:
        done_sum, total, reported = issue_progress(cur, PID)
    assert body["issueEstimateMissingCount"] == total - reported
    assert body["issueEstimatePct"] == round(done_sum / total, 2)
    # 화면·AI 가 같은 산정 함수를 쓴다
    with tx() as cur:
        now = progress.compute(cur, PID, date.fromisoformat(body["snapshotDate"]))
    assert now.issueEstimate is not None and now.issueEstimate.missing == total - reported
    assert now.basis == body["representativeBasis"]
