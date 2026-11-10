# ruff: noqa: E501
"""F 그룹: 확인 요청·조치 보고·활동 기록 (UC-050 ~ UC-053) 예제 시나리오.

S0 → S0r(TD-RR-1 등록) → S0a → S1(원천 반영) → S1r(보고) → 재요청 → 재보고 → 확인완료를
한 흐름으로 돈다. 알림은 각 전이 직후에 읽어 모아 두고 UC-053-S02 에서 판정한다.
실연동 무기록(UC-050-S05·UC-051-S05)은 어댑터 정적 검사만 자동으로 하고 원천 비교는 5174 실연동에서 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.db import fetch_one, tx
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import files
from tests.fixtures.im009.replay import Faults, ReplaySource, install, restore_faults
from tests.scenarios.conftest import auth

pytestmark = pytest.mark.db

T0 = d.T0.isoformat()
ADAPTERS = Path(__file__).resolve().parents[2] / "app" / "integration" / "adapter"


@pytest.fixture
def replay(monkeypatch, s0) -> ReplaySource:
    return install(monkeypatch, ReplaySource(state="S1", files=s0.files))


def _get(target, s0, path: str, acc="TD-ACC-C1"):
    res = target.get(path, headers=auth(s0.tokens[acc]))
    assert res.status_code == 200, (path, res.status_code, res.text[:200])
    return res.json()


def _detail(target, s0, rid: str, acc="TD-ACC-C1") -> dict:
    return _get(target, s0, f"/api/review-requests/{rid}", acc)


def _pending(target, s0) -> int:
    rows = {p["id"]: p for p in _get(target, s0, "/api/projects?size=100")["content"]}
    return rows[s0.ids["TD-PRJ-1"]]["openReviewRequestCount"]


def _request(target, s0, target_type: str, key: str, title: str, acc="TD-ACC-C1"):
    return target.post(f"/api/projects/{s0.ids['TD-PRJ-1']}/review-requests", json={
        "targetType": target_type, "targetKey": key, "title": title, "body": "", "purpose": "GENERAL",
    }, headers=auth(s0.tokens[acc]))


def _ratio(v) -> float | None:
    if v is None:
        return None
    v = float(v)
    return round(v / 100, 4) if v > 1 else round(v, 4)


# ------------------------------------------------------------------ UC-050 (S0)


def test_UC_050_S04_거절(target, s0):
    """V1 요청 / 없는 이슈 / 빈 제목 → 각각 거절 (AC-050-3)."""
    assert _request(target, s0, "WBS_ITEM", "3.2", "x", acc="TD-ACC-V1").status_code == 403
    assert _request(target, s0, "ISSUE", "00000000-0000-4000-8000-000000000000", "x").status_code in (400, 404)
    assert _request(target, s0, "WBS_ITEM", "3.2", "").status_code in (400, 422)
    assert _pending(target, s0) == 0


def test_UC_050_S03_지표_요청(target, s0):
    """대표 진척률 요청 → 값 30.0, 단계 L1, 산출 근거 (AC-050-1)."""
    res = _request(target, s0, "METRIC", "REPRESENTATIVE", "대표 진척률 확인")
    assert res.status_code == 201, res.text
    snap = _detail(target, s0, res.json()["id"])["snapshot"]
    assert _ratio(snap["value"]) == 0.3 and snap["level"] == "L1" and snap["basis"], snap
    s0.ids["RR-METRIC"] = res.json()["id"]


def test_UC_050_S02_이슈_리스크_산출물_요청(target, s0):
    """R4 / R7 / 요구사항정의서 요청 → 상태·우선순위·담당 + 관련 지표값 저장 (AC-050-1·2). 승인률은 DEC-12."""
    pid = s0.ids["TD-PRJ-1"]
    issues = {r["key"]: r for r in _get(target, s0, f"/api/projects/{pid}/issues?size=100")["content"]}
    with tx() as cur:
        r7 = fetch_one(cur, "select id::text as id from risk where project_id = %s and title = %s", (pid, "외부 기관 일정 미확정"))
    problems: list[str] = []
    res = _request(target, s0, "ISSUE", issues["RM-204"]["id"], "외부 연계 협의 상태 확인")
    assert res.status_code == 201, res.text
    snap = _detail(target, s0, res.json()["id"])["snapshot"]
    if snap.get("status") != "IN_PROGRESS":
        problems.append(f"R4 상태 {snap.get('status')}")
    if "높음" not in str(snap) and snap.get("severity") is None:
        problems.append(f"R4 우선순위(높음)가 저장 상태에 없다: {snap}")
    if not any(k for k in snap if "rate" in k.lower() or "처리율" in str(snap.get(k, ""))):
        problems.append("이슈 요청에 일반 이슈 처리율(66.7%)이 함께 저장되지 않았다")
    res = _request(target, s0, "RISK", r7["id"], "외부 기관 일정 리스크 확인")
    assert res.status_code == 201, res.text
    snap = _detail(target, s0, res.json()["id"])["snapshot"]
    if snap.get("status") not in ("OPEN", "MITIGATING") or not snap.get("severity"):
        problems.append(f"R7 상태·심각도 {snap}")
    if not any("rate" in k.lower() or "open_risk" in k.lower() for k in snap):
        problems.append("리스크 요청에 위험 처리율 50.0%·열린 리스크 1 이 함께 저장되지 않았다")
    res = _request(target, s0, "WORK_PRODUCT", "REQUIREMENTS_SPEC", "요구사항정의서 확인")
    assert res.status_code == 201, res.text
    snap = _detail(target, s0, res.json()["id"])["snapshot"]
    if snap.get("status") != "APPROVED" or snap.get("version") != "v1":
        problems.append(f"요구사항정의서 저장 상태 {snap}")
    assert not problems, problems


def test_UC_050_S05_원천_무기록(target, s0):
    """어댑터 정적 검사: 쓰기 메서드 호출 없음 (AC-050-4, CC-01). 원천 비교는 5174 실연동."""
    offenders = []
    for path in ADAPTERS.glob("*_connector.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\.(post|put|patch|delete)\(", text):
            offenders.append((path.name, m.group(0)))
        if re.search(r"method\s*=\s*['\"](POST|PUT|PATCH|DELETE)", text):
            offenders.append((path.name, "method="))
    assert offenders == [], offenders


def test_UC_050_S01_WBS_작업_요청(target, s0):
    """S0 → S0r: 3.2 에 TD-RR-1 등록. 저장 상태(실적 40%·계획 100%·제출본 없음·지연·#204·진척률·가중치), 미처리 0 → 1 (AC-050-1·5)."""
    before = _pending(target, s0)
    s0.s0r()
    rid = s0.ids["TD-RR-1"]
    det = _detail(target, s0, rid)
    snap = det["snapshot"]
    problems: list[str] = []
    if _ratio(snap.get("actual")) != 0.4:
        problems.append(f"실적 {snap.get('actual')}")
    if _ratio(snap.get("declared_planned")) != 1.0:
        problems.append(f"계획률 {snap.get('declared_planned')}")
    if snap.get("deliverable") != "SW설계서":
        problems.append(f"산출물 열 {snap.get('deliverable')}")
    if snap.get("file_check") != "OVERDUE":
        problems.append(f"판정 {snap.get('file_check')} (기대 지연 OVERDUE)")
    if snap.get("product_version") not in (None, "", "NONE"):
        problems.append(f"제출본 {snap.get('product_version')} (기대 없음)")
    if _ratio(snap.get("weight")) != 0.2:
        problems.append(f"가중치 {snap.get('weight')}")
    if "204" not in str(snap):
        problems.append("연결 이슈 #204 진행중이 저장 상태에 없다")
    if not any("progress" in k.lower() or "representative" in k.lower() for k in snap):
        problems.append("보고 진척률 30.0% 가 저장 상태에 없다")
    if _pending(target, s0) != before + 1:
        problems.append(f"미처리 {before} → {_pending(target, s0)} (기대 +1)")
    s0.ids["PENDING-BASE"] = str(before)
    # 알림: 요청 직후 V1 미읽음, C1 자기 요청 알림 없음 (UC-053-S02 에서 판정)
    v1n = _get(target, s0, "/api/notifications", acc="TD-ACC-V1")
    c1n = _get(target, s0, "/api/notifications", acc="TD-ACC-C1")
    s0.ids["N-V1-AFTER-REQ"] = str([i["kind"] for i in v1n["items"]]) + f"|{v1n['unread']}"
    s0.ids["N-C1-AFTER-REQ"] = str([i["kind"] for i in c1n["items"] if i["kind"] == "REVIEW_REQUESTED"])
    target.post("/api/notifications/seen", json={}, headers=auth(s0.tokens["TD-ACC-V1"]))
    s0.ids["N-V1-AFTER-SEEN"] = str(_get(target, s0, "/api/notifications", acc="TD-ACC-V1")["unread"])
    assert not problems, problems


# ------------------------------------------------------------------ S0r → S0a → S1 → S1r


def test_UC_050_S06_등록_상태_불변(target, s0):
    """S0r → S1 뒤 요청 상세의 등록 시점 상태는 그대로(40%·제출본 없음·지연) (AC-050-1)."""
    s0.s0a()
    s0.s1()
    snap = _detail(target, s0, s0.ids["TD-RR-1"])["snapshot"]
    assert _ratio(snap.get("actual")) == 0.4 and snap.get("file_check") == "OVERDUE", snap
    assert snap.get("product_version") in (None, "", "NONE"), snap


def test_UC_051_S03a_발주기관_공백_보고(target, s0):
    """S1: 발주기관 보고 / 공백 보고 → 거절 (AC-051-3). TD-RR-1 흐름을 보호하려고 다른 요청(지표)에 시도한다."""
    rid = s0.ids["RR-METRIC"]
    assert target.post(f"/api/review-requests/{rid}/report", json={"body": "x", "evidence": []}, headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 403
    assert target.post(f"/api/review-requests/{rid}/report", json={"body": "   ", "evidence": []}, headers=auth(s0.tokens["TD-ACC-V1"])).status_code in (400, 422)


def test_UC_051_S01_조치_뒤_보고(target, s0, screen):
    """S1 → S1r: 변경 내역(실적 40→85, 제출본 없음→v1, 지연→제출, #204 진행중→해결, 진척률 30→39), 보고문 저장, 미처리 1 (AC-051-1·2)."""
    s0.s1r()
    det = _detail(target, s0, s0.ids["TD-RR-1"])
    changes = {c["field"]: (c["before"], c["after"]) for c in det["changes"]}
    problems: list[str] = []
    if det["status"] != "REPORTED" or det["reportBody"] != d.REVIEW_REQUEST_TD_RR_1["report"]:
        problems.append(f"상태·보고문 {det['status']} {det['reportBody']}")
    if "actual" not in changes or _ratio(changes["actual"][0]) != 0.4 or _ratio(changes["actual"][1]) != 0.85:
        problems.append(f"실적 변경 {changes.get('actual')}")
    if "product_version" not in changes and "submission" not in changes:
        problems.append(f"제출본 없음 → v1 변경이 없다: {sorted(changes)}")
    if "file_check" not in changes:
        problems.append("판정 지연 → 제출 변경이 없다")
    if not any("204" in str(v) for v in changes.values()):
        problems.append("#204 진행중 → 해결 변경이 없다")
    if not any("progress" in k.lower() or "representative" in k.lower() for k in changes):
        problems.append("보고 진척률 30.0 → 39.0 변경이 없다")
    if _pending(target, s0) != int(s0.ids["PENDING-BASE"]) + 1:
        problems.append(f"미처리 {_pending(target, s0)} (기대 기준+1, 조치보고도 미처리)")
    c1n = _get(target, s0, "/api/notifications", acc="TD-ACC-C1")
    s0.ids["N-C1-AFTER-REPORT"] = str([i["kind"] for i in c1n["items"]]) + f"|{c1n['unread']}"
    assert not problems, problems
    _ui_UC_051_S01(screen, s0)


def test_UC_053_S02_알림_흐름(target, s0):
    """V1 미읽음 1(요청) → 열면 0, 보고 뒤 C1 미읽음 1(보고), C1 자기 요청 알림 없음 (AC-053-2·3)."""
    problems: list[str] = []
    if "REVIEW_REQUESTED" not in s0.ids["N-V1-AFTER-REQ"] or s0.ids["N-V1-AFTER-REQ"].endswith("|0"):
        problems.append(f"요청 뒤 V1 알림 {s0.ids['N-V1-AFTER-REQ']}")
    if s0.ids["N-C1-AFTER-REQ"] != "[]":
        problems.append(f"C1 에게 자기 요청 알림이 갔다: {s0.ids['N-C1-AFTER-REQ']}")
    if s0.ids["N-V1-AFTER-SEEN"] != "0":
        problems.append(f"읽음 뒤 V1 미읽음 {s0.ids['N-V1-AFTER-SEEN']}")
    if "REVIEW_REPORTED" not in s0.ids["N-C1-AFTER-REPORT"] or s0.ids["N-C1-AFTER-REPORT"].endswith("|0"):
        problems.append(f"보고 뒤 C1 알림 {s0.ids['N-C1-AFTER-REPORT']}")
    assert not problems, problems


# ------------------------------------------------------------------ UC-052 (S1r)


def test_UC_052_S03_권한(target, s0):
    """S1r: V1·A1 확인·재요청 → 거절 (AC-052-1)."""
    rid = s0.ids["TD-RR-1"]
    for acc in ("TD-ACC-V1", "TD-ACC-A1"):
        assert target.post(f"/api/review-requests/{rid}/confirm", json={"acknowledgeCompletion": False, "note": ""}, headers=auth(s0.tokens[acc])).status_code == 403, acc
        assert target.post(f"/api/review-requests/{rid}/rerequest", json={"body": "다시"}, headers=auth(s0.tokens[acc])).status_code == 403, acc


def test_UC_052_S02_재요청(target, s0):
    """C1 재요청(사유 필수) → 상태 요청, 횟수 1, 최초 시점 상태 보존 (AC-052-3)."""
    rid = s0.ids["TD-RR-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    assert target.post(f"/api/review-requests/{rid}/rerequest", json={"body": ""}, headers=c1).status_code in (400, 422)
    res = target.post(f"/api/review-requests/{rid}/rerequest", json={"body": "규격 협의 결과 문서를 첨부해 주세요"}, headers=c1)
    assert res.status_code == 200, res.text
    det = res.json()
    assert det["status"] == "REQUESTED" and det["rerequestCount"] == 1, det
    assert _ratio(det["events"][0]["snapshot"].get("actual")) == 0.4  # 최초 요청 시점 상태는 이력에 보존
    assert [e["kind"] for e in det["events"]] == ["REQUESTED", "REPORTED", "REREQUESTED"], [e["kind"] for e in det["events"]]
    assert _pending(target, s0) == int(s0.ids["PENDING-BASE"]) + 1


def test_UC_051_S04_재요청_뒤_재보고(target, s0):
    """재보고 → 이전 보고 이력, 최초 대비·재요청 대비 변화 (AC-051-4)."""
    rid = s0.ids["TD-RR-1"]
    res = target.post(f"/api/review-requests/{rid}/report", json={"body": "규격 협의록 첨부", "evidence": [{"kind": "WORK_PRODUCT", "ref": "", "note": "", "workProductId": s0.ids["TD-DOC-3:wp"]}]}, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code == 200, res.text
    det = res.json()
    kinds = [e["kind"] for e in det["events"]]
    assert kinds == ["REQUESTED", "REPORTED", "REREQUESTED", "REPORTED"], kinds
    assert det["events"][1]["body"] == d.REVIEW_REQUEST_TD_RR_1["report"]  # 이전 보고 이력
    assert _ratio(det["events"][0]["snapshot"].get("actual")) == 0.4 and _ratio(det["currentState"].get("actual")) == 0.85


def test_UC_052_S01_확인완료(target, s0, screen):
    """확인완료 → 확인자 김주무관, 미처리 1 → 0 (AC-052-2)."""
    rid = s0.ids["TD-RR-1"]
    base = int(s0.ids["PENDING-BASE"])
    assert _pending(target, s0) == base + 1
    res = target.post(f"/api/review-requests/{rid}/confirm", json={"acknowledgeCompletion": False, "note": "확인했습니다"}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text
    det = res.json()
    assert det["status"] == "CONFIRMED" and det["confirmedByName"] == d.ACCOUNTS["TD-ACC-C1"].display, det
    assert _pending(target, s0) == base
    assert _ratio(det["events"][0]["snapshot"].get("actual")) == 0.4  # 확인 뒤 상태는 바뀌지 않는다
    _ui_UC_052_S01(screen, s0)


def test_UC_052_S04_중복(target, s0):
    """확인 2회 → 둘째 「이미 처리됨」 (AC-052-4)."""
    res = target.post(f"/api/review-requests/{s0.ids['TD-RR-1']}/confirm", json={"acknowledgeCompletion": False, "note": ""}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 409, res.text


def test_UC_051_S03b_확인완료_뒤_보고(target, s0):
    """확인완료 뒤 보고 → 거절 (AC-051-3)."""
    res = target.post(f"/api/review-requests/{s0.ids['TD-RR-1']}/report", json={"body": "늦은 보고", "evidence": []}, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code in (400, 409), res.text


def test_UC_052_S05_전체_주기(target, s0):
    """요청→보고→재요청→재보고→확인 이력 5건 순서대로, 미처리 1→1→1→1→0 (AC-052-2·3)."""
    det = _detail(target, s0, s0.ids["TD-RR-1"])
    kinds = [e["kind"] for e in det["events"]]
    assert kinds == ["REQUESTED", "REPORTED", "REREQUESTED", "REPORTED", "CONFIRMED"], kinds
    assert det["rerequestCount"] == 1 and det["status"] == "CONFIRMED"
    assert _pending(target, s0) == int(s0.ids["PENDING-BASE"])


# ------------------------------------------------------------------ 주기 뒤: 추가 변경·활동 기록


def test_UC_051_S02_보고_뒤_추가_변경(target, s0, replay):
    """S1r 에서 실적 95% 로 갱신·수집 → 보고에 붙은 내역은 85%, 지금 상태는 95% (AC-051-2)."""
    leaves = [list(r) for r in files.WBS_LEAVES_S0]
    leaves[1][7] = 0.95
    header, rows = files._wbs_rows(leaves)
    path = s0.files["TD-DOC-6"].parent / "WBS-95.xlsx"
    files._xlsx(path, "WBS", header, rows)
    s0.files["TD-WBS-95"] = path
    replay.faults = Faults(wbs_variant="TD-WBS-95", wbs_sha="95959595" + "0" * 32)
    job = target.post(f"/api/connections/{s0.ids['TD-CON-1']}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"])).json()
    assert job["status"] == "SUCCEEDED", job
    det = _detail(target, s0, s0.ids["TD-RR-1"])
    reported = next(e for e in det["events"] if e["kind"] == "REPORTED")
    assert _ratio(reported["snapshot"].get("actual")) == 0.85, reported["snapshot"]
    assert _ratio(det["currentState"].get("actual")) == 0.95, det["currentState"]
    # S1 내용으로 되돌린다(같은 blob, 그 판을 되살린다. DEF-V033)
    replay.faults = restore_faults("S1")
    target.post(f"/api/connections/{s0.ids['TD-CON-1']}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens["TD-ACC-V1"]))



# ------------------------------------------------------------------ UC-053


def test_UC_053_S03_활동_기록(target, s0):
    """요청·업로드·제출·수집·스냅샷·보고가 시간순으로 남고 V3 에게는 안 보인다 (AC-053-4)."""
    pid = s0.ids["TD-PRJ-1"]
    page = _get(target, s0, f"/api/projects/{pid}/activity?size=200")
    items = page["content"]
    kinds = {i["kind"] for i in items}
    problems: list[str] = []
    for want in ("REVIEW_REQUESTED", "REVIEW_REPORTED", "REVIEW_CONFIRMED"):
        if want not in kinds:
            problems.append(f"활동 기록에 {want} 없음")
    if not any("DOCUMENT" in k or "UPLOAD" in k for k in kinds):
        problems.append("문서 업로드 기록 없음")
    if not any("SNAPSHOT" in k for k in kinds):
        problems.append("스냅샷 기록 없음")
    if not any("SYNC" in k for k in kinds):
        problems.append("수집 기록 없음")
    stamps = [i["occurredAt"] for i in items]
    if stamps != sorted(stamps) and stamps != sorted(stamps, reverse=True):
        problems.append("시간순이 아니다")
    res = target.get(f"/api/projects/{pid}/activity?size=10", headers=auth(s0.tokens["TD-ACC-V3"]))
    if res.status_code not in (403, 404):
        problems.append(f"배정 없는 V3 에게 활동 기록이 보인다: {res.status_code}")
    assert not problems, problems


@pytest.mark.skip(reason="목록·현황 머리줄의 미처리 건수 표시는 브라우저 시나리오. API 건수는 UC-050-S01 에서 확인")
def test_UC_053_S01_미처리_건수(target, s0):
    """0 → 1, 요청 목록으로 이동 (AC-053-1)."""


@pytest.mark.skip(reason="DEC-08(알림 범위·내 차례 건수) 결정 전")
def test_UC_053_S04_내_차례(target, s0):
    """역할별 내 차례 건수 (AC-053-5)."""


@pytest.mark.skip(reason="원천 비교는 5174 실연동에서 본다. 정적 검사는 UC-050-S05")
def test_UC_051_S05_원천_무기록(target, s0):
    """보고가 원천에 기록을 남기지 않는다 (AC-051-5)."""


def _ui_UC_051_S01(screen, s0):
    """화면: 용역사 요청 상세에 요청 시점과 지금이 나란히, 바뀐 줄 구분, 보고문."""
    if not screen:
        return
    sc = screen("TD-ACC-V1")
    sc.open(f"/p/{s0.ids['TD-PRJ-1']}/reviews?open={s0.ids['TD-RR-1']}")
    dlg = "[role=dialog]"
    sc.see("요청 시점과 지금", "조치 보고", d.REVIEW_REQUEST_TD_RR_1["report"], selector=dlg)
    sc.see(re.compile(r"요청 이후 \d+개 값이 바뀌었습니다"), selector=dlg)
    changed = sc.page.locator(f"{dlg} tbody tr[class*=bg-warning]")
    assert changed.count() >= 4, f"바뀐 줄 {changed.count()} (기대 4 이상)"
    body = sc.text(dlg)
    for want in ("40", "85", "39.0"):
        assert want in body, f"요청 상세에 {want} 가 없다"
    sc.done()


def _ui_UC_052_S01(screen, s0):
    """화면: 요청 상세 「확인완료」·확인자, 현황 머리줄 미처리 건수가 기준으로 돌아옴."""
    if not screen:
        return
    pid = s0.ids["TD-PRJ-1"]
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/reviews?open={s0.ids['TD-RR-1']}")
    sc.see("확인완료", d.ACCOUNTS["TD-ACC-C1"].display, selector="[role=dialog]")
    sc.shot("상세")
    sc.open(f"/p/{pid}/dashboard").see(f"미처리 확인 요청 {int(s0.ids['PENDING-BASE'])}건")
    sc.done()
