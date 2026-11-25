# ruff: noqa: E501
"""D 그룹: WBS·산출물·완료 확인 (UC-030 ~ UC-033) 예제 시나리오.

한 S0 위에서 순서대로 돈다. 앞부분은 S0 그대로의 WBS 인식·지연 판정을 보고, UC-031-S01 이
S0a(SW설계서 v1 제출)를 만들어 승인까지 간다. 그 뒤 UC-032 가 3.2 완료 확인·철회를 보고,
WBS 변형(합≠1·머리글 없음·v2·L2·산출물 열 변경)은 저장소 파일을 바꿔 재수집한 뒤 원래 파일로
되돌린다. DEC-04·10·12 에 걸린 시나리오는 보류한다.
"""

from __future__ import annotations

import re

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
    res = target.post(f"/api/connections/{s0.ids[con]}/sync", json={"kind": "BACKFILL"}, headers=auth(s0.tokens[acc]))
    # 거절(409 수집 중 등)이면 잡 대신 오류 본문이 온다. 원인을 그대로 보이게 코드와 본문을 남긴다
    assert res.status_code == 202, (res.status_code, res.text[:300])
    job = res.json()
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


def _confirm(target, s0, doc_id: str, type_code: str, title: str, version: str, acc="TD-ACC-V1"):
    """초안 확정 = 산출물 제출본 등록(DEC-14). 상태를 고르지 않는다."""
    return target.post(f"/api/documents/{doc_id}/draft/confirm", json={
        "type": type_code, "title": title, "version": version, "requirements": [],
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
    """변형 뒤 S0 내용으로 되돌린다. 같은 blob 이라 그 판이 현행으로 되살아나야 한다(DEF-V033)."""
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


def _plan_upload(target, s0, prj: str, path, name: str, version: str | None = None, acc="TD-ACC-V1"):
    """일정 화면의 WBS 올리기와 같은 요청(11-24). 올린 파일이 곧바로 사업수행계획서가 된다."""
    with open(path, "rb") as f:
        return target.post(
            f"/api/projects/{s0.ids[prj]}/wbs/plan", files={"file": (name, f, XLSX)},
            data={"version": version} if version else {}, headers=auth(s0.tokens[acc]),
        )


def test_UC_030_S02_업로드_계획서(target, s0, screen):
    """저장소가 없는 TD-PRJ-9 에서 일정 화면 「WBS 올리기」로 TD-DOC-6 을 v1 으로 올림 → 같은 인식 결과, L1,
    수치의 원천에 올린 파일 이름 (AC-030-1·8)."""
    pid = s0.ids["TD-PRJ-9"]
    if screen:
        sc = screen("TD-ACC-V1")
        sc.open(f"/p/{pid}/schedule").see("진척률 산정의 핵심 입력이 빠져 있습니다")
        sc.page.get_by_role("button", name="WBS 올리기").click()
        dlg = sc.page.get_by_role("dialog")
        dlg.locator("#planFile").set_input_files(str(s0.files["TD-DOC-6"]))
        dlg.locator("#planVersion").fill("v1")
        dlg.get_by_role("button", name="올리기").click()
        dlg.wait_for(state="hidden", timeout=60000)
        sc.see("수치의 원천", "올린 파일", s0.files["TD-DOC-6"].name, selector="main", timeout=30000)
        sc.page.get_by_role("button", name="WBS 새 버전 올리기").wait_for(timeout=15000)
        sc.shot("WBS 올린 뒤 일정")
        sc.done()
    else:
        res = _plan_upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-6"], s0.files["TD-DOC-6"].name, "v1")
        assert res.status_code == 201, res.text
        assert (res.json()["version"], res.json()["leafCount"]) == ("v1", 5), res.json()
    w = _wbs(target, s0, "TD-PRJ-9")
    leaves = [i for i in w["items"] if i["weight"] and i["level"] > 0]
    assert w["source"] == "WBS_FILE" and len(leaves) == 5, (w["source"], w["warnings"], len(leaves))
    assert (w["planVersion"], w["sourceFile"]["origin"]) == ("v1", "UPLOAD"), (w["planVersion"], w["sourceFile"])
    assert w["sourceFile"]["path"] == s0.files["TD-DOC-6"].name
    assert w["planUpload"] is True
    assert _progress(target, s0, "TD-PRJ-9")["level"] == "L1"


def test_UC_030_S11_WBS_올리기_창구(target, s0, screen):
    """일정 화면 WBS 올리기의 규칙. 저장소에서 WBS 를 읽는 TD-PRJ-1 에는 버튼이 없고 API 도 거절한다. WBS 로
    읽히지 않는 파일·엑셀이 아닌 파일은 받지 않고 현행 판이 그대로다. 새 버전(v2)을 올리면 그 판으로 바뀌고,
    올린 계획서는 자료 목록에 나오지 않는다 (AC-030-8)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    repo = _wbs(target, s0, "TD-PRJ-1")
    assert repo["planUpload"] is False
    refused = _plan_upload(target, s0, "TD-PRJ-1", s0.files["TD-DOC-6"], "WBS.xlsx")
    assert refused.status_code == 409 and refused.json()["code"] == "PLAN_FROM_REPOSITORY", refused.text

    bad = target.post(f"/api/projects/{s0.ids['TD-PRJ-9']}/wbs/plan",
                      files={"file": ("WBS.xlsx", b"not a workbook", XLSX)}, headers=v1)
    assert bad.status_code == 400 and "WBS 로 읽을 수 없습니다" in bad.json()["message"], bad.text
    pdf = target.post(f"/api/projects/{s0.ids['TD-PRJ-9']}/wbs/plan",
                      files={"file": ("WBS.pdf", b"%PDF-1.4", "application/pdf")}, headers=v1)
    assert pdf.status_code == 400 and ".xlsx" in pdf.json()["message"], pdf.text
    assert _wbs(target, s0, "TD-PRJ-9")["planVersion"] == "v1", "거절한 파일이 현행 판을 바꿨다"

    v2 = files.wbs_v2(s0.files["TD-DOC-6"].parent / "WBS-S11-v2.xlsx")  # 말단 6건
    res = _plan_upload(target, s0, "TD-PRJ-9", v2, v2.name, "v2")
    assert res.status_code == 201, res.text
    doc_id = res.json()["documentId"]
    w = _wbs(target, s0, "TD-PRJ-9")
    assert (w["planVersion"], w["sourceFile"]["path"]) == ("v2", v2.name), (w["planVersion"], w["sourceFile"])
    assert len([i for i in w["items"] if i["weight"] and i["level"] > 0]) == 6
    docs = target.get(f"/api/projects/{s0.ids['TD-PRJ-9']}/documents?general=true&size=100", headers=v1)
    assert docs.status_code == 200, docs.text
    assert doc_id not in {x["id"] for x in docs.json()["content"]}, "올린 계획서가 자료 목록에 나왔다"
    if screen:
        sc = screen("TD-ACC-V1")
        sc.open(f"/p/{s0.ids['TD-PRJ-1']}/schedule").see("수치의 원천")
        assert sc.page.get_by_role("button", name=re.compile("WBS (새 버전 )?올리기")).count() == 0
        sc.shot("저장소 WBS 사업에는 버튼 없음")
        sc.open(f"/p/{s0.ids['TD-PRJ-9']}/schedule").see(v2.name)
        sc.expect_rejected()
        sc.page.get_by_role("button", name="WBS 새 버전 올리기").click()
        dlg = sc.page.get_by_role("dialog")
        bad_file = v2.parent / "깨진-WBS.xlsx"
        bad_file.write_bytes(b"not a workbook")
        dlg.locator("#planFile").set_input_files(str(bad_file))
        dlg.get_by_role("button", name="올리기").click()
        sc.see("WBS 로 읽을 수 없습니다", selector='[role="dialog"]')
        sc.shot("못 읽는 파일 거절")
        sc.done()


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


def test_UC_030_S07_인식_결과_표시(target, s0, replay, screen):
    """DEC-04 (b): 인식 결과(말단 5·묶음 1·가중치 합 1.000·산출물 미지정 0·열 매핑)와 재수집 안내가 보인다.
    머리글 없는 판을 수집하면 사유가 보이고 직전 5건이 기준선으로 남아 0건·0% 로 보이지 않는다 (AC-030-3·4)."""
    pid = s0.ids["TD-PRJ-1"]
    rec = _wbs(target, s0, acc="TD-ACC-V1")["recognition"]
    assert rec["status"] == "OK", rec
    assert (rec["leafCount"], rec["groupCount"], rec["weightTotal"], rec["missingDeliverableCount"]) == (5, 1, 1.0, 0), rec
    headers = {c["label"]: c["header"] for c in rec["columns"]}
    assert headers["작업명"] == "업무분류" and headers["가중치"] == "가중치" and headers["실적"] == "실적", headers
    assert rec["headerRow"] == 1 and "원본 파일을 고쳐" in rec["guidance"]
    sc = screen("TD-ACC-V1") if screen else None
    if sc:
        sc.open(f"/p/{pid}/schedule").see("계획서 인식 결과", "업무분류", "원본 파일을 고쳐")
        facts = sc.page.get_by_test_id("recognition-facts").inner_text()
        for want in ("말단 작업", "5개", "1.000", "산출물 미지정", "0개"):
            assert want in facts, facts
        sc.shot("인식_결과")
    replay.faults = Faults(wbs_variant="TD-WBS-NOHEAD", wbs_sha="7d7d7d7d" + "0" * 32)
    _sync(target, s0)
    try:
        w = _wbs(target, s0, acc="TD-ACC-V1")
        failed = w["recognition"]
        assert failed["status"] == "FAILED" and "머리글을 찾지 못했습니다" in (failed["error"] or ""), failed
        assert failed["usingPrevious"] is True
        assert len([i for i in w["items"] if i["weight"] and i["level"] > 0]) == 5
        prog = _progress(target, s0)
        assert prog["representative"] is not None and round(prog["representative"], 4) == 0.3, prog
        if sc:
            sc.open(f"/p/{pid}/schedule").see("읽지 못했습니다", "머리글을 찾지 못했습니다", "작업 5개를 이전 기준선으로")
            sc.see(re.compile(r"보고 진척률\s*30\.0%"))
            sc.shot("읽지_못한_판")
    finally:
        _restore_wbs(target, s0, replay)
    assert _wbs(target, s0, acc="TD-ACC-V1")["recognition"]["status"] == "OK", "되돌린 뒤에도 인식 결과가 실패로 남았다"
    if sc:
        sc.done()


# ------------------------------------------------------------------ UC-031 (S0 → S0a → 승인)


def test_UC_031_S07_지연_판정(target, s0):
    """S0, T0: 3.2 는 지연(종료 07-31 < T0, 미제출) (AC-031-3, IM-005A 7.2)."""
    items = {i["wbsId"]: i for i in _deliverables(target, s0)["items"]}
    assert items["3.2"]["status"] == "OVERDUE", items["3.2"]
    assert items["3.1"]["status"] == "SUBMITTED", items["3.1"]
    assert {items[k]["status"] for k in ("3.3", "3.4", "3.5")} <= {"MISSING", "NONE"}, [items[k]["status"] for k in ("3.3", "3.4", "3.5")]


def test_UC_031_S01_올려_제출하고_승인(target, s0, screen):
    """TD-DOC-3 업로드(3.2) → SW설계서 제출(S0a) → C1 승인. 판정 제출(연결 문서), 승인자, 지표 불변 (AC-031-1·3·4·6)."""
    before = (_progress(target, s0)["representative"], _completion(target, s0)["completionRate"])
    s0.s0a()
    check = _checklist(target, s0)
    assert check["SOFTWARE_DESIGN"]["status"] == "SUBMITTED" and check["SOFTWARE_DESIGN"]["version"] == "v1", check["SOFTWARE_DESIGN"]
    items = {i["wbsId"]: i for i in _deliverables(target, s0)["items"]}
    assert items["3.2"]["status"] == "SUBMITTED", items["3.2"]
    assert items["3.2"]["rule"] == "DESIGNATED", items["3.2"]  # WBS 자동 예상 산출물(V73)
    wp = s0.ids["TD-DOC-3:wp"]
    res = target.post(f"/api/projects/{s0.ids['TD-PRJ-1']}/work-products/{wp}/approve", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 204, res.text
    check = _checklist(target, s0)
    assert check["SOFTWARE_DESIGN"]["status"] == "APPROVED"
    assert check["SOFTWARE_DESIGN"]["approvedBy"] and d.ACCOUNTS["TD-ACC-C1"].display in str(check["SOFTWARE_DESIGN"]["approvedBy"])
    after = (_progress(target, s0)["representative"], _completion(target, s0)["completionRate"])
    assert after == before, (before, after)
    assert round(after[0], 4) == 0.3 and round(after[1], 4) == 0.15
    _ui_UC_031_S01(screen, s0)


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
    """용역사·관리자 승인 / 빈 사유 반려 → 거절 (AC-031-4, DEC-05). 지난 버전 승인은 S04 뒤 본다."""
    wp = s0.ids["TD-DOC-3:wp"]
    pid = s0.ids["TD-PRJ-1"]
    assert target.post(f"/api/projects/{pid}/work-products/{wp}/approve", headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403
    a1 = auth(s0.tokens["TD-ACC-A1"])
    for res in (target.post(f"/api/projects/{pid}/work-products/{wp}/approve", headers=a1),
                target.post(f"/api/projects/{pid}/work-products/{wp}/reject", json={"reason": "x"}, headers=a1)):
        assert res.status_code == 403 and "플랫폼 관리자는" in res.json()["message"], res.text
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


def test_UC_031_S04_반려_뒤_재제출_이력(target, s0, screen):
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
    past = {h["version"]: h for h in now["previousVersions"]}
    assert past["v2"]["status"] == "REJECTED" and past["v2"]["rejectReason"] == "목차 누락", past
    assert past["v2"]["decidedBy"] and past["v2"]["decidedAt"], "반려한 사람·일자가 없다"
    _review_window_history(target, s0, screen)


def _review_window_history(target, s0, screen):
    """산출물 검토 창(11-18·19 개편 뒤 승인 단위는 올라온 산출물): 3.2 양식에 올린 것을 반려
    「목차 누락」 → 같은 양식에 새 파일 → 새 것이 최신·승인 대기, 상세보기에 지난 버전의 반려·사유·
    처리자·처리 일시 (AC-031-4·5, IM-002 v0.2.29)."""
    pid = s0.ids["TD-PRJ-1"]
    v1, c1 = auth(s0.tokens["TD-ACC-V1"]), auth(s0.tokens["TD-ACC-C1"])
    item = next(i for i in _deliverables(target, s0)["items"] if i["wbsId"] == "3.2")
    form = next(dd for dd in item["designated"] if not dd.get("needsRedesignation"))
    made: list[str] = []

    def put(name: str, marker: str) -> str:
        with open(_fresh_docx(s0, name, marker), "rb") as f:
            res = target.post(
                f"/api/projects/{pid}/documents", files={"file": (name, f, DOCX)},
                data={"wbsId": "3.2", "designatedId": form["id"]}, headers=v1,
            )
        assert res.status_code in (200, 201, 202), res.text
        s0.await_document("TD-ACC-V1", res.json()["id"])
        made.append(res.json()["id"])
        return res.json()["id"]

    try:
        first = put("SW설계서_검토1.docx", "검토 1차")
        # 반려는 발주기관만, 사유가 있어야 한다
        assert target.post(f"/api/projects/{pid}/documents/{first}/reject", json={"reason": "목차 누락"}, headers=v1).status_code == 403
        assert target.post(f"/api/projects/{pid}/documents/{first}/reject", json={"reason": " "}, headers=c1).status_code in (400, 422)
        res = target.post(f"/api/projects/{pid}/documents/{first}/reject", json={"reason": "목차 누락"}, headers=c1)
        assert res.status_code == 204, res.text
        second = put("SW설계서_검토2.docx", "검토 2차")
        item = next(i for i in _deliverables(target, s0)["items"] if i["wbsId"] == "3.2")
        review = {r["documentId"]: r for r in item["review"]}
        assert review[second]["latest"] and review[second]["status"] == "SUBMITTED", review[second]
        old = review[first]
        assert not old["latest"] and old["status"] == "REJECTED" and old["rejectReason"] == "목차 누락", old
        who = d.ACCOUNTS["TD-ACC-C1"].display
        assert old["reviewedBy"] == who and old["reviewedAt"], old
        if not screen:
            return
        sc = screen("TD-ACC-C1")
        sc.open(f"/p/{pid}/deliverables").see("3.2")
        sc.page.locator("tr", has_text="3.2").filter(has_text="설계").first.get_by_role("button", name="검토").click()
        dialog = sc.page.get_by_role("dialog")
        entry = dialog.locator("li", has_text="SW설계서_검토2.docx").first
        # 같은 양식에 앞 시나리오(S01 등)가 올린 판도 지난 버전으로 센다. 수는 모듈 순서에 따라 다르다
        entry.get_by_text(re.compile(r"지난 버전 \d+개")).wait_for(timeout=15000)
        entry.get_by_role("button", name="상세보기").click()
        dialog.get_by_role("button", name=re.compile("SW설계서_검토1.docx")).click()
        sc.see("반려 사유: 목차 누락", who, selector='[role="dialog"]')
        sc.shot("검토 창 지난 버전")
        sc.done()
    finally:
        for doc in made:
            target.delete(f"/api/documents/{doc}", headers=v1)


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


def test_UC_031_S02_저장소_파일_고르기(target, s0, replay, screen):
    """V1 이 3.2 [업로드] → 저장소 파일 선택에서 설계서 파일 → 3.2 「제출」, 검토 창에 그 파일이 승인 대기.
    고르지 않은 저장소 파일은 작업 판정에 들지 않는다 (AC-031-2).

    11-19 개편(41bec3e)으로 저장소 파일 자동 판정이 없어지고 올리기에서 고르게 바뀌었다. 옛 시험은 설정
    경로에 커밋하면 제출본이 생기는지를 봤다. 모듈을 이어 돌리면 앞 시나리오(S01)가 3.2 에 TD-DOC-3 을
    올린 뒤라 「1/1건」 대신 고른 파일이 3.2 문서로 붙고 판정이 제출인지 본다."""
    path = "docs/20-design/SW설계서_v0.9.docx"
    name = path.rsplit("/", 1)[-1]
    pid = s0.ids["TD-PRJ-1"]
    v1 = auth(s0.tokens["TD-ACC-V1"])
    made: list[str] = []
    try:
        replay.faults = Faults(serve_design_file=True, extra_tree_paths=[path])
        _sync(target, s0)
        listed = target.get(f"/api/projects/{pid}/repository-files", headers=v1)
        assert listed.status_code == 200, listed.text
        assert path in listed.json()["paths"], listed.json()
        before = {i["wbsId"]: i for i in _deliverables(target, s0)["items"]}
        if screen:
            sc = screen("TD-ACC-V1")
            sc.open(f"/p/{pid}/deliverables").see("3.2")
            row = sc.page.locator("tr", has_text="3.2").filter(has_text="설계").first
            # 3.2 에는 WBS 가 정한 양식이 있어 [업로드]가 양식 창을 열고, 저장소 파일은 그 안에서 고른다
            row.get_by_role("button", name="업로드").click()
            forms = sc.page.get_by_role("dialog").first
            forms.get_by_role("button", name="업로드").first.click()
            sc.page.get_by_role("menuitem", name="저장소 파일 선택").click()
            dialog = sc.page.get_by_role("dialog").filter(has_text="저장소 파일 선택")
            dialog.get_by_role("combobox").click()
            sc.page.get_by_label("저장소 파일 찾기").fill("SW설계서")
            sc.page.get_by_role("option", name=path).click()
            dialog.get_by_role("button", name="업로드").click()
            dialog.wait_for(state="hidden", timeout=30000)
            sc.shot("저장소 파일 올림")
        else:
            res = target.post(
                f"/api/projects/{pid}/documents/from-repository",
                json={"path": path, "wbsId": "3.2"},
                headers=v1,
            )
            assert res.status_code == 201, res.text
        after = {i["wbsId"]: i for i in _deliverables(target, s0)["items"]}
        docs = [x for x in after["3.2"]["documents"] if x["fileName"] == name]
        assert docs, after["3.2"]["documents"]
        made = [x["id"] for x in docs]
        assert after["3.2"]["status"] == "SUBMITTED", after["3.2"]
        changed = [w for w in before if w != "3.2" and before[w]["status"] != after[w]["status"]]
        assert not changed, f"고르지 않은 작업의 판정이 바뀌었다: {changed}"
        if screen:
            sc.open(f"/p/{pid}/deliverables").see("3.2")
            assert "제출" in sc.page.locator("tr", has_text="3.2").filter(has_text="설계").first.inner_text()
            sc.done()
            c1 = screen("TD-ACC-C1")
            c1.open(f"/p/{pid}/deliverables").see("3.2")
            c1.page.locator("tr", has_text="3.2").filter(has_text="설계").first.get_by_role(
                "button", name="검토"
            ).click()
            c1.see(name, "승인 대기", selector='[role="dialog"]')
            c1.shot("검토 창")
            c1.done()
    finally:
        for doc in made:
            target.delete(f"/api/documents/{doc}", headers=v1)
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
    """가중치 열 없음 → 기간 비례 가중치 × 파일 실적, 「추정」 표시, 30.3% (A3, DEC-19 (b), IM-005A 7.1)."""
    replay.faults = Faults(wbs_variant="TD-WBS-L2", wbs_sha="2c2c2c2c" + "0" * 32)
    _sync(target, s0)
    prog = _progress(target, s0)
    try:
        assert prog["level"] == "L2" and prog["representative"] is not None, prog
        assert round(prog["representative"], 4) == 0.3029, prog["representative"]
        # 계획선도 같은 가중치로: (44 + 106 + 106 + 14) / 375 = 0.72
        assert round(prog["wbsPlanned"], 4) == 0.72, prog["wbsPlanned"]
        assert prog["estimated"] is True and prog["basisNote"].startswith("추정"), prog
        assert any("기간에 비례" in w for w in prog["warnings"]), prog["warnings"]
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
    # 선행: 3.2 가 확인돼 있어야 「다시 확인 필요」가 성립한다(UC-032-S01·S02 가 만든다). 이 시험만
    # 골라 돌리면 확인이 없어 NONE 이 나온다. 그때는 제품 결함이 아니라 시작 상태가 다르다
    before = next(i for i in _completion(target, s0)["items"] if i["wbsId"] == "3.2")
    assert before["completionStatus"] == "CONFIRMED", f"시작 상태가 아니다(3.2 확인 없음): {before}"
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
    # 작업에 바로 올리면 읽은 뒤 자동 제출된다(11-18). 유형·버전을 정해 확정한 뒤 작업에 붙인다
    doc = _upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-2"], "시험결과서.docx", DOCX)
    res = _confirm(target, s0, doc, "TEST_REPORT", "시험결과서", "v1")
    assert res.status_code == 200, res.text
    wp = res.json()["workProductId"]
    assert target.patch(f"/api/documents/{doc}", json={"wbsId": "3.4"}, headers=v1).status_code == 200
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


def test_UC_031_S10_승인률(target, s0):
    """S0 산출물 승인률 1/5 = 20.0%: 분모 = 예상 산출물 5(요청 없이 WBS 산출물 열), 분자 = 3.1 에 올라온 요구사항정의서 승인.
    사업수행계획서는 WBS 산출물 열에 없어 세지 않는다. 산출 근거 문장 (AC-031-9, DEC-12 (b), IM-005A 7.2)."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    prog = target.get(f"/api/projects/{pid}/progress?at={d.T0.isoformat()}", headers=c1).json()
    ap = prog["deliverableApproval"]
    assert (ap["numerator"], ap["denominator"]) == (1, 5), ap
    assert round(ap["value"], 4) == 0.2 and "예상 산출물" in ap["note"], ap
    spec = {
        "template": "STAT_CARD", "title": "TST 승인률",
        "query": {"measure": "deliverable_approval_rate", "dimensions": [], "filters": [], "projectScope": [pid], "limit": None},
        "options": {"unit": None, "sort": "desc", "threshold": None, "stacked": None, "showLegend": None, "compareWithPrevious": None, "columns": None},
    }
    res = target.post("/api/widgets/preview", json={"spec": spec}, headers=c1)
    assert res.status_code == 200, res.text[:200]
    body = res.json()
    assert round(body["total"]["values"]["value"], 2) == 20.0, body["total"]
    assert "WBS" in (body.get("basis") or ""), body.get("basis")


# ------------------------------------------------------------------ UC-033 (V70~V73, 11-18·11-19)

_DESIG = "/api/projects/{pid}/wbs/designated-deliverables"


def _row(target, s0, wbs_id: str, acc="TD-ACC-C1") -> dict:
    res = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/wbs/deliverables?at={T0}", headers=auth(s0.tokens[acc]))
    assert res.status_code == 200, res.text
    return next(i for i in res.json()["items"] if i["wbsId"] == wbs_id)


def _requested(row: dict) -> list[dict]:
    return [x for x in row["designated"] if x.get("origin") != "WBS"]


def _designate(target, s0, wbs_id: str, acc="TD-ACC-C1", **body):
    pid = s0.ids["TD-PRJ-1"]
    key = _row(target, s0, wbs_id)["taskKey"]
    return target.post(_DESIG.format(pid=pid), json={"taskKey": key, **body}, headers=auth(s0.tokens[acc]))


def _xlsx_bytes(marker: str) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["항목", marker])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _submit(target, s0, designated_id: str, name: str, marker: str, acc="TD-ACC-V1") -> str:
    res = target.post(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/documents",
        files={"file": (name, _xlsx_bytes(marker), XLSX)},
        data={"designatedId": designated_id}, headers=auth(s0.tokens[acc]),
    )
    assert res.status_code == 201, res.text
    s0.await_document(acc, res.json()["id"])
    return res.json()["id"]


def _review(target, s0, doc_id: str, action: str, acc="TD-ACC-C1", reason: str | None = None):
    return target.post(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/documents/{doc_id}/{action}",
        json={"reason": reason} if reason else {}, headers=auth(s0.tokens[acc]),
    )


def _template(target, s0, designated_id: str, marker: str, acc="TD-ACC-C1"):
    return target.post(
        f"{_DESIG.format(pid=s0.ids['TD-PRJ-1'])}/{designated_id}/template",
        files={"file": (f"양식-{marker}.xlsx", _xlsx_bytes(marker), XLSX)}, headers=auth(s0.tokens[acc]),
    )


def _undesignate(target, s0, designated_id: str, docs: list[str]) -> None:
    pid = s0.ids["TD-PRJ-1"]
    for doc in docs:
        target.delete(f"/api/documents/{doc}", headers=auth(s0.tokens["TD-ACC-C1"]))
    target.delete(f"{_DESIG.format(pid=pid)}/{designated_id}", headers=auth(s0.tokens["TD-ACC-C1"]))


def test_UC_033_S03_용역사_지정_시도(target, s0):
    """V1 이 3.4 에 산출물 항목을 정하려 함 → 거절. 요청 항목이 생기지 않는다 (AC-033-1)."""
    res = _designate(target, s0, "3.4", acc="TD-ACC-V1", name="통합시험결과서")
    assert res.status_code == 403, res.text
    assert _requested(_row(target, s0, "3.4")) == []


def test_UC_033_S01_지정_제출_승인(target, s0):
    """C1 이 3.4 에 「통합시험결과서」 항목·양식·안내를 정한다 → V1 양식 내려받기 → 제출 → C1 반려(사유) →
    V1 다시 올림 → C1 승인. 양식은 제출본이 아니고, 판마다 상태가 남는다 (AC-033-1·3)."""
    pid = s0.ids["TD-PRJ-1"]
    res = _designate(target, s0, "3.4", name="통합시험결과서", productType="TEST_REPORT", guide="결함 목록을 붙인다")
    assert res.status_code == 201, res.text
    did = res.json()["id"]
    docs: list[str] = []
    try:
        assert _template(target, s0, did, "S01", acc="TD-ACC-V1").status_code == 403
        assert _template(target, s0, did, "S01").status_code == 204
        got = target.get(f"{_DESIG.format(pid=pid)}/{did}/template", headers=auth(s0.tokens["TD-ACC-V1"]))
        assert got.status_code == 200 and got.content[:2] == b"PK", got.status_code
        row = _row(target, s0, "3.4")
        [item] = _requested(row)
        assert (item["name"], item["guide"], item["status"]) == ("통합시험결과서", "결함 목록을 붙인다", "MISSING")
        assert item["templateFileName"] == "양식-S01.xlsx"
        assert row["review"] == [], "양식이 제출본으로 잡혔다"

        docs.append(_submit(target, s0, did, "통합시험결과-v1.xlsx", "v1"))
        assert _requested(_row(target, s0, "3.4"))[0]["status"] == "SUBMITTED"
        assert _review(target, s0, docs[0], "approve", acc="TD-ACC-V1").status_code == 403
        assert _review(target, s0, docs[0], "reject").status_code == 400  # 사유 필수
        assert _review(target, s0, docs[0], "reject", reason="결함 목록 누락").status_code == 204

        docs.append(_submit(target, s0, did, "통합시험결과-v2.xlsx", "v2"))
        assert _review(target, s0, docs[1], "approve").status_code == 204
        row = _row(target, s0, "3.4", acc="TD-ACC-V1")
        item = _requested(row)[0]
        assert item["status"] == "APPROVED"
        assert [v["state"] for v in item["versions"]] == ["APPROVED", "REJECTED"]
        assert item["versions"][1]["rejectReason"] == "결함 목록 누락"
        latest = {r["documentId"]: r["latest"] for r in row["review"]}
        assert latest == {docs[1]: True, docs[0]: False}, row["review"]
    finally:
        _undesignate(target, s0, did, docs)


def test_UC_033_S02_교체_뒤_재지정(target, s0, replay):
    """3.3(구현)·3.4(시험) 에 요청 항목을 정한 뒤 3.4 를 3.4·3.5 로 쪼갠 v2 수집 → 그대로인 3.3 은
    지정이 따라가고, 가중치가 옮겨 간 3.4 는 정체가 끊겨 「재지정 필요」로 모인다(지정·제출 이력 보존).
    발주기관이 새 3.4 로 다시 정하면 그 작업에 붙는다 (AC-033-4)."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    made = [
        _designate(target, s0, "3.3", name="소스 목록", productType="SOFTWARE_COMPONENT"),
        _designate(target, s0, "3.4", name="통합시험결과서", productType="TEST_REPORT"),
    ]
    ids = [r.json().get("id") for r in made if r.status_code == 201]
    try:
        assert [r.status_code for r in made] == [201, 201], [r.text for r in made]
        keep, moved = ids
        replay.faults = Faults(wbs_variant="TD-WBS-V2", wbs_sha="e2e2e2e2" + "3" * 32)
        _sync(target, s0)
        screen_ = target.get(f"/api/projects/{pid}/wbs/deliverables?at={T0}", headers=c1).json()
        rows = {i["wbsId"]: i for i in screen_["items"]}
        assert keep in [x["id"] for x in _requested(rows["3.3"])], "정체가 이어진 3.3 의 지정이 사라졌다"
        orphans = {x["id"]: x for x in screen_["redesignation"]}
        assert moved in orphans, screen_["redesignation"]
        assert orphans[moved]["needsRedesignation"] is True and orphans[moved]["taskNameAt"] == "시험"
        assert moved not in [x["id"] for x in _requested(rows["3.4"])]

        res = target.patch(f"{_DESIG.format(pid=pid)}/{moved}", json={"taskKey": rows["3.4"]["taskKey"]}, headers=c1)
        assert res.status_code == 204, res.text
        again = target.get(f"/api/projects/{pid}/wbs/deliverables?at={T0}", headers=c1).json()
        assert moved not in [x["id"] for x in again["redesignation"]]
        assert moved in [x["id"] for x in _requested({i["wbsId"]: i for i in again["items"]}["3.4"])]
        kinds = [e["kind"] for e in target.get(f"{_DESIG.format(pid=pid)}/{moved}/history", headers=c1).json()]
        assert kinds == ["CREATED", "REASSIGNED"], kinds
    finally:
        _restore_wbs(target, s0, replay)
        for x in ids:
            _undesignate(target, s0, x, [])


def test_UC_033_S04_예상_산출물_관리(target, s0, screen):
    """3.4 에 요청 항목을 더하면 「예상 산출물」 칸에 첫 이름과 「외 1건」, [관리] 가 보이고, 관리 창에
    「WBS 자동」 항목(시험결과서)과 요청 항목이 함께 나온다. WBS 자동 항목도 고칠 수 있다 (AC-033-2)."""
    pid = s0.ids["TD-PRJ-1"]
    res = _designate(target, s0, "3.4", name="결함 조치 보고서", productType="TEST_REPORT")
    assert res.status_code == 201, res.text
    did = res.json()["id"]
    auto: dict = {}
    try:
        row = _row(target, s0, "3.4")
        origins = sorted((x["origin"], x["name"]) for x in row["designated"])
        assert origins == [("REQUEST", "결함 조치 보고서"), ("WBS", "시험결과서")], origins
        auto = next(x for x in row["designated"] if x["origin"] == "WBS")
        fix = target.patch(
            f"{_DESIG.format(pid=pid)}/{auto['id']}", json={"guide": "시험 범위를 적는다"},
            headers=auth(s0.tokens["TD-ACC-C1"]),
        )
        assert fix.status_code == 204, fix.text
        fixed = next(x for x in _row(target, s0, "3.4")["designated"] if x["origin"] == "WBS")
        assert fixed["guide"] == "시험 범위를 적는다"
        if screen:
            sc = screen("TD-ACC-C1")
            sc.open(f"/p/{pid}/deliverables").see("3.4")
            line = sc.page.locator("tr", has_text="3.4").filter(has_text="시험").first
            assert "외 1건" in line.inner_text()
            line.get_by_role("button", name="관리").click()
            sc.see("WBS 자동", "발주사 요청", "결함 조치 보고서", "시험결과서", selector="body")
            sc.shot("예상 산출물 관리 창")
            sc.done()
    finally:
        if auto:
            target.patch(f"{_DESIG.format(pid=pid)}/{auto['id']}", json={"guide": ""}, headers=auth(s0.tokens["TD-ACC-C1"]))
        _undesignate(target, s0, did, [])


def test_UC_033_S05_산출물별_검토(target, s0, screen):
    """3.4 에 올라온 산출물이 검토 창에 하나씩 나오고 발주기관만 승인·반려 단추가 있다. 용역사는 같은
    창을 「보기」로 연다. 양식은 올라온 산출물로 세지 않는다 (AC-033-3)."""
    pid = s0.ids["TD-PRJ-1"]
    did = _designate(target, s0, "3.4", name="통합시험결과서", productType="TEST_REPORT").json()["id"]
    docs: list[str] = []
    try:
        assert _template(target, s0, did, "S05").status_code == 204
        docs.append(_submit(target, s0, did, "통합시험결과-S05.xlsx", "S05"))
        row = _row(target, s0, "3.4")
        assert [r["documentId"] for r in row["review"]] == docs, row["review"]
        assert row["review"][0]["status"] == "SUBMITTED"
        assert _review(target, s0, docs[0], "approve", acc="TD-ACC-V1").status_code == 403
        if screen:
            dlg = '[role="dialog"]'
            c1 = screen("TD-ACC-C1")
            c1.open(f"/p/{pid}/deliverables").see("3.4")
            c1.page.locator("tr", has_text="3.4").filter(has_text="시험").first.get_by_role("button", name="검토").click()
            c1.see("통합시험결과서", "승인 대기", selector=dlg)
            assert c1.page.get_by_role("dialog").get_by_role("button", name="승인").count() == 1
            assert "양식-S05.xlsx" not in c1.page.get_by_role("dialog").inner_text()
            c1.shot("발주기관 검토 창")
            c1.done()
            v1 = screen("TD-ACC-V1")
            v1.open(f"/p/{pid}/deliverables").see("3.4")
            v1.page.locator("tr", has_text="3.4").filter(has_text="시험").first.get_by_role("button", name="보기", exact=True).last.click()
            v1.see("통합시험결과서", selector=dlg)
            assert v1.page.get_by_role("dialog").get_by_role("button", name="승인").count() == 0
            v1.shot("용역사 보기 창")
            v1.done()
        assert _review(target, s0, docs[0], "reject", reason="서명 누락").status_code == 204
        assert _requested(_row(target, s0, "3.4"))[0]["versions"][0]["rejectReason"] == "서명 누락"
    finally:
        _undesignate(target, s0, did, docs)


def test_UC_031_S12_29110_충족_현황(target, s0, screen):
    """산출물 화면 머리의 「ISO/IEC 29110 충족 현황」 → 22종이 PM·SI 로 나뉘고 줄마다 계획 없음·미제출·
    제출·승인 중 하나와 근거 예상 산출물이 보인다. 3.1 요구사항정의서(승인)는 승인 (AC-031-10)."""
    pid = s0.ids["TD-PRJ-1"]
    res = target.get(f"/api/projects/{pid}/wbs/iso29110", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["items"]) == 22 and sum(body["counts"].values()) == 22, body["counts"]
    assert {i["process"] for i in body["items"]} == {"PM", "SI"}
    assert {i["status"] for i in body["items"]} <= {"UNPLANNED", "PLANNED", "SUBMITTED", "APPROVED"}
    by = {i["type"]: i for i in body["items"]}
    assert by["REQUIREMENTS_SPEC"]["status"] == "APPROVED", by["REQUIREMENTS_SPEC"]
    assert [s["wbsId"] for s in by["REQUIREMENTS_SPEC"]["sources"]] == ["3.1"]
    assert any(i["status"] == "UNPLANNED" and i["sources"] == [] for i in body["items"])
    if screen:
        sc = screen("TD-ACC-C1")
        sc.open(f"/p/{pid}/deliverables").see("3.1")
        sc.page.get_by_role("button", name="ISO/IEC 29110 충족 현황").click()
        sc.see("ISO/IEC 29110 산출물 충족 현황", "프로젝트 관리(PM)", "소프트웨어 구현(SI)", "계획 없음", selector='[role="dialog"]')
        sc.shot("29110 충족 현황")
        sc.done()


def _ui_UC_031_S01(screen, s0):
    """화면: 3.2 판정 제출, 29110 충족 현황 설계서 줄, 일정 화면 진척 30.0%·완료 확인율 15.0%.

    인도 점검표(22종 버전 승인 화면)는 11-19 에 뺐다. 22종 쪽은 충족 현황으로 본다."""
    if not screen:
        return
    pid = s0.ids["TD-PRJ-1"]
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/deliverables").see("SW설계서")
    row = sc.row("SW설계서")
    assert "제출" in row and "지연" not in row, row
    sc.page.get_by_role("button", name="ISO/IEC 29110 충족 현황").click()
    sc.see("ISO/IEC 29110 산출물 충족 현황", selector='[role="dialog"]')
    line = sc.page.locator('[role="dialog"] li', has_text="설계서").filter(has_text="3.2").first.inner_text()
    assert "제출" in line or "승인" in line, line
    sc.shot("충족 현황")
    sc.page.keyboard.press("Escape")
    # 완료 확인율은 화면이 소수 없이 「15%」로 쓴다
    sc.open(f"/p/{pid}/schedule").see(
        re.compile(r"보고 진척률\s*30\.0%"), re.compile(r"완료 확인율\s*15(\.0)?%")
    )
    sc.done()


