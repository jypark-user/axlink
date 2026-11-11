# ruff: noqa: E501
"""C 그룹: 요구사항 (UC-020 ~ UC-023) 예제 시나리오.

한 S0 위에서 순서대로 돈다. UC-020-S01 이 명세서를 등록·제출하고, UC-021-S03 이 돌려보내고,
UC-020-S08 이 다시 제출하고, UC-021-S02 가 확정한다. 그 뒤 UC-023 이 지정·되돌림을 본다.
DEC 에 걸린 값(이행률 분모, 승인률)은 단언하지 않고 결정 뒤로 남긴다.
"""

from __future__ import annotations

import re

import pytest

from app.db import fetch_all, fetch_one, tx
from app.standard import trace_service
from tests.fixtures.im009 import data as d
from tests.fixtures.im009.replay import Faults, ReplaySource, install
from tests.scenarios.conftest import auth

pytestmark = pytest.mark.db


@pytest.fixture
def replay(monkeypatch, s0) -> ReplaySource:
    # UC-021-S07 이 원천을 S1 로 바꾼 뒤에는 그 상태를 이어 쓴다. S0 로 되돌리면 같은 blob
    # 으로 예전 버전에 다시 insert 하는 제품 결함(DEF-V033)을 밟아 뒤 시험이 연쇄로 깨진다
    return install(monkeypatch, ReplaySource(state=s0.ids.get("SOURCE-STATE", "S0"), files=s0.files))


def _base(s0, prj: str = "TD-PRJ-1") -> str:
    return f"/api/projects/{s0.ids[prj]}/requirement-baseline"


def _reqs(target, s0, prj: str = "TD-PRJ-1", acc: str = "TD-ACC-C1") -> dict[str, dict]:
    res = target.get(f"/api/projects/{s0.ids[prj]}/requirements?size=100", headers=auth(s0.tokens[acc]))
    assert res.status_code == 200, res.text
    return {r["code"]: r for r in res.json()["content"]}


def _detail(target, s0, rid: str, acc: str = "TD-ACC-C1") -> dict:
    res = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/requirements/{rid}", headers=auth(s0.tokens[acc]))
    assert res.status_code == 200, res.text
    return res.json()


def _activity_kinds(target, s0, baseline_id: str, acc: str = "TD-ACC-V1") -> list[str]:
    """그 기준선을 대상으로 한 활동 기록 종류(오래된 것부터). AC-020-9."""
    res = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/activity?size=100", headers=auth(s0.tokens[acc]))
    assert res.status_code == 200, res.text
    rows = [a for a in res.json()["content"] if a["targetType"] == "REQUIREMENT_BASELINE" and a["targetKey"] == baseline_id]
    return [a["kind"] for a in sorted(rows, key=lambda a: a["occurredAt"])]


def _links(cur, pid: str) -> set[tuple]:
    rows = fetch_all(
        cur,
        "select from_type, from_id::text, to_type, to_id::text, link_kind, status "
        "from trace_link where project_id = %s and origin = 'AUTO'",
        (pid,),
    )
    return {tuple(r.values()) for r in rows}


# ------------------------------------------------------------------ UC-020


