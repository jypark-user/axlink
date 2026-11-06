# ruff: noqa: E501
"""D 그룹: WBS·산출물·완료 확인 (UC-030 ~ UC-033) 예제 시나리오.

한 S0 위에서 순서대로 돈다. 앞부분은 S0 그대로의 WBS 인식·지연 판정을 보고, UC-031-S01 이
S0a(SW설계서 v1 제출)를 만들어 승인까지 간다. 그 뒤 UC-032 가 3.2 완료 확인·철회를 보고,
WBS 변형(합≠1·머리글 없음·v2·L2·산출물 열 변경)은 저장소 파일을 바꿔 재수집한 뒤 원래 파일로
되돌린다. DEC-04·10·12 에 걸린 시나리오는 보류한다.
"""

from __future__ import annotations

import pytest

from app.db import fetch_all, tx
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import files
from tests.fixtures.im009.replay import Faults, ReplaySource, install, restore_faults, tool_base
from tests.scenarios.conftest import auth

pytestmark = pytest.mark.db

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
T0 = d.T0.isoformat()


@pytest.fixture
def replay(monkeypatch, s0) -> ReplaySource:
    # 앞 시험이 복원한 WBS 를 이어 쓴다. 옛 파일을 다시 내면 DEF-V033 을 밟는다
    return install(
        monkeypatch,
        ReplaySource(state="S0", files=s0.files, wbs_current=s0.ids.get("WBS-CURRENT")),
    )


def _wbs(target, s0, prj="TD-PRJ-1", acc="TD-ACC-C1", at=T0) -> dict:
    res = target.get(f"/api/projects/{s0.ids[prj]}/wbs?at={at}", headers=auth(s0.tokens[acc]))
    assert res.status_code == 200, res.text
    return res.json()


def _progress(target, s0, prj="TD-PRJ-1") -> dict:
    return target.get(f"/api/projects/{s0.ids[prj]}/progress?at={T0}", headers=auth(s0.tokens["TD-ACC-C1"])).json()


def _completion(target, s0, prj="TD-PRJ-1") -> dict:
    return target.get(f"/api/projects/{s0.ids[prj]}/wbs/completion?at={T0}", headers=auth(s0.tokens["TD-ACC-C1"])).json()


def _deliverables(target, s0, prj="TD-PRJ-1") -> dict:
    return target.get(f"/api/projects/{s0.ids[prj]}/wbs/deliverables?at={T0}", headers=auth(s0.tokens["TD-ACC-C1"])).json()


def _checklist(target, s0, prj="TD-PRJ-1", acc="TD-ACC-C1") -> dict[str, dict]:
    res = target.get(f"/api/projects/{s0.ids[prj]}/work-products", headers=auth(s0.tokens[acc])).json()
    return {i["type"]: i for i in res["items"]}


