"""자료 상세와 설정 (ARC-016 3-3-1). WBS 항목과 29110 유형 태그를 사람이 정한다."""

from tests.conftest import requires_db
from tests.test_documents import _auth, _upload, _xlsx_bytes, as_pm  # noqa: F401  (fixture)
from tests.test_wbs_deliverables_api import PID, plan  # noqa: F401  (fixture)
from tests.test_wbs_schedule_api import no_plan  # noqa: F401  (plan 이 쓰는 fixture)


@requires_db
def test_상세는_정보와_설정을_주고_설정은_판정에_바로_반영된다(client, as_pm, plan):  # noqa: F811
    token = as_pm
    doc_id = _upload(client, token, "설계 메모.xlsx", _xlsx_bytes("상세확인")).json()["id"]

    detail = client.get(f"/api/documents/{doc_id}", headers=_auth(token))
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["fileName"] == "설계 메모.xlsx" and body["status"] == "STRUCTURED"
    assert body["wbsId"] is None and body["productType"] is None
    assert body["downloadUrl"] == f"/api/documents/{doc_id}/content"
    assert body["originalUrl"] is None  # 직접 올린 문서라 원천 링크가 없다
    assert body["extractedCharCount"] > 0

    # WBS 항목과 유형을 정한다
    res = client.patch(
        f"/api/documents/{doc_id}",
        json={"wbsId": "2.1", "productType": "SOFTWARE_DESIGN"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["wbsId"] == "2.1" and res.json()["wbsName"] == "연계 수집"
    assert res.json()["productType"] == "SOFTWARE_DESIGN"

    # 산출물 화면이 그 항목을 제출로, 유형 태그를 사람이 정한 값으로 본다
    items = client.get(
        f"/api/projects/{PID}/wbs/deliverables?at=2026-09-22", headers=_auth(token)
    ).json()
    item = next(i for i in items["items"] if i["wbsId"] == "2.1")
    assert item["status"] == "SUBMITTED" and item["rule"] == "LINKED_DOC"
    assert item["productType"] == "SOFTWARE_DESIGN"
    assert [d["id"] for d in item["documents"]] == [doc_id]

    # 빈 문자열은 지운다
    res = client.patch(
        f"/api/documents/{doc_id}", json={"wbsId": "", "productType": ""}, headers=_auth(token)
    )
    assert res.json()["wbsId"] is None and res.json()["productType"] is None


@requires_db
def test_없는_항목이나_모르는_유형은_거절한다(client, as_pm, plan):  # noqa: F811
    doc_id = _upload(client, as_pm, "아무거나.xlsx", _xlsx_bytes("거절확인")).json()["id"]
    missing = client.patch(f"/api/documents/{doc_id}", json={"wbsId": "9.9"}, headers=_auth(as_pm))
    assert missing.status_code == 400
    bad = client.patch(
        f"/api/documents/{doc_id}", json={"productType": "NOT_A_TYPE"}, headers=_auth(as_pm)
    )
    assert bad.status_code == 400 and "유형" in bad.json()["message"]