def test_UC_020_S05_발주기관_시도(target, s0):
    """C1 이 등록 → 거절 (AC-020-3). 항목 수정·제출 거절은 S01 뒤 S11 과 함께 본다."""
    res = target.post(_base(s0), json={"documentId": s0.ids["TD-DOC-1"]}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 403, res.text


def test_UC_020_S10_다른_사업_문서(target, s0):
    """TD-PRJ-2 의 문서 ID 로 TD-PRJ-1 에 등록 → 거절 (COMMON-S01)."""
    path = s0.files["TD-DOC-5"]
    with path.open("rb") as f:
        up = target.post(
            f"/api/projects/{s0.ids['TD-PRJ-2']}/documents",
            files={"file": ("회의록.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth(s0.tokens["TD-ACC-V3"]),
        )
    assert up.status_code in (200, 201, 202), up.text
    other_doc = up.json()["id"]
    s0.await_document("TD-ACC-V3", other_doc)
    res = target.post(_base(s0), json={"documentId": other_doc}, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code in (400, 403, 404), res.text


def test_UC_020_S07_등록_취소(target, s0):
    """등록 뒤 취소 → 확정 전 목록 없음, TD-DOC-1 남음, 기존 3건 그대로, 등록·취소 활동 기록 (AC-020-6·9)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    made = target.post(_base(s0), json={"documentId": s0.ids["TD-DOC-1"]}, headers=v1)
    assert made.status_code == 201, made.text
    bid = made.json()["id"]
    assert target.delete(f"{_base(s0)}/{bid}", headers=v1).status_code == 204
    assert target.get(_base(s0), headers=v1).json()["state"] == "NONE"
    assert target.get(f"/api/documents/{s0.ids['TD-DOC-1']}", headers=v1).status_code == 200
    assert set(_reqs(target, s0)) == {"UR.PORT.001", "UR.PORT.002", "UR.PORT.003"}
    assert _activity_kinds(target, s0, bid) == ["BASELINE_REGISTERED", "BASELINE_DISCARDED"]


def test_UC_020_S01_표_형식_명세서_등록_제출(target, s0, screen):
    """3건 추출(A 같음·B 다름·D 새), 상위 SR.PORT.001, 제출 뒤 확정 대기. 목록·이행률 불변, 등록·제출 활동 기록 (AC-020-1·4·9).

    뒤 시나리오가 이 제출에 기대므로 판정은 모아서 끝에 한다(제출은 항목 판정과 무관하게 시도)."""
    v1, c1 = auth(s0.tokens["TD-ACC-V1"]), auth(s0.tokens["TD-ACC-C1"])
    problems: list[str] = []
    before_rate = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/requirements/summary", headers=c1).json()
    made = target.post(_base(s0), json={"documentId": s0.ids["TD-DOC-1"]}, headers=v1)
    assert made.status_code == 201, made.text
    b = made.json()
    s0.ids["BASELINE-1"] = b["id"]
    items = {i["code"]: i for i in b["items"]}
    if set(items) != {"UR.PORT.001", "UR.PORT.002", "UR.PORT.004"}:
        problems.append(f"추출 코드 {sorted(items)}")
    for code, want in (("UR.PORT.001", "SAME"), ("UR.PORT.002", "CHANGED"), ("UR.PORT.004", "NEW")):
        got = items.get(code, {}).get("match")
        if got != want:
            it = items.get(code, {})
            problems.append(
                f"{code} 판정 {got} (기대 {want}); 명세 {it.get('title')!r}/{it.get('priority')} "
                f"기존 {it.get('existing')}"
            )
    if not all(i["location"].startswith("표 1") for i in items.values()):
        problems.append(f"위치 {[i['location'] for i in items.values()]}")
    if [p["code"] for p in b["parents"]] != ["SR.PORT.001"]:
        problems.append(f"상위 요구사항 {[p['code'] for p in b['parents']]} (기대 ['SR.PORT.001'])")
    if b["blockingCount"] != 0:
        problems.append(f"막는 문제 {b['blockingCount']}")
    sub = target.post(f"{_base(s0)}/{b['id']}/submit", headers=v1)
    assert sub.status_code == 200 and sub.json()["status"] == "SUBMITTED", sub.text
    if set(_reqs(target, s0)) != {"UR.PORT.001", "UR.PORT.002", "UR.PORT.003"}:
        problems.append("제출 뒤 요구사항 목록이 기존 3건과 다르다")
    after_rate = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/requirements/summary", headers=c1).json()
    if after_rate["verifiedRate"] != before_rate["verifiedRate"]:
        problems.append("제출로 이행률이 바뀌었다")
    kinds = _activity_kinds(target, s0, b["id"])
    if kinds != ["BASELINE_REGISTERED", "BASELINE_SUBMITTED"]:
        problems.append(f"활동 기록 {kinds} (기대 등록·제출)")
    assert not problems, problems
    _ui_UC_020_S01(screen, s0)


def test_UC_020_S11_제출_뒤_수정(target, s0):
    """확정 대기 상태에서 항목 수정 → 거절 (E8). 발주기관의 항목 수정·제출도 거절 (AC-020-3)."""
    v1, c1 = auth(s0.tokens["TD-ACC-V1"]), auth(s0.tokens["TD-ACC-C1"])
    bid = s0.ids["BASELINE-1"]
    b = target.get(f"{_base(s0)}/{bid}", headers=v1).json()
    item = b["items"][0]
    body = {"code": item["code"], "title": "바꿈", "priority": "SHOULD"}
    assert target.put(f"{_base(s0)}/{bid}/items/{item['id']}", json=body, headers=v1).status_code == 409
    assert target.put(f"{_base(s0)}/{bid}/items/{item['id']}", json=body, headers=c1).status_code in (403, 409)
    assert target.post(f"{_base(s0)}/{bid}/submit", headers=c1).status_code in (403, 409)


def test_UC_020_S06_두_번째_등록(target, s0):
    """확정 대기 등록이 있을 때 새 등록 → 거절 (AC-020-5). 확정본 있을 때는 UC-021-S02 뒤 본다."""
    res = target.post(_base(s0), json={"documentId": s0.ids["TD-DOC-1"]}, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code == 409, res.text


# ------------------------------------------------------------------ UC-021 (앞부분)


def test_UC_021_S04_제출_전_열람_용역사_확정(target, s0):
    """용역사 확정 → 거절 (AC-021-8). 발주기관은 확정 대기 목록을 본다."""
    bid = s0.ids["BASELINE-1"]
    assert target.post(f"{_base(s0)}/{bid}/confirm", json={}, headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403
    assert target.get(f"{_base(s0)}/{bid}", headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 200


def test_UC_021_S05_같음을_바꾸겠다고_선택(target, s0):
    """「같음」 A 를 바꾸겠다고 고르면 거절, 상태는 확정 대기 유지 (E2)."""
    bid = s0.ids["BASELINE-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    res = target.post(f"{_base(s0)}/{bid}/confirm", json={"applySpecCodes": ["UR.PORT.001"]}, headers=c1)
    assert res.status_code == 400, res.text
    assert target.get(f"{_base(s0)}/{bid}", headers=c1).json()["status"] == "SUBMITTED"


def test_UC_021_S03_돌려보내기(target, s0, screen):
    """사유 「중요도 재검토」로 돌려보냄 → 정리 중, 용역사 화면에 사유, 활동 기록 (AC-021-8)."""
    bid = s0.ids["BASELINE-1"]
    c1, v1 = auth(s0.tokens["TD-ACC-C1"]), auth(s0.tokens["TD-ACC-V1"])
    assert target.post(f"{_base(s0)}/{bid}/return", json={"reason": ""}, headers=c1).status_code in (400, 422)
    res = target.post(f"{_base(s0)}/{bid}/return", json={"reason": "중요도 재검토"}, headers=c1)
    assert res.status_code == 200 and res.json()["status"] == "DRAFT", res.text
    seen = target.get(f"{_base(s0)}/{bid}", headers=v1).json()
    assert seen["returnedReason"] == "중요도 재검토"
    acts = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/activity?size=50", headers=v1)
    if acts.status_code == 200:
        assert "돌려" in acts.text or "반려" in acts.text, "활동 기록에 돌려보냄이 없다"
    _ui_UC_021_S03(screen, s0)


def test_UC_020_S08_돌려보냄_뒤_재제출(target, s0, screen):
    """사유 확인 → 고침 → 제출 → 확정 대기, 사유 표시 사라짐 (AC-020-7). API 부분."""
    bid = s0.ids["BASELINE-1"]
    v1 = auth(s0.tokens["TD-ACC-V1"])
    res = target.post(f"{_base(s0)}/{bid}/submit", headers=v1)
    assert res.status_code == 200 and res.json()["status"] == "SUBMITTED", res.text
    assert not res.json()["returnedReason"], "재제출 뒤에도 돌려보낸 사유가 남아 있다"
    _ui_UC_020_S08(screen, s0)


@pytest.mark.skip(reason="동시 확정은 두 요청을 겹쳐 보내야 한다. 5174 에서 따로 돈다")
def test_UC_021_S09_동시_확정(target, s0):
    """확정 2회 동시 → 1회만 확정 (COMMON-S04)."""


def test_UC_021_S02_기존_있는_사업의_확정(target, s0):
    """미리보기 새1·같음1·바뀜1·포함되지 않음1. 확정 뒤 4행, 확정 목록 3, B 명칭·이력, A 보존 (AC-021-1·2·3·4)."""
    bid = s0.ids["BASELINE-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    pid = s0.ids["TD-PRJ-1"]
    before = _detail(target, s0, s0.ids["TD-REQ-A"])
    preview = target.get(f"{_base(s0)}/{bid}", headers=c1).json()
    matches = sorted(i["match"] for i in preview["items"])
    problems: list[str] = []
    if matches != ["CHANGED", "NEW", "SAME"]:
        problems.append(f"미리보기 판정 {matches} (기대 새1·같음1·바뀜1)")
    if [m["code"] for m in preview["missing"]] != ["UR.PORT.003"]:
        problems.append(f"포함되지 않음 {preview['missing']}")
    res = target.post(f"{_base(s0)}/{bid}/confirm", json={"applySpecCodes": ["UR.PORT.002"]}, headers=c1)
    assert res.status_code == 200, res.text
    c = res.json()
    assert c["status"] == "CONFIRMED"
    if c["counts"] != {"NEW": 1, "SAME": 1, "CHANGED": 1}:
        problems.append(f"확정 건수 {c['counts']}")
    assert c["confirmedBy"] == d.ACCOUNTS["TD-ACC-C1"].display
    reqs = _reqs(target, s0)
    assert len(reqs) == 4, reqs.keys()
    assert sum(1 for r in reqs.values() if r["inBaseline"]) == 3
    assert reqs["UR.PORT.003"]["inBaseline"] is False
    assert reqs["UR.PORT.002"]["title"] == "민원 신청 조회·취소"
    assert reqs["UR.PORT.002"]["id"] == s0.ids["TD-REQ-B"]
    b_detail = _detail(target, s0, s0.ids["TD-REQ-B"])
    assert any(h["field"] == "title" and h["fromValue"] == "민원 신청 조회" for h in b_detail["history"]), b_detail["history"]
    after = _detail(target, s0, s0.ids["TD-REQ-A"])
    assert after["status"] == "VERIFIED" and after["id"] == before["id"]
    assert {(lk["fromType"], lk["fromId"]) for lk in after["traceLinks"]} == {(lk["fromType"], lk["fromId"]) for lk in before["traceLinks"]}
    state = target.get(_base(s0), headers=c1).json()
    assert state["state"] == "CONFIRMED" and state["outsideBaselineCount"] == 1
    s0.ids["REQ-D"] = reqs["UR.PORT.004"]["id"]
    with tx() as cur:
        s0.ids["LINKS-AFTER-CONFIRM"] = str(len(_links(cur, pid)))
    assert not problems, problems


def test_UC_020_S06b_확정본_있을_때_등록(target, s0):
    """확정본이 있으면 새 등록 거절 (AC-020-5 둘째 절)."""
    res = target.post(_base(s0), json={"documentId": s0.ids["TD-DOC-1"]}, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code == 409 and res.json().get("code") == "BASELINE_CONFIRMED", res.text


def test_UC_020_S02_읽히지_않는_양식_보완(target, s0, screen):
    """TD-PRJ-9, TD-DOC-7(카드형 명세서 PDF) 등록 → 「찾지 못했습니다」(0건) → 항목 3건 직접 추가 → 제출 (AC-020-1 E2).

    화면 시나리오. 끝에 돌려보내고 등록을 취소해 TD-PRJ-9 를 비운다(UC-021-S01 이 같은 사업에 첫 확정을 한다)."""
    if not screen:
        pytest.skip("화면 시나리오. 원격 대상 + AXLINK_BROWSER_CHROME 에서 돈다")
    pid = s0.ids["TD-PRJ-9"]
    v1, c1 = auth(s0.tokens["TD-ACC-V1"]), auth(s0.tokens["TD-ACC-C1"])
    s0._upload("TD-ACC-V1", "TD-PRJ-9", "TD-DOC-7")
    cards = [
        ("UR.CARD.001", "알림 수신 설정", "시민은 민원 처리 알림을 받을 방법(문자, 앱)을 고를 수 있다.", "필수"),
        ("UR.CARD.002", "처리 결과 알림", "민원 처리가 끝나면 시민이 고른 방법으로 결과를 알린다.", "필수"),
        ("UR.CARD.003", "알림 이력 조회", "시민은 지난 30일 동안 받은 알림을 목록으로 볼 수 있다.", "권장"),
    ]
    bid = None
    try:
        sc = screen("TD-ACC-V1")
        page = sc.page
        sc.open(f"/p/{pid}/requirement-baseline").see("요구사항 명세서")
        page.locator("#spec-doc").click()
        page.get_by_role("option", name=re.compile("카드형-명세서")).click()
        page.get_by_role("button", name="명세서로 등록").click()
        sc.see("명세서에서 요구사항을 찾지 못했습니다")
        sc.shot("0건_안내")
        for code, title, body, priority in cards:
            page.get_by_role("button", name="항목 추가").click()
            dlg = page.get_by_role("dialog")
            dlg.locator("#b-code").fill(code)
            dlg.locator("#b-title").fill(title)
            dlg.locator("#b-body").fill(body)
            dlg.locator("#b-priority").click()
            page.get_by_role("option", name=priority, exact=True).click()
            dlg.get_by_role("button", name="저장").click()
            sc.see(code)
        sc.shot("직접_추가_3건")
        page.get_by_role("button", name="제출", exact=True).click()
        sc.see("발주기관 확정 대기", "UR.CARD.001", "UR.CARD.002", "UR.CARD.003")
        state = target.get(_base(s0, "TD-PRJ-9"), headers=v1).json()
        bid = state["working"]["id"]
        working = target.get(f"{_base(s0, 'TD-PRJ-9')}/{bid}", headers=v1).json()
        assert working["status"] == "SUBMITTED", working["status"]
        got = {i["code"]: (i["title"], i["priority"]) for i in working["items"]}
        assert got == {
            "UR.CARD.001": ("알림 수신 설정", "MUST"),
            "UR.CARD.002": ("처리 결과 알림", "MUST"),
            "UR.CARD.003": ("알림 이력 조회", "SHOULD"),
        }, got
        sc.done()
    finally:
        if bid is None:
            state = target.get(_base(s0, "TD-PRJ-9"), headers=v1).json()
            bid = (state.get("working") or {}).get("id")
        if bid:
            target.post(f"{_base(s0, 'TD-PRJ-9')}/{bid}/return", json={"reason": "시험 정리(UC-020-S02)"}, headers=c1)
            target.delete(f"{_base(s0, 'TD-PRJ-9')}/{bid}", headers=v1)


def test_UC_021_S01_기존_없는_사업의_첫_확정(target, s0, screen):
    """TD-PRJ-9 에 같은 3행 명세서 → 확정 → 요구사항 3, 확정본 v1, 포함되지 않음 0, 확정자 (AC-021-1·4·9)."""
    v1, c1 = auth(s0.tokens["TD-ACC-V1"]), auth(s0.tokens["TD-ACC-C1"])
    pid = s0.ids["TD-PRJ-9"]
    path = s0.files["TD-DOC-1"]
    with path.open("rb") as f:
        up = target.post(f"/api/projects/{pid}/documents", files={"file": ("요구사항명세서_v1.0.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, headers=v1)
    assert up.status_code in (200, 201, 202), up.text
    s0.await_document("TD-ACC-V1", up.json()["id"])
    made = target.post(_base(s0, "TD-PRJ-9"), json={"documentId": up.json()["id"]}, headers=v1)
    assert made.status_code == 201, made.text
    bid = made.json()["id"]
    assert all(i["match"] == "NEW" for i in made.json()["items"])
    assert target.post(f"{_base(s0, 'TD-PRJ-9')}/{bid}/submit", headers=v1).status_code == 200
    res = target.post(f"{_base(s0, 'TD-PRJ-9')}/{bid}/confirm", json={}, headers=c1)
    assert res.status_code == 200, res.text
    c = res.json()
    assert c["counts"] == {"NEW": 3, "SAME": 0, "CHANGED": 0} and c["missing"] == []
    assert c["version"] == 1 and c["confirmedBy"] == d.ACCOUNTS["TD-ACC-C1"].display
    assert c["confirmedByRole"] == "CLIENT"
    reqs = _reqs(target, s0, "TD-PRJ-9")
    assert set(reqs) == {"UR.PORT.001", "UR.PORT.002", "UR.PORT.004"}
    state = target.get(_base(s0, "TD-PRJ-9"), headers=c1).json()
    assert state["outsideBaselineCount"] == 0
    _ui_UC_021_S01(screen, s0)


def test_UC_021_S07_확정_뒤_재수집(target, s0, replay):
    """S1 자료로 재수집 → 요구사항 4행 유지, B 명칭·A 지정 유지, G2 는 B 의 출처로 남음 (AC-021-6)."""
    replay.state = "S1"
    s0.ids["SOURCE-STATE"] = "S1"
    for con in ("TD-CON-1", "TD-CON-2"):
        job = target.post(f"/api/connections/{s0.ids[con]}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"])).json()
        assert job["status"] == "SUCCEEDED", job
    reqs = _reqs(target, s0)
    assert len(reqs) == 4
    assert reqs["UR.PORT.002"]["title"] == "민원 신청 조회·취소"
    assert reqs["UR.PORT.001"]["status"] == "VERIFIED"
    issues = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/issues?size=100", headers=auth(s0.tokens["TD-ACC-C1"])).json()
    keys = {i["key"] for i in issues["content"]}
    # 확정 뒤에도 출처 연결을 끊지 않는다(DEF-V018 결정 b). G2 는 일반 이슈로 세지 않는다
    assert "GH-2" not in keys, "기준선 안 요구사항 B 의 출처 이슈 G2 가 일반 이슈로 바뀌었다"


def test_UC_021_S08_없는_코드_참조_상위_코드(target, s0, replay):
    """커밋 [UR.PORT.009] 변형 → 「요구사항에 없는 코드」 1건, SR.PORT.001 은 없음 (AC-021-7)."""
    replay.faults = Faults(extra_commits=[d.Commit(
        "TD-CMT-X", "TD-CON-1", "f0f0f0f00009f0f0f0f00009f0f0f0f00009f0f0",
        "fix: 없는 요구사항 참조 [UR.PORT.009] 와 상위 SR.PORT.001 언급", ("src/x.py",),
        "2026-09-01T09:00:00Z", "S0",
    )])
    job = target.post(f"/api/connections/{s0.ids['TD-CON-1']}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"])).json()
    assert job["status"] == "SUCCEEDED", job
    refs = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/requirements/unresolved-refs", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert refs.status_code == 200, refs.text
    # 화면은 parentTitle 이 붙은 줄을 「상위 요구사항 ID」로 따로 접고, 나머지만 「요구사항에 없는 ID」로 보인다
    unknown = [r["code"] for r in refs.json() if not r.get("parentTitle")]
    parents = [r["code"] for r in refs.json() if r.get("parentTitle")]
    assert "UR.PORT.009" in unknown, refs.json()
    assert "SR.PORT.001" not in unknown, refs.json()
    assert "SR.PORT.001" in parents, refs.json()


@pytest.mark.skip(reason="DEC-11(이행률 분모) 결정 전. 결정 뒤 7.7 → 7.x 로 옮긴 값으로 단언한다")
def test_UC_021_S10_분모_AI_범위(target, s0):
    """DEC-11 제안 기준 분모 3, 이행률 33.3% (AC-021-10)."""


# ------------------------------------------------------------------ UC-022


def test_UC_022_S01_커밋_이슈_연결(target, s0, screen):
    """A 상세: TD-CMT-1(구현, 근거 「[UR.PORT.001]」), R1·R2·R9 커스텀 필드 연결. 근거 원문·링크 (AC-022-1·2)."""
    detail = _detail(target, s0, s0.ids["TD-REQ-A"])
    links = [lk for lk in detail["traceLinks"] if lk["status"] == "ACTIVE"]
    by_from = {(lk["fromType"], lk["fromLabel"]): lk for lk in links}
    commit = next((lk for lk in links if lk["fromType"] == "CODE_CHANGE" and "통합 로그인 구현" in lk["fromLabel"]), None)
    assert commit is not None, [lk["fromLabel"] for lk in links]
    assert commit["linkKind"] == "IMPLEMENTS" and "[UR.PORT.001]" in (commit["evidenceText"] or "")
    assert commit["externalUrl"]
    issue_links = [lk for lk in links if lk["fromType"] == "ISSUE"]
    assert len(issue_links) >= 3, [lk["fromLabel"] for lk in issue_links]
    assert all(lk["evidenceKind"] and lk["externalUrl"] for lk in links), links
    assert all(lk["evidenceText"] for lk in links), "근거 원문이 비어 있는 자동 연결이 있다"
    assert by_from  # 사용만
    _ui_UC_022_S01(screen, s0)


def test_UC_022_S03_멱등_재생성(target, s0):
    """재생성 ×3 → 연결 집합 동일 (AC-022-3, COMMON-S08)."""
    pid = s0.ids["TD-PRJ-1"]
    sets = []
    for _ in range(3):
        with tx() as cur:
            trace_service.build_project_links(cur, pid)
            sets.append(_links(cur, pid))
    assert sets[0] == sets[1] == sets[2]


def test_UC_022_S04_같은_번호_다른_연결(target, s0):
    """TD-CMT-4(GH-4, TD-CON-1) → G4, TD-CMT-W1(GH-4, TD-CON-3) → W4. 서로 바뀌지 않음 (AC-022-5)."""
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        rows = fetch_all(
            cur,
            """
            select c.external_id as from_ext, c.tool_connection_id::text as from_con,
                   i.external_id as to_ext, i.tool_connection_id::text as to_con
              from trace_link l
              join code_change c on c.id = l.from_id
              join issue i on i.id = l.to_id
             where l.project_id = %s and l.to_type = 'ISSUE' and c.kind = 'COMMIT'
            """,
            (pid,),
        )
    pairs = {(r["from_con"], r["to_ext"], r["to_con"]) for r in rows}
    con1, con3 = s0.ids["TD-CON-1"], s0.ids["TD-CON-3"]
    assert (con1, "issue:4", con1) in pairs, pairs
    assert (con3, "issue:4", con3) in pairs, pairs
    assert (con1, "issue:4", con3) not in pairs and (con3, "issue:4", con1) not in pairs


def test_UC_022_S12_이슈_본문_참조는_해석하지_않음(target, s0):
    """G4 본문 RM-204 → R4 연결 없음 (AC-022-2)."""
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        row = fetch_one(
            cur,
            """
            select 1 from trace_link l join issue a on a.id = l.from_id join issue b on b.id = l.to_id
             where l.project_id = %s and a.external_id = 'issue:4' and b.external_id = '204'
            """,
            (pid,),
        )
    assert row is None, "이슈 본문의 RM-204 참조가 추적관계로 만들어졌다"


def test_UC_022_S05_지나가는_언급(target, s0):
    """설계 문서 20줄의 UR.PORT.003 언급 → C 로 연결 없음 (AC-022-2)."""
    detail = _detail(target, s0, s0.ids["TD-REQ-C"])
    docs = [lk for lk in detail["traceLinks"] if lk["fromType"] == "REPO_DOCUMENT" or "설계-민원조회" in lk["fromLabel"]]
    assert docs == [], [lk["fromLabel"] for lk in docs]


def test_UC_022_S07_일관성(target, s0):
    """목록·추적표·상세가 같은 상태를 말한다 (AC-022-6)."""
    c1 = auth(s0.tokens["TD-ACC-C1"])
    pid = s0.ids["TD-PRJ-1"]
    reqs = _reqs(target, s0)
    rows = target.get(f"/api/projects/{pid}/traceability?size=100", headers=c1).json()["content"]
    by_code = {r["requirementCode"]: r for r in rows}
    for code, r in reqs.items():
        assert by_code[code]["requirementStatus"] == r["status"], code
        detail = _detail(target, s0, r["id"])
        assert detail["status"] == r["status"], code
        active = [lk for lk in detail["traceLinks"] if lk["status"] == "ACTIVE" and lk["linkKind"] == "IMPLEMENTS"]
        assert len(by_code[code]["implementsList"]) == len(active), (code, by_code[code]["implementsList"], active)


def test_UC_022_S08_구조적_긍정(target, s0):
    """TD-PR-1(Closes #4) → G4, R2 → R1(후속) 연결, 근거 유형 구조적 (AC-022-7·1)."""
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        rel = fetch_one(
            cur,
            """
            select l.evidence_kind from trace_link l join issue a on a.id = l.from_id
              join issue b on b.id = l.to_id
             where l.project_id = %s and a.external_id = '202' and b.external_id = '201'
            """,
            (pid,),
        )
        pr = fetch_one(
            cur,
            """
            select 1 from trace_link l join code_change c on c.id = l.from_id join issue i on i.id = l.to_id
             where l.project_id = %s and c.external_id = 'pull_request:6' and i.external_id = 'issue:4'
            """,
            (pid,),
        )
    assert rel is not None, "R2 → R1 이슈관계 연결이 없다"
    assert pr is not None, "PR-1 Closes #4 → G4 연결이 없다(DEF-V010)"


def test_UC_022_S09_구조적_부정(target, s0):
    """PR-1 → 요구사항 없음. PR-2 → R3 만 있고 → B 없음 (AC-022-7·2)."""
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        pr1_req = fetch_one(cur, """
            select 1 from trace_link l join code_change c on c.id = l.from_id
             where l.project_id = %s and c.external_id = 'pull_request:6' and l.to_type = 'REQUIREMENT'
            """, (pid,))
        pr2_r3 = fetch_one(cur, """
            select 1 from trace_link l join code_change c on c.id = l.from_id join issue i on i.id = l.to_id
             where l.project_id = %s and c.external_id = 'pull_request:7' and i.external_id = '203'
            """, (pid,))
        pr2_b = fetch_one(cur, """
            select 1 from trace_link l join code_change c on c.id = l.from_id
             where l.project_id = %s and c.external_id = 'pull_request:7' and l.to_type = 'REQUIREMENT'
               and l.to_id = %s
            """, (pid, s0.ids["TD-REQ-B"]))
    assert pr1_req is None, "코드 없는 PR-1 이 요구사항으로 이어졌다"
    assert pr2_r3 is not None, "PR-2 의 RM-203 참조가 R3 연결로 남지 않았다"
    assert pr2_b is None, "PR-2 가 R3 를 거쳐 요구사항 B 로 전이됐다"


def test_UC_022_S11_커스텀_필드_문서_안_코드(target, s0):
    """커스텀 필드 연결 6건(R1·R2·R9→A, R3·R10→B, R5→C), 설계 문서 → B(6줄, #L6). 20줄 언급 없음 (AC-022-1·2)."""
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        rows = fetch_all(cur, """
            select i.external_id as issue, l.to_id::text as req
              from trace_link l join issue i on i.id = l.from_id
             where l.project_id = %s and l.to_type = 'REQUIREMENT' and l.evidence_kind = 'CUSTOM_FIELD'
               and l.status = 'ACTIVE'
            """, (pid,))
        doc = fetch_all(cur, """
            select l.evidence_url, l.to_id::text as req from trace_link l
             where l.project_id = %s and l.from_type = 'REPO_DOCUMENT' and l.status = 'ACTIVE'
            """, (pid,))
    pairs = {(r["issue"], r["req"]) for r in rows}
    a, b, c = s0.ids["TD-REQ-A"], s0.ids["TD-REQ-B"], s0.ids["TD-REQ-C"]
    assert pairs == {("201", a), ("202", a), ("209", a), ("203", b), ("210", b), ("205", c)}, pairs
    assert len(doc) == 1 and doc[0]["req"] == b, doc
    assert (doc[0]["evidence_url"] or "").endswith("#L6"), doc[0]["evidence_url"]


def test_UC_022_S06_수집_전_사업(target, s0, screen):
    """TD-PRJ-3 추적표 → 연결 없음, 안내 (E1). 화면 시나리오."""
    if not screen:
        pytest.skip("화면 시나리오. 원격 대상 + AXLINK_BROWSER_CHROME 에서 돈다")
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{s0.ids['TD-PRJ-3']}/traceability")
    sc.see("요구사항이 없습니다", "명세서를 등록하고 발주기관이 확정하면 목록이 생깁니다")
    sc.not_see(re.compile(r"외 \d+건 더 보기"), "근거:")
    sc.done()


def test_UC_022_S02_근거_사라짐(target, s0, replay):
    """TD-CMT-1 메시지에서 코드 제거 뒤 재수집 → 연결 「근거 사라짐」, 삭제되지 않음 (AC-022-4)."""
    sha = d.COMMITS[0].sha
    replay.faults = Faults(commit_message={sha: "feat(auth): 통합 로그인 구현"})
    job = target.post(f"/api/connections/{s0.ids['TD-CON-1']}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"])).json()
    assert job["status"] == "SUCCEEDED", job
    detail = _detail(target, s0, s0.ids["TD-REQ-A"])
    commit = next((lk for lk in detail["traceLinks"] if lk["fromType"] == "CODE_CHANGE" and "통합 로그인 구현" in lk["fromLabel"]), None)
    assert commit is not None, "근거가 사라진 연결이 지워졌다"
    assert commit["status"] == "BROKEN", commit
    assert commit["statusReason"] and commit["statusChangedAt"], commit
    # 복원: 원래 메시지로 재수집
    replay.faults = Faults()  # 상태는 fixture 가 이어 쓴다(S1)
    target.post(f"/api/connections/{s0.ids['TD-CON-1']}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"]))


def test_UC_022_S10_조회_실패_vs_소실(target, s0, replay):
    """재수집 중 응답 없음 → 연결 그대로 유효 (AC-022-8). 소실·대체는 S02 와 별도 설계."""
    before = _detail(target, s0, s0.ids["TD-REQ-A"])
    replay.faults = Faults(unreachable=True)
    job = target.post(f"/api/connections/{s0.ids['TD-CON-1']}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"])).json()
    assert job["status"] == "FAILED"
    after = _detail(target, s0, s0.ids["TD-REQ-A"])
    assert {(lk["id"], lk["status"]) for lk in before["traceLinks"]} == {(lk["id"], lk["status"]) for lk in after["traceLinks"]}