def _sync(target, s0, con="TD-CON-1", acc="TD-ACC-V1") -> dict:
    job = target.post(f"/api/connections/{s0.ids[con]}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens[acc])).json()
    assert job["status"] == "SUCCEEDED", job
    return job


def _upload(target, s0, prj: str, path, name: str, mime: str, acc="TD-ACC-V1", wbs_id: str | None = None) -> str:
    with open(path, "rb") as f:
        res = target.post(
            f"/api/projects/{s0.ids[prj]}/documents", files={"file": (name, f, mime)},
            data={"wbsId": wbs_id} if wbs_id else {}, headers=auth(s0.tokens[acc]),
        )
    assert res.status_code in (200, 201, 202), res.text
    s0.await_document(acc, res.json()["id"])  # 원격 서버는 뒤에서 처리한다
    return res.json()["id"]


def _confirm(target, s0, doc_id: str, type_code: str, title: str, version: str, acc="TD-ACC-V1", status="SUBMITTED"):
    return target.post(f"/api/documents/{doc_id}/draft/confirm", json={
        "type": type_code, "title": title, "version": version, "requirements": [], "workProductStatus": status,
    }, headers=auth(s0.tokens[acc]))


def _fresh_docx(s0, name: str, marker: str):
    """내용이 다른 DOCX 를 즉석에서 만든다. 같은 내용은 같은 문서로 합쳐지므로 판본마다 다르게."""
    from docx import Document

    path = s0.files["TD-DOC-3"].parent / name
    doc = Document()
    doc.add_heading(f"SW설계서 {marker}", level=1)
    doc.add_paragraph(f"이 판본은 {marker} 이다. 외부 연계 규격은 2026-08-25 협의를 마쳤다.")
    doc.save(path)
    return path


def _completion_cycle(target, s0, wbs_id: str, scope: str, wp_id: str) -> str:
    pid = s0.ids["TD-PRJ-1"]
    req = target.post(f"/api/projects/{pid}/review-requests", json={
        "targetType": "WBS_ITEM", "targetKey": wbs_id, "title": f"{wbs_id} 완료 확인", "body": "",
        "purpose": "WBS_COMPLETION", "completionScope": scope,
    }, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    rep = target.post(f"/api/review-requests/{rid}/report", json={
        "body": "제출본 근거", "evidence": [{"kind": "WORK_PRODUCT", "ref": "", "note": "", "workProductId": wp_id}],
    }, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert rep.status_code == 200, rep.text
    con = target.post(f"/api/review-requests/{rid}/confirm", json={"acknowledgeCompletion": True, "note": "확인"}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert con.status_code == 200, con.text
    return rid


def _restore_wbs(target, s0, replay) -> None:
    """변형 뒤 S0 내용으로 되돌린다. 새 커밋 해시로 내 DEF-V033 을 밟지 않는다."""
    f = restore_faults("S0")
    s0.ids["WBS-CURRENT"] = (f.wbs_variant, f.wbs_sha)
    replay.wbs_current = s0.ids["WBS-CURRENT"]
    replay.faults = Faults()
    _sync(target, s0)


# ------------------------------------------------------------------ UC-030


def test_UC_030_S01_저장소_WBS_인식(target, s0):
    """말단 5, 합 1.00, 산출물 미지정 0, 경고 0, 3.3 계획선(T0) 77.9% (AC-030-1·2·4·6)."""
    w = _wbs(target, s0)
    assert w["source"] == "WBS_FILE", w["source"]
    leaves = [i for i in w["items"] if i["weight"] and i["level"] > 0]
    assert [i["wbsId"] for i in leaves] == ["3.1", "3.2", "3.3", "3.4", "3.5"], [i["wbsId"] for i in leaves]
    assert round(sum(i["weight"] for i in leaves), 4) == 1.0
    by = {i["wbsId"]: i for i in leaves}
    assert by["3.2"]["name"] == "설계" and by["3.2"]["deliverable"] == "SW설계서"
    assert by["3.2"]["startDate"] == "2026-04-16" and by["3.2"]["endDate"] == "2026-07-31"
    assert by["3.2"]["progress"] == 40 and by["3.1"]["progress"] == 100
    assert by["3.3"]["planned"] == 78, by["3.3"]["planned"]  # 0.7794 → 78
    assert w["warnings"] == [], w["warnings"]
    assert all(i["deliverable"] for i in leaves)
    prog = _progress(target, s0)
    assert prog["wbsDeclaredPlanned"] is not None  # 파일 계획 열은 참고값으로 따로


def test_UC_030_S02_업로드_계획서(target, s0):
    """TD-PRJ-9 에 TD-DOC-6 올려 「사업수행계획서」 확정 → 같은 인식 결과, L1 (AC-030-1)."""
    doc = _upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-6"], "WBS.xlsx", XLSX)
    res = _confirm(target, s0, doc, "PROJECT_PLAN", "사업수행계획서", "v1")
    assert res.status_code == 200, res.text
    w = _wbs(target, s0, "TD-PRJ-9")
    leaves = [i for i in w["items"] if i["weight"] and i["level"] > 0]
    assert w["source"] == "WBS_FILE" and len(leaves) == 5, (w["source"], w["warnings"], len(leaves))
    assert _progress(target, s0, "TD-PRJ-9")["level"] == "L1"


def test_UC_030_S08_편집_시도(target, s0):
    """실적 수정 API 호출 → 없음(거절) (AC-030-7)."""
    pid = s0.ids["TD-PRJ-1"]
    h = auth(s0.tokens["TD-ACC-C1"])
    for method, path in (("PATCH", f"/api/projects/{pid}/wbs/items/3.2"), ("PUT", f"/api/projects/{pid}/wbs/3.2"), ("PATCH", f"/api/projects/{pid}/wbs")):
        res = target.request(method, path, json={"progress": 90}, headers=h)
        assert res.status_code in (403, 404, 405), (method, path, res.status_code)
    assert next(i for i in _wbs(target, s0)["items"] if i["wbsId"] == "3.2")["progress"] == 40


def test_UC_030_S10_WBS_없음(target, s0):
    """PRJ-3: 원천 없음·고지 / PRJ-2: 원천 Redmine (AC-030-1, E3)."""
    w3 = _wbs(target, s0, "TD-PRJ-3")
    assert w3["source"] == "NONE" and w3["items"] == [] and w3["notice"], w3
    w2 = _wbs(target, s0, "TD-PRJ-2", acc="TD-ACC-C2")
    assert w2["source"] == "REDMINE", w2["source"]
    assert len(w2["items"]) >= 6, len(w2["items"])


@pytest.mark.skip(reason="DEC-04(WBS 인식 결과 확인 단계) 결정 전")
def test_UC_030_S07_확인_다시_지정(target, s0):
    """인식 결과에서 확인 / 다시 지정 (A1)."""


# ------------------------------------------------------------------ UC-031 (S0 → S0a → 승인)


def test_UC_031_S07_지연_판정(target, s0):
    """S0, T0: 3.2 는 지연(종료 07-31 < T0, 미제출) (AC-031-3, IM-009 7.2)."""
    items = {i["wbsId"]: i for i in _deliverables(target, s0)["items"]}
    assert items["3.2"]["status"] == "OVERDUE", items["3.2"]
    assert items["3.1"]["status"] == "SUBMITTED", items["3.1"]
    assert {items[k]["status"] for k in ("3.3", "3.4", "3.5")} <= {"MISSING", "NONE"}, [items[k]["status"] for k in ("3.3", "3.4", "3.5")]


def test_UC_031_S01_올려_제출하고_승인(target, s0):
    """TD-DOC-3 업로드(3.2) → SW설계서 제출(S0a) → C1 승인. 판정 제출(연결 문서), 승인자, 지표 불변 (AC-031-1·3·4·6)."""
    before = (_progress(target, s0)["representative"], _completion(target, s0)["completionRate"])
    s0.s0a()
    check = _checklist(target, s0)
    assert check["SOFTWARE_DESIGN"]["status"] == "SUBMITTED" and check["SOFTWARE_DESIGN"]["version"] == "v1", check["SOFTWARE_DESIGN"]
    items = {i["wbsId"]: i for i in _deliverables(target, s0)["items"]}
    assert items["3.2"]["status"] == "SUBMITTED", items["3.2"]
    assert items["3.2"]["rule"] in ("LINKED_DOC", "LINKED", "PRODUCT_TYPE", "FILE_NAME"), items["3.2"]
    wp = s0.ids["TD-DOC-3:wp"]
    res = target.post(f"/api/projects/{s0.ids['TD-PRJ-1']}/work-products/{wp}/approve", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 204, res.text
    check = _checklist(target, s0)
    assert check["SOFTWARE_DESIGN"]["status"] == "APPROVED"
    assert check["SOFTWARE_DESIGN"]["approvedBy"] and d.ACCOUNTS["TD-ACC-C1"].display in str(check["SOFTWARE_DESIGN"]["approvedBy"])
    after = (_progress(target, s0)["representative"], _completion(target, s0)["completionRate"])
    assert after == before, (before, after)
    assert round(after[0], 4) == 0.3 and round(after[1], 4) == 0.15


def test_UC_031_S11_승인_중복(target, s0):
    """승인 2회 → 둘째 「이미 승인됨」 (COMMON-S04)."""
    res = target.post(f"/api/projects/{s0.ids['TD-PRJ-1']}/work-products/{s0.ids['TD-DOC-3:wp']}/approve", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 409, res.text


def test_UC_031_S08_같은_버전_재제출(target, s0):
    """승인된 v1 로 다시 제출 → 거절 「승인된 버전」 (AC-031-8)."""
    # 같은 내용은 같은 문서로 합쳐지므로(중복 제거) 다른 내용의 파일을 v1 로 다시 제출한다
    doc = _upload(target, s0, "TD-PRJ-1", _fresh_docx(s0, "SW설계서_v1-재제출.docx", "v1 재제출"), "SW설계서_v1-재제출.docx", DOCX)
    res = _confirm(target, s0, doc, "SOFTWARE_DESIGN", "SW설계서", "v1")
    assert res.status_code == 409, res.text
    assert "승인" in res.text


def test_UC_031_S05_거절들(target, s0):
    """용역사 승인 / 빈 사유 반려 → 거절 (AC-031-4). 지난 버전 승인은 S04 뒤 본다."""
    wp = s0.ids["TD-DOC-3:wp"]
    pid = s0.ids["TD-PRJ-1"]
    assert target.post(f"/api/projects/{pid}/work-products/{wp}/approve", headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403
    assert target.post(f"/api/projects/{pid}/work-products/{wp}/reject", json={"reason": ""}, headers=auth(s0.tokens["TD-ACC-C1"])).status_code in (400, 422)
    assert target.post(f"/api/projects/{pid}/work-products/{wp}/reject", json={"reason": "x"}, headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403


def test_UC_031_S09_지표_독립(target, s0):
    """승인 전후 보고 진척률 30.0%·완료 확인율 15.0% (AC-031-6, CC-09). S01 에서 비교한 값을 다시 확인."""
    assert round(_progress(target, s0)["representative"], 4) == 0.3
    assert round(_completion(target, s0)["completionRate"], 4) == 0.15


# ------------------------------------------------------------------ UC-032 (S0a + 승인 상태)


def test_UC_032_S03_권한(target, s0):
    """요청·확인·철회는 발주기관만, 보고는 용역사만 (AC-032-1)."""
    pid = s0.ids["TD-PRJ-1"]
    body = {"targetType": "WBS_ITEM", "targetKey": "3.3", "title": "x", "body": "", "purpose": "WBS_COMPLETION", "completionScope": "범위"}
    assert target.post(f"/api/projects/{pid}/review-requests", json=body, headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403
    assert target.post(f"/api/projects/{pid}/review-requests", json=body, headers=auth(s0.tokens["TD-ACC-A1"])).status_code == 403
    # 보고는 용역사만: C1 이 보고 시도
    rid = s0.ids["TD-RR-31"]
    assert target.post(f"/api/review-requests/{rid}/report", json={"body": "x", "evidence": []}, headers=auth(s0.tokens["TD-ACC-C1"])).status_code in (403, 409)


def test_UC_032_S01_요청_보고_확인(target, s0):
    """3.2 요청 → V1 보고(근거 SW설계서 v1) → C1 확인. 완료 확인율 15.0% → 35.0%, 진척률 30.0% 불변 (AC-032-3)."""
    assert round(_completion(target, s0)["completionRate"], 4) == 0.15
    rid = _completion_cycle(target, s0, "3.2", "설계서 v1 제출·승인", s0.ids["TD-DOC-3:wp"])
    s0.ids["TD-RR-32"] = rid
    c = _completion(target, s0)
    assert round(c["completionRate"], 4) == 0.35, c["completionRate"]
    assert round(_progress(target, s0)["representative"], 4) == 0.3
    item = next(i for i in c["items"] if i["wbsId"] == "3.2")
    assert item["completionStatus"] == "CONFIRMED" and item["confirmedBy"] == d.ACCOUNTS["TD-ACC-C1"].display


def test_UC_032_S04_중복_이미_확인(target, s0):
    """확인된 3.2 재요청 → 거절 (AC-032-2). 열린 요청 중복은 S06 흐름에서 본다."""
    pid = s0.ids["TD-PRJ-1"]
    res = target.post(f"/api/projects/{pid}/review-requests", json={
        "targetType": "WBS_ITEM", "targetKey": "3.2", "title": "다시", "body": "", "purpose": "WBS_COMPLETION", "completionScope": "설계서 v1 제출·승인",
    }, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 409, res.text


def test_UC_032_S08_근거_고정(target, s0):
    """확인 뒤 SW설계서 v2 제출 → 요청 상세의 근거는 v1·제출 상태 그대로 (AC-032-8)."""
    doc = _upload(target, s0, "TD-PRJ-1", _fresh_docx(s0, "SW설계서_v2.docx", "v2"), "SW설계서_v2.docx", DOCX)
    assert _confirm(target, s0, doc, "SOFTWARE_DESIGN", "SW설계서", "v2").status_code == 200
    detail = target.get(f"/api/review-requests/{s0.ids['TD-RR-32']}", headers=auth(s0.tokens["TD-ACC-C1"])).json()
    recs = detail["completionRecords"]
    assert recs and str(recs[-1]["evidence"]).find("v1") >= 0, recs
    assert "v2" not in str(recs[-1]["evidence"])
    assert _checklist(target, s0)["SOFTWARE_DESIGN"]["version"] == "v2"


def test_UC_032_S02_철회_재확인(target, s0):
    """철회 → 15.0% → 새 요청·보고·확인 → 35.0%, 기록 3줄 (AC-032-4)."""
    res = target.post(f"/api/review-requests/{s0.ids['TD-RR-32']}/withdraw-completion", json={"reason": "근거 재검토"}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text
    assert round(_completion(target, s0)["completionRate"], 4) == 0.15
    rid2 = _completion_cycle(target, s0, "3.2", "설계서 v2 제출", s0.ids["TD-DOC-3:wp"])
    assert round(_completion(target, s0)["completionRate"], 4) == 0.35
    detail = target.get(f"/api/review-requests/{rid2}", headers=auth(s0.tokens["TD-ACC-C1"])).json()
    # 철회 기록은 첫 요청에, 재확인은 새 요청에 붙는다. 작업 기준으로 이어 본다
    first = target.get(f"/api/review-requests/{s0.ids['TD-RR-32']}", headers=auth(s0.tokens["TD-ACC-C1"])).json()
    recs = {r["id"]: r for r in first["completionRecords"] + detail["completionRecords"]}.values()
    kinds = [r["kind"] for r in sorted(recs, key=lambda r: r["decidedAt"])]
    assert kinds[-3:] == ["CONFIRMED", "WITHDRAWN", "CONFIRMED"], kinds


def test_UC_032_S09_WBS_없음(target, s0):
    """TD-PRJ-3 완료 요청 → 거절, 완료 확인율 「산출 불가」 (E1)."""
    pid = s0.ids["TD-PRJ-3"]
    res = target.post(f"/api/projects/{pid}/review-requests", json={
        "targetType": "WBS_ITEM", "targetKey": "3.1", "title": "x", "body": "", "purpose": "WBS_COMPLETION", "completionScope": "x",
    }, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 400, res.text
    assert _completion(target, s0, "TD-PRJ-3")["completionRate"] is None


# ------------------------------------------------------------------ UC-031 S04 (반려 뒤 재제출)


def test_UC_031_S04_반려_뒤_재제출_이력(target, s0):
    """v2 반려 「목차 누락」 → v3 제출 → 점검표에 현행 v3, 이력에 v2·사유 (AC-031-4·5)."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    current = _checklist(target, s0)["SOFTWARE_DESIGN"]
    assert current["version"] == "v2" and current["status"] == "SUBMITTED"
    res = target.post(f"/api/projects/{pid}/work-products/{current['id']}/reject", json={"reason": "목차 누락"}, headers=c1)
    assert res.status_code == 204, res.text
    doc = _upload(target, s0, "TD-PRJ-1", _fresh_docx(s0, "SW설계서_v3.docx", "v3"), "SW설계서_v3.docx", DOCX)
    assert _confirm(target, s0, doc, "SOFTWARE_DESIGN", "SW설계서", "v3").status_code == 200
    now = _checklist(target, s0)["SOFTWARE_DESIGN"]
    assert now["version"] == "v3" and now["status"] == "SUBMITTED"
    with tx() as cur:
        rows = fetch_all(cur, "select version, status, is_current from work_product where project_id = %s and type = 'SOFTWARE_DESIGN' order by created_at", (pid,))
    hist = {r["version"]: (r["status"], r["is_current"]) for r in rows}
    assert hist["v2"] == ("REJECTED", False) and hist["v3"] == ("SUBMITTED", True), hist
    # 지난 버전과 반려 사유가 점검표 응답에 보여야 한다(AC-031-5)
    assert any(k in now for k in ("versions", "history", "previousVersions")), f"점검표 응답에 지난 버전·반려 사유가 없다: {sorted(now)}"


def test_UC_031_S05b_지난_버전_승인(target, s0):
    """반려된 v2(지난 버전) 승인 → 거절 (AC-031-4)."""
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        rows = fetch_all(cur, "select id::text as id from work_product where project_id = %s and type = 'SOFTWARE_DESIGN' and version = 'v2'", (pid,))
    res = target.post(f"/api/projects/{pid}/work-products/{rows[0]['id']}/approve", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 409, res.text


# ------------------------------------------------------------------ UC-031 S06 (WBS 없는 사업)


def test_UC_031_S06_WBS_없는_사업(target, s0):
    """TD-PRJ-3: 점검표 제출·승인 동작, 작업별 판정 「할 수 없음」 (AC-031-7)."""
    doc = _upload(target, s0, "TD-PRJ-3", s0.files["TD-DOC-2"], "요구사항정의서.docx", DOCX, acc="TD-ACC-C1")
    res = _confirm(target, s0, doc, "REQUIREMENTS_SPEC", "요구사항정의서", "v1", acc="TD-ACC-C1")
    assert res.status_code == 200, res.text
    wp = res.json()["workProductId"]
    assert target.post(f"/api/projects/{s0.ids['TD-PRJ-3']}/work-products/{wp}/approve", headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 204
    assert _checklist(target, s0, "TD-PRJ-3")["REQUIREMENTS_SPEC"]["status"] == "APPROVED"
    deliv = _deliverables(target, s0, "TD-PRJ-3")
    assert deliv["items"] == [], deliv["items"]


# ------------------------------------------------------------------ WBS 변형 (저장소 파일 교체 → 재수집 → 복원)


def test_UC_031_S03_설정_경로_아닌_커밋(target, s0, replay):
    """docs/misc/SW설계서.docx 커밋 → 제출본 없음, 판정 「제출(파일 이름)」 (AC-031-2·3)."""
    before = {k: v["version"] for k, v in _checklist(target, s0).items() if v["status"] not in ("NONE", None)}
    replay.faults = Faults(extra_tree_paths=["docs/misc/SW설계서.docx"])
    _sync(target, s0)
    items = {i["wbsId"]: i for i in _deliverables(target, s0)["items"]}
    # 3.2 는 이미 연결 문서(v3)가 있어 그 근거가 앞선다. 파일 이름 근거는 3.4(시험결과서) 같은 빈 작업에서 본다
    assert items["3.2"]["status"] == "SUBMITTED"
    after = {k: v["version"] for k, v in _checklist(target, s0).items() if v["status"] not in ("NONE", None)}
    assert after == before, (before, after)  # 설정 경로가 아니라 제출본이 생기지 않는다
    _restore_wbs(target, s0, replay)


def test_UC_031_S02_설정_경로_커밋(target, s0, replay, monkeypatch):
    """설정 경로에 설계서 파일 커밋 → 수집 → 제출본 생성(버전 = 해시), 판정 「제출(저장소 경로)」 (AC-031-2)."""
    from app.config import settings

    monkeypatch.setattr(settings, "collect_files", "docs/00-management/WBS.xlsx=PROJECT_PLAN,docs/20-design/SW설계서_v0.9.docx=SOFTWARE_DESIGN")
    replay.faults = Faults(serve_design_file=True, extra_tree_paths=["docs/20-design/SW설계서_v0.9.docx"])
    _sync(target, s0)
    with tx() as cur:
        rows = fetch_all(cur, "select version, status, source_kind, is_current from work_product where project_id = %s and type = 'SOFTWARE_DESIGN' order by created_at", (s0.ids["TD-PRJ-1"],))
    tool_rows = [r for r in rows if r["source_kind"] == "TOOL"]
    assert tool_rows and tool_rows[-1]["status"] == "SUBMITTED" and tool_rows[-1]["version"].startswith("d3d3d3d3"), rows
    _restore_wbs(target, s0, replay)


def test_UC_030_S03_합이_1이_아님(target, s0, replay):
    """합 1.10 변형 → 경고 「1.100」, 정규화 뒤 보고 진척률 27.3% (AC-030-3)."""
    replay.faults = Faults(wbs_variant="TD-WBS-SUM", wbs_sha="5a5a5a5a" + "0" * 32)
    _sync(target, s0)
    w = _wbs(target, s0)
    assert any("1.1" in x for x in w["warnings"]), w["warnings"]
    assert round(_progress(target, s0)["representative"], 4) == 0.2727, _progress(target, s0)["representative"]
    _restore_wbs(target, s0, replay)
    assert round(_progress(target, s0)["representative"], 4) == 0.3


def test_UC_030_S04_머리글_없음(target, s0, replay):
    """머리글 없는 변형 → 경고 「머리글」, 이전 5건 유지, 진척 30.0% 유지 (AC-030-3)."""
    replay.faults = Faults(wbs_variant="TD-WBS-NOHEAD", wbs_sha="4b4b4b4b" + "0" * 32)
    _sync(target, s0)
    w = _wbs(target, s0)
    prog = _progress(target, s0)
    try:
        assert any("머리글" in x for x in w["warnings"] + prog["warnings"]), (w["warnings"], prog["warnings"])
        assert len([i for i in w["items"] if i["weight"] and i["level"] > 0]) == 5, "이전 기준선 5건이 유지되지 않았다"
        assert prog["representative"] is not None and round(prog["representative"], 4) == 0.3, prog
    finally:
        _restore_wbs(target, s0, replay)


def test_UC_030_S06_가중치_없는_WBS_L2(target, s0, replay):
    """가중치 열 없음 → 기간 비례 가중치, 산출물 기준 실적, 「추정」 표시, 11.7% (A3, IM-009 7.1)."""
    replay.faults = Faults(wbs_variant="TD-WBS-L2", wbs_sha="2c2c2c2c" + "0" * 32)
    _sync(target, s0)
    prog = _progress(target, s0)
    try:
        assert prog["level"] in ("L2", "L1") and prog["representative"] is not None, prog
        assert round(prog["representative"], 4) == 0.1173, prog["representative"]
        assert "추정" in str(prog), "추정 표시가 없다"
    finally:
        _restore_wbs(target, s0, replay)


def test_UC_032_S05_계획서_교체_뒤(target, s0, replay):
    """3.2 산출물 열만 바꾼 변형 → 3.2 「다시 확인 필요」, 완료 확인율 15.0%(3.1 만) (AC-032-5)."""
    leaves = [list(r) for r in files.WBS_LEAVES_S0]
    leaves[1][2] = "상세설계서"
    header, rows = files._wbs_rows(leaves)
    path = s0.files["TD-DOC-6"].parent / "WBS-DELIV32.xlsx"
    files._xlsx(path, "WBS", header, rows)
    s0.files["TD-WBS-DELIV32"] = path
    replay.faults = Faults(wbs_variant="TD-WBS-DELIV32", wbs_sha="d32d32d3" + "0" * 32)
    _sync(target, s0)
    c = _completion(target, s0)
    try:
        item = next(i for i in c["items"] if i["wbsId"] == "3.2")
        assert item["completionStatus"] == "RECONFIRM", item
        assert round(c["completionRate"], 4) == 0.15, c["completionRate"]
    finally:
        _restore_wbs(target, s0, replay)


def test_UC_032_S06_요청_뒤_변경(target, s0, replay):
    """3.3 요청·보고 뒤 3.3 산출물 열 변경 → 확인 거절, 상태 조치보고 (AC-032-6)."""
    pid = s0.ids["TD-PRJ-1"]
    req = target.post(f"/api/projects/{pid}/review-requests", json={
        "targetType": "WBS_ITEM", "targetKey": "3.3", "title": "3.3 완료 확인", "body": "", "purpose": "WBS_COMPLETION", "completionScope": "구현 완료",
    }, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    assert target.post(f"/api/review-requests/{rid}/report", json={"body": "보고", "evidence": [{"kind": "OTHER", "ref": "x", "note": "", "workProductId": None}]}, headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 200
    leaves = [list(r) for r in files.WBS_LEAVES_S0]
    leaves[2][2] = "소스 목록"
    header, rows = files._wbs_rows(leaves)
    path = s0.files["TD-DOC-6"].parent / "WBS-DELIV33.xlsx"
    files._xlsx(path, "WBS", header, rows)
    s0.files["TD-WBS-DELIV33"] = path
    replay.faults = Faults(wbs_variant="TD-WBS-DELIV33", wbs_sha="d33d33d3" + "0" * 32)
    _sync(target, s0)
    try:
        res = target.post(f"/api/review-requests/{rid}/confirm", json={"acknowledgeCompletion": True, "note": ""}, headers=auth(s0.tokens["TD-ACC-C1"]))
        assert res.status_code == 409, res.text
        detail = target.get(f"/api/review-requests/{rid}", headers=auth(s0.tokens["TD-ACC-C1"])).json()
        assert detail["status"] == "REPORTED", detail["status"]
    finally:
        _restore_wbs(target, s0, replay)


def test_UC_030_S05_버전_교체_정체_승계(target, s0, replay):
    """3.4 를 3.4·3.5 로 쪼갠 v2 → 3.1 확인 기록 유지, 새 3.5·3.6 처리, 빠진 번호 비활성 (AC-030-5)."""
    replay.faults = Faults(wbs_variant="TD-WBS-V2", wbs_sha="e2e2e2e2" + "0" * 32)
    _sync(target, s0)
    w = _wbs(target, s0)
    c = _completion(target, s0)
    try:
        leaves = [i["wbsId"] for i in w["items"] if i["weight"] and i["level"] > 0]
        assert leaves == ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6"], leaves
        by = {i["wbsId"]: i for i in c["items"]}
        assert by["3.1"]["completionStatus"] == "CONFIRMED" and by["3.1"]["keyReason"] == "CONTINUED", by["3.1"]
        assert by["3.5"]["name"] == "인수시험" and by["3.5"]["completionStatus"] in ("NONE", "RECONFIRM"), by["3.5"]
        assert by["3.6"]["completionStatus"] == "NONE"
    finally:
        _restore_wbs(target, s0, replay)


# ------------------------------------------------------------------ TD-PRJ-9 (별도 WBS)


def test_UC_030_S09_산출물_열_누락(target, s0, replay):
    """TD-PRJ-9 에 TD-WBS-MISS → 「산출물 미지정 1(3.4)」, 3.4 판정 「해당 없음」 (AC-030-2·4)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    replay.faults = Faults(wbs_targets={"daon/prj9"}, wbs_variant="TD-WBS-MISS", wbs_sha="9999aaaa" + "0" * 32)
    made = target.post(f"/api/projects/{s0.ids['TD-PRJ-9']}/connections", json={
        "tool": "GITHUB", "name": "PRJ-9 저장소", "baseUrl": tool_base("GITHUB", "https://api.github.com"), "targetResource": "daon/prj9",
        "credential": {"accessToken": "ghp_prj9Token000000000000"},
    }, headers=v1)
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    s0.ids["CON-PRJ9"] = cid
    assert target.post(f"/api/connections/{cid}/test", headers=v1).status_code == 200
    job = target.post(f"/api/connections/{cid}/sync", json={"kind": "BACKFILL"}, headers=v1).json()
    assert job["status"] == "SUCCEEDED", job
    w = _wbs(target, s0, "TD-PRJ-9")
    leaves = {i["wbsId"]: i for i in w["items"] if i["weight"] and i["level"] > 0}
    assert len(leaves) == 5 and leaves["3.4"]["deliverable"] in (None, ""), leaves.get("3.4")
    assert w["deliverables"]["none"] == 1, w["deliverables"]
    items = {i["wbsId"]: i for i in _deliverables(target, s0, "TD-PRJ-9")["items"]}
    assert items["3.4"]["status"] == "NONE", items["3.4"]
    assert leaves["3.2"]["weight"] == 0.2 and leaves["3.2"]["progress"] == 40


def test_UC_032_S10_가중치_기준_확인(target, s0, replay):
    """TD-PRJ-9 에 TD-WBS-V2(말단 6) → 3.4(0.12) 만 확인 → 완료 확인율 12.0% (AC-032-3)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    cid = s0.ids["CON-PRJ9"]
    replay.faults = Faults(wbs_targets={"daon/prj9"}, wbs_variant="TD-WBS-V2", wbs_sha="e2e2e2e2" + "1" * 32)
    job = target.post(f"/api/connections/{cid}/sync", json={"kind": "BACKFILL"}, headers=v1).json()
    assert job["status"] == "SUCCEEDED", job
    assert len([i for i in _wbs(target, s0, "TD-PRJ-9")["items"] if i["weight"] and i["level"] > 0]) == 6
    pid = s0.ids["TD-PRJ-9"]
    doc = _upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-2"], "시험결과서.docx", DOCX, wbs_id="3.4")
    res = _confirm(target, s0, doc, "TEST_REPORT", "시험결과서", "v1")
    assert res.status_code == 200, res.text
    wp = res.json()["workProductId"]
    req = target.post(f"/api/projects/{pid}/review-requests", json={
        "targetType": "WBS_ITEM", "targetKey": "3.4", "title": "3.4 완료 확인", "body": "", "purpose": "WBS_COMPLETION", "completionScope": "시험 완료",
    }, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    assert target.post(f"/api/review-requests/{rid}/report", json={"body": "보고", "evidence": [{"kind": "WORK_PRODUCT", "ref": "", "note": "", "workProductId": wp}]}, headers=v1).status_code == 200
    assert target.post(f"/api/review-requests/{rid}/confirm", json={"acknowledgeCompletion": True, "note": ""}, headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 200
    c = _completion(target, s0, "TD-PRJ-9")
    assert round(c["completionRate"], 4) == 0.12, c["completionRate"]  # 개수 기준 1/6 = 0.1667 이 아니다


# ------------------------------------------------------------------ 보류


@pytest.mark.skip(reason="DEC-12(승인률 분모·분자) 결정 전")
def test_UC_031_S10_승인률(target, s0):
    """승인률 (AC-031-9)."""


@pytest.mark.skip(reason="기록 저장 실패 주입은 DB 장애 모의가 필요하다. 별도 자동 시험으로 설계")
def test_UC_032_S07_기록_실패_롤백(target, s0):
    """저장 실패 → 상태 불변 (AC-032-7)."""


@pytest.mark.skip(reason="DEC-10(협의 범위 코드·계약 범위) 결정 전. 지정 API 미구현")
def test_UC_033_S01_지정_제출_승인(target, s0):
    """작업별 산출물 항목·양식 지정 (AC-033-1~3)."""


@pytest.mark.skip(reason="DEC-10 결정 전")
def test_UC_033_S02_교체_뒤_재지정(target, s0):
    """계획서 교체 뒤 재지정 (AC-033-4)."""


@pytest.mark.skip(reason="DEC-10 결정 전. 지정 API 가 없어 거절(403)과 미구현(404)을 가를 수 없다")
def test_UC_033_S03_용역사_지정_시도(target, s0):
    """V1 지정 → 거절 (AC-033-1)."""
