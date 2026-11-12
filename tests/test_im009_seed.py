"""IM-009 공통 시험 자료 투입이 문서의 기대값(7절)대로 S0 를 만드는지 본다.

이 시험은 자료 투입 스크립트의 정확성을 보는 것이고 제품 기능 판정이 아니다. 기대값과 다르면
① 투입 스크립트 오류 ② 제품 차이 ③ 명세 오류 가운데 어느 것인지 검증 기록(defects.jsonl)에
구분해 적는다. 기대값을 구현에 맞춰 바꾸지 않는다.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_db
from tests.fixtures.im009 import data as d
from tests.fixtures.im009.seed import Seeder


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def seeded(client):
    s = Seeder(client)
    try:
        s.s0()
        yield s
    finally:
        s.cleanup()


@requires_db
def test_s0_계정과_사업이_배정대로_보인다(client, seeded):
    s = seeded
    me_v1 = client.get("/api/auth/me", headers=_auth(s.tokens["TD-ACC-V1"])).json()
    assert set(me_v1["allowedProjectIds"]) == {s.ids["TD-PRJ-1"], s.ids["TD-PRJ-9"]}
    me_v0 = client.get("/api/auth/me", headers=_auth(s.tokens["TD-ACC-V0"])).json()
    assert me_v0["allowedProjectIds"] == []
    me_c1 = client.get("/api/auth/me", headers=_auth(s.tokens["TD-ACC-C1"])).json()
    assert {s.ids["TD-PRJ-1"], s.ids["TD-PRJ-3"], s.ids["TD-PRJ-9"]} <= set(
        me_c1["allowedProjectIds"]
    )
    assert s.ids["TD-PRJ-2"] not in me_c1["allowedProjectIds"]


@requires_db
def test_s0_이슈_커밋_PR_마일스톤_건수(client, seeded):
    s = seeded
    pid = s.ids["TD-PRJ-1"]
    h = _auth(s.tokens["TD-ACC-C1"])
    issues = client.get(f"/api/projects/{pid}/issues?size=100", headers=h).json()
    # 7.3: 전체 수집 이슈 16 가운데 리스크 2 는 risk 로 승격되고,
    # 출처 이슈 3 은 요구사항 상태만 바꾼다.
    # 일반 이슈 목록은 9 다. 결함 2(R9·R10)는 결함 트래커 매핑으로 갈라진다(DEC-02).
    # 전체 이슈(결함 포함) 목록이 11 이다.
    assert issues["totalElements"] == d.EXPECTED_S0["general_issues"], [
        i["key"] for i in issues["content"]
    ]
    keys = {i["key"] for i in issues["content"]}
    assert {"RM-201", "RM-204", "GH-4", "GH-5"} <= keys and "RM-209" not in keys
    every = client.get(f"/api/projects/{pid}/issues?size=100&kind=ALL", headers=h).json()
    assert every["totalElements"] == 11
    defects = client.get(f"/api/projects/{pid}/issues?size=100&kind=DEFECT", headers=h).json()
    assert defects["totalElements"] == d.EXPECTED_S0["defects"]
    assert "GH-1" not in keys and "RM-207" not in keys

    reqs = client.get(f"/api/projects/{pid}/requirements?size=50", headers=h).json()
    assert reqs["totalElements"] == d.EXPECTED_S0["requirements"]
    by_code = {r["code"]: r for r in reqs["content"]}
    assert by_code["UR.PORT.001"]["status"] == "VERIFIED"


@requires_db
def test_s0_진척과_계획선_T0(client, seeded):
    s = seeded
    pid = s.ids["TD-PRJ-1"]
    h = _auth(s.tokens["TD-ACC-C1"])
    prog = client.get(f"/api/projects/{pid}/progress?at={d.T0.isoformat()}", headers=h).json()
    # 7.1: 보고 진척률 0.3000, 계획선 0.6695 (중간값, 소수 넷째 자리). API 는 비율(0~1)로 준다.
    # 표시값 66.9% 는 원래 값 0.669461 의 반올림이다. 넷째 자리 중간값 0.6695 를 다시 반올림하면
    # 67.0 이 나와 틀린다(DEF-V001, 결함 아님으로 닫음). 여기서는 중간값과 비교한다.
    assert round(prog["representative"], 4) == d.EXPECTED_S0["progress_ratio"], prog
    assert round(prog["wbsPlanned"], 4) == d.EXPECTED_S0["plan_ratio_t0"], prog


@requires_db
def test_s0_제출본과_확인_요청(client, seeded):
    s = seeded
    pid = s.ids["TD-PRJ-1"]
    h = _auth(s.tokens["TD-ACC-C1"])
    wps = client.get(f"/api/projects/{pid}/work-products", headers=h).json()
    current = {i["type"]: i for i in wps["items"] if i.get("currentVersion") or i.get("status")}
    # 7.2: 제출본 2 — 요구사항정의서 v1 승인(업로드) · 사업수행계획서(저장소 수집, 제출)
    submitted = [i for i in wps["items"] if i.get("status") in ("SUBMITTED", "APPROVED")]
    assert len(submitted) == d.EXPECTED_S0["submissions"], [
        (i["type"], i.get("status")) for i in submitted
    ]
    assert current["REQUIREMENTS_SPEC"]["status"] == "APPROVED"
    assert current["PROJECT_PLAN"]["status"] == "SUBMITTED"
    # 미처리 0 (3.1 완료 확인은 확인완료까지 끝났다)
    reqs = client.get(f"/api/projects/{pid}/review-requests", headers=h).json()
    pending = [
        r
        for r in (reqs if isinstance(reqs, list) else reqs.get("content", []))
        if r["status"] in ("REQUESTED", "REPORTED")
    ]
    assert pending == []