# ------------------------------------------------------------------ UC-023


def test_UC_023_S04_용역사_사유_없음(target, s0):
    """V1 지정 / C1 빈 사유 → 각각 거절 (AC-023-5)."""
    pid = s0.ids["TD-PRJ-1"]
    rid = s0.ids["REQ-D"]
    assert target.put(f"/api/projects/{pid}/requirements/{rid}/status", json={"status": "VERIFIED", "reason": "x"}, headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403
    assert target.put(f"/api/projects/{pid}/requirements/{rid}/status", json={"status": "VERIFIED", "reason": ""}, headers=auth(s0.tokens["TD-ACC-C1"])).status_code in (400, 422)


def test_UC_023_S05_지표_독립(target, s0):
    """지정 전후 보고 진척률·완료 확인율 불변 (AC-023-6, CC-09). 승인률은 DEC-12."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    before_p = target.get(f"/api/projects/{pid}/progress?at={d.T0.isoformat()}", headers=c1).json()["representative"]
    before_c = target.get(f"/api/projects/{pid}/wbs/completion?at={d.T0.isoformat()}", headers=c1).json()
    res = target.put(f"/api/projects/{pid}/requirements/{s0.ids['REQ-D']}/status", json={"status": "VERIFIED", "reason": "시험 결과서 확인"}, headers=c1)
    assert res.status_code == 200, res.text
    after_p = target.get(f"/api/projects/{pid}/progress?at={d.T0.isoformat()}", headers=c1).json()["representative"]
    after_c = target.get(f"/api/projects/{pid}/wbs/completion?at={d.T0.isoformat()}", headers=c1).json()
    assert after_p == before_p
    assert after_c["confirmedCount"] == before_c["confirmedCount"]


def test_UC_023_S01_지정(target, s0):
    """D 「검증」 지정 → 지금 상태 검증, 근거 상태 정의 유지, 지정자·조직·사유 (AC-023-1). 이행률은 DEC-03·11."""
    detail = _detail(target, s0, s0.ids["REQ-D"])
    assert detail["status"] == "VERIFIED"
    assert detail["statusBasis"] == "CLIENT_DECIDED"
    assert detail["evidenceStatus"] == "DEFINED"
    dec = detail["decision"]
    assert dec and dec["reason"] == "시험 결과서 확인" and dec["decidedBy"]


def test_UC_023_S02_재수집_뒤_보존(target, s0, replay):
    """S1 수집 뒤 D 지정 유지 (AC-023-2)."""
    replay.state = "S1"
    job = target.post(f"/api/connections/{s0.ids['TD-CON-1']}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"])).json()
    assert job["status"] == "SUCCEEDED", job
    detail = _detail(target, s0, s0.ids["REQ-D"])
    assert detail["status"] == "VERIFIED" and detail["statusBasis"] == "CLIENT_DECIDED"


def test_UC_023_S03_되돌림(target, s0):
    """되돌림 → 정의 상태, 재되돌림 거절 (AC-023-3)."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    res = target.post(f"/api/projects/{pid}/requirements/{s0.ids['REQ-D']}/status/revert", json={"reason": "근거 재확인"}, headers=c1)
    assert res.status_code == 200, res.text
    detail = _detail(target, s0, s0.ids["REQ-D"])
    assert detail["status"] == "DEFINED" and detail["statusBasis"] != "CLIENT_DECIDED"
    again = target.post(f"/api/projects/{pid}/requirements/{s0.ids['REQ-D']}/status/revert", json={"reason": "다시"}, headers=c1)
    assert again.status_code == 409, again.text


@pytest.mark.skip(reason="AI 「요구사항 이행률」 답은 실모델이 필요하다. DEC-03·11 결정 뒤 5174 에서 본다")
def test_UC_023_S06_일관성(target, s0):
    """목록·추적표·스냅샷·AI 답이 같은 이행률 (AC-023-4)."""


# 삭제가 막히지 않으면 S0 가 깨지므로 가장 마지막에 돈다(AC-020-8 미구현 시 뒤 시나리오 보호)
def test_UC_020_S09_명세서_문서_삭제_시도(target, s0):
    """등록이 살아 있는 동안 TD-DOC-1 삭제 → 거절 (AC-020-8)."""
    res = target.delete(f"/api/documents/{s0.ids['TD-DOC-1']}", headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code in (400, 409), f"명세서 문서 삭제가 막히지 않았다: {res.status_code} {res.text[:200]}"
    assert target.get(f"/api/documents/{s0.ids['TD-DOC-1']}", headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 200


def _ui_UC_020_S01(screen, s0):
    """화면: 용역사 기준선 화면 「발주기관 확정 대기」·추출 항목, 발주기관 요구사항 목록은 기존 3건."""
    if not screen:
        return
    pid = s0.ids["TD-PRJ-1"]
    sc = screen("TD-ACC-V1")
    sc.open(f"/p/{pid}/requirement-baseline").see("발주기관 확정 대기", "UR.PORT.004", "SR.PORT.001")
    sc.done()
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/traceability").see("UR.PORT.001", "UR.PORT.003")
    sc.not_see("UR.PORT.004", selector="table")
    sc.done()


def _ui_UC_021_S03(screen, s0):
    """화면: 용역사 기준선 화면에 돌려보낸 사유."""
    if not screen:
        return
    sc = screen("TD-ACC-V1")
    sc.open(f"/p/{s0.ids['TD-PRJ-1']}/requirement-baseline")
    sc.see("발주기관이 돌려보냈습니다", "중요도 재검토")
    sc.done()


def _ui_UC_020_S08(screen, s0):
    """화면: 재제출 뒤 「발주기관 확정 대기」, 돌려보낸 사유 사라짐."""
    if not screen:
        return
    sc = screen("TD-ACC-V1")
    sc.open(f"/p/{s0.ids['TD-PRJ-1']}/requirement-baseline").see("발주기관 확정 대기")
    sc.not_see("발주기관이 돌려보냈습니다", "중요도 재검토")
    sc.done()


def _ui_UC_021_S01(screen, s0):
    """화면: TD-PRJ-9 확정본 v1·확정자, 요구사항 3건."""
    if not screen:
        return
    pid = s0.ids["TD-PRJ-9"]
    sc = screen("TD-ACC-C1")
    who = d.ACCOUNTS["TD-ACC-C1"].display
    sc.open(f"/p/{pid}/requirement-baseline").see("확정본 v1", f"확정 {who}")
    sc.shot("확정본")
    sc.open(f"/p/{pid}/traceability").see("UR.PORT.001", "UR.PORT.002", "UR.PORT.004", "3건")
    sc.done()


def _ui_UC_022_S01(screen, s0):
    """화면: A 줄에 커밋(근거 메시지)·커스텀 필드 이슈 R1·R2·R9 가 링크로 보인다."""
    if not screen:
        return
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{s0.ids['TD-PRJ-1']}/traceability").see("UR.PORT.001")
    row = sc.page.locator("tr", has_text="UR.PORT.001").first
    more = row.get_by_text(re.compile(r"외 \d+건 더 보기"))
    if more.count():
        more.first.click()
    row_text = row.inner_text()
    for want in ("[UR.PORT.001]", "RM-201", "RM-202", "RM-209"):
        assert want in row_text, f"A 줄에 {want} 가 없다: {row_text!r}"
    hrefs = [a.get_attribute("href") or "" for a in row.locator("a").all()]
    assert sum(1 for h in hrefs if h.startswith("http")) >= 4, hrefs
    sc.done()
