"""WBS 작업별 산출물·양식 지정 (UC-033, 10-14 협의 1-1절 「WBS 산출물」, GH-141) 수용시험.

AC-033-1 발주기관만 지정한다 · AC-033-2 용역사 화면에 「내야 할 산출물」과 양식, 제출본이 항목에
이어진다 · AC-033-3 항목별 버전 이력·반려 사유, 양식은 제출본이 아니다 · AC-033-4 계획서
교체 뒤 정체가 이어지면 유지, 끊기면 「재지정 필요」이고 이력은 남는다.
"""

import io
import uuid
from datetime import date

import pytest
from openpyxl import Workbook

from app.auth import duties
from app.auth.models import AuthPrincipal
from app.common import errors
from app.dashboard import deliverable, designation, wbs
from app.db import fetch_all, tx
from app.standard import wbs_repository
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
D = date(2026, 9, 1)
TODAY = date(2026, 9, 15)
BASE = [
    ("1.1", "착수보고", "착수보고서.md", 0.2, 1.0),
    ("1.2", "중간보고", "중간보고서.md", 0.3, 0.5),
    ("2.1", "통합 시험", "시험결과서", 0.5, 0.0),
]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- 순수 규칙


def test_확정해야_제출이고_항목_상태는_최근_제출본이_정한다():
    registered = {"draft_status": "PROPOSED", "work_product_id": None}
    submitted = {"draft_status": "CONFIRMED", "work_product_id": "w", "wp_status": "SUBMITTED"}
    rejected = {"draft_status": "CONFIRMED", "work_product_id": "w", "wp_status": "REJECTED"}
    # 제안과 다른 유형으로 확정해도 확정이다(CI 에서 잡힌 것: 시험결과서를 TEST_REPORT 로 확정)
    overridden = {"draft_status": "MANUAL_OVERRIDE", "work_product_id": "w",
                  "wp_status": "SUBMITTED"}
    assert designation.version_state(overridden) == "SUBMITTED"
    assert designation.version_state(registered) == "REGISTERED"
    assert designation.version_state(submitted) == "SUBMITTED"
    assert designation.version_state(rejected) == "REJECTED"
    assert designation.item_status([]) == "MISSING"
    assert designation.item_status(["REGISTERED"]) == "REGISTERED"
    # 새로 올린 것이 확정 전이면 그 앞의 제출본 상태가 남는다
    assert designation.item_status(["REGISTERED", "REJECTED", "APPROVED"]) == "REJECTED"
    assert not designation.is_submitted("REGISTERED")


def test_확정_전_제출본은_다음_할_일을_알려_준다():
    """「냈는데 왜 미제출이냐」를 막는다. 초안이 있으면 제출하러 가고, 읽는 중이면 기다린다."""
    ready = {"draft_status": "PROPOSED", "work_product_id": None, "processing_state": "DONE"}
    reading = {"draft_status": None, "work_product_id": None, "processing_state": "RUNNING"}
    broken = {"draft_status": None, "work_product_id": None, "processing_state": "DONE"}
    done = {"draft_status": "CONFIRMED", "work_product_id": "w", "wp_status": "SUBMITTED"}
    assert designation.submit_readiness(ready) == "READY"
    assert designation.submit_readiness(reading) == "PROCESSING"
    assert designation.submit_readiness(broken) == "NO_DRAFT"
    assert designation.submit_readiness(done) is None
    assert designation.is_submitted("REJECTED")


def _item(wbs_id: str, deliverable_text: str | None, end: date, key: str) -> dict:
    return {"id": key, "wbs_id": wbs_id, "deliverable": deliverable_text, "weight": 0.5,
            "end_on": end, "task_key": key}


def test_지정이_있는_작업은_산출물_열_대신_지정_항목으로_판정한다():
    """산출물 열에 맞는 파일이 있어도 지정 항목이 다 안 왔으면 제출이 아니다(UC-033 4단계)."""
    items = [
        _item("1.1", "착수보고서", date(2026, 9, 30), "k1"),
        _item("1.2", None, date(2026, 9, 1), "k2"),  # 산출물 열이 비어도 지정으로 판정한다
        _item("1.3", None, date(2026, 9, 30), "k3"),
    ]
    docs = [{"id": "d", "original_filename": "착수보고서.hwpx", "wbs_item_id": None}]
    cover = {
        "k1": designation.Coverage(2, 1),
        "k2": designation.Coverage(1, 0),
        "k3": designation.Coverage(1, 1),
    }
    out = {j.wbs_id: j for j in deliverable.judge(
        items, tree=None, products=[], documents=docs, today=TODAY, designated=cover
    )}
    assert (out["1.1"].status, out["1.1"].rule) == ("MISSING", "DESIGNATED")
    assert out["1.1"].ref == "지정 산출물 2건 중 1건 제출"
    assert out["1.2"].status == "OVERDUE"
    assert (out["1.3"].status, out["1.3"].ref) == ("SUBMITTED", "지정 산출물 1건 중 1건 제출")
    # 지정이 없으면 예전 규칙 그대로
    plain = deliverable.judge(items[:1], tree=None, products=[], documents=docs, today=TODAY)
    assert (plain[0].status, plain[0].rule) == ("SUBMITTED", "FILE_NAME")


@pytest.mark.parametrize("role", ["SUPER_ADMIN", "CONTRACTOR"])
def test_지정은_발주기관만_한다(role):
    nobody = "00000000-0000-4000-8000-00000000dead"
    principal = AuthPrincipal(user_id=nobody, org_id=nobody, org_type="PLATFORM", role=role)
    with pytest.raises(errors.ApiError) as raised:
        duties.require(principal, "DELIVERABLE_DESIGNATE")
    assert raised.value.status == 403
    assert ("플랫폼 관리자는" in raised.value.message) == (role == "SUPER_ADMIN")


# ---------------------------------------------------------------- DB 도우미


def _plan(rows, groups=("1", "2")) -> wbs.WbsPlan:
    leaves = [
        wbs.WbsRow(wbs_id=i, name=n, deliverable=d, start=D, end=D, weight=w, actual=a,
                   declared_planned=None)
        for i, n, d, w, a in rows
    ]
    return wbs.WbsPlan(
        rows=leaves, weight_total=round(sum(r.weight for r in leaves), 6), warnings=[],
        groups=[wbs.WbsGroup(wbs_id=g, name=f"묶음 {g}", start=D, end=D) for g in groups],
    )


def _xlsx(marker: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["시험 항목", "결과"])
    ws.append([marker, "통과"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _clean(cur) -> None:
    cur.execute("delete from wbs_designated_deliverable where project_id = %s", (PID,))
    cur.execute(
        "delete from doc_chunk where project_id = %s and source_type = 'DOCUMENT_UPLOAD'", (PID,)
    )
    cur.execute("delete from document_upload where project_id = %s", (PID,))
    cur.execute(
        "delete from work_product where project_id = %s and source_kind = 'DOCUMENT'", (PID,)
    )
    cur.execute(
        """
        update work_product w set is_current = true, updated_at = now()
         where w.project_id = %s and w.version = '0' and not w.is_current
           and not exists (select 1 from work_product c
                            where c.project_id = w.project_id and c.type = w.type
                              and c.is_current)
        """,
        (PID,),
    )
    cur.execute("delete from wbs_completion_record where project_id = %s", (PID,))
    cur.execute("delete from review_request where project_id = %s", (PID,))
    cur.execute("delete from wbs_item where project_id = %s", (PID,))


class Env:
    def __init__(self) -> None:
        self.plans: list[str] = []

    def load(self, rows, groups=("1", "2")) -> None:
        wp_id = str(uuid.uuid4())
        with tx() as cur:
            cur.execute(
                "update work_product set is_current = false "
                "where project_id = %s and type = 'PROJECT_PLAN'",
                (PID,),
            )
            cur.execute(
                """
                insert into work_product (id, project_id, type, version, title, status,
                                          is_current, source_kind, pm_activity)
                values (%s, %s, 'PROJECT_PLAN', %s, 'WBS', 'SUBMITTED', true, 'TOOL', 'PM_1')
                """,
                (wp_id, PID, f"d{len(self.plans) + 1}"),
            )
            wbs_repository.replace_plan(cur, PID, wp_id, _plan(rows, groups))
        self.plans.append(wp_id)

    def task_key(self, wbs_id: str) -> str:
        with tx() as cur:
            cur.execute(
                "select task_key from wbs_item where project_id = %s and wbs_id = %s and active",
                (PID, wbs_id),
            )
            return str(cur.fetchone()["task_key"])


@pytest.fixture
def env():
    with tx() as cur:
        saved = fetch_all(
            cur,
            "select id, is_current from work_product "
            "where project_id = %s and type = 'PROJECT_PLAN'",
            (PID,),
        )
        _clean(cur)
    e = Env()
    yield e
    with tx() as cur:
        _clean(cur)
        cur.execute("delete from work_product where id = any(%s::uuid[])", (e.plans,))
        for r in saved:
            cur.execute(
                "update work_product set is_current = %s where id = %s", (r["is_current"], r["id"])
            )


def _base(pid: str = PID) -> str:
    return f"/api/projects/{pid}/wbs/designated-deliverables"


def _designate(client, token, task_key, name="시험결과서", **extra):
    body = {"taskKey": task_key, "name": name, **extra}
    return client.post(_base(), json=body, headers=_auth(token))


def _screen(client, token) -> dict:
    res = client.get(f"/api/projects/{PID}/wbs/deliverables", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


def _row(screen: dict, wbs_id: str) -> dict:
    return next(i for i in screen["items"] if i["wbsId"] == wbs_id)


def _upload(client, token, designated_id: str, name: str, data: bytes) -> dict:
    res = client.post(
        f"/api/projects/{PID}/documents",
        files={"file": (name, data, "application/octet-stream")},
        data={"designatedId": designated_id},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    return res.json()


def _confirm(client, token, doc_id: str, version: str) -> str:
    res = client.post(
        f"/api/documents/{doc_id}/draft/confirm",
        json={"type": "TEST_REPORT", "title": "통합 시험결과서", "version": version,
              "requirements": []},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["workProductId"]


# ---------------------------------------------------------------- AC-033-1


@requires_db
def test_AC_033_1_WBS_가_없으면_먼저_등록하라고_한다(client, client_token, env):
    res = _designate(client, client_token("r2"), str(uuid.uuid4()))
    assert res.status_code == 400, res.text
    assert "먼저 WBS 를 등록하세요" in res.json()["message"]


@requires_db
def test_AC_033_1_발주기관만_지정하고_용역사_관리자는_거절된다(client, client_token, env):
    """UC-033-S03. 역할 검사는 대상 조회보다 먼저다."""
    env.load(BASE)
    key = env.task_key("2.1")
    for user in ("r3", "r1"):
        res = _designate(client, client_token(user), key)
        assert res.status_code == 403, res.text
    assert "플랫폼 관리자는" in _designate(client, client_token("r1"), key).json()["message"]

    po = client_token("r2")
    assert _designate(client, po, key, name="  ").status_code == 400
    assert _designate(client, po, key, productType="NOPE").status_code == 400
    assert _designate(client, po, str(uuid.uuid4())).status_code == 400  # 지금 WBS 에 없는 작업
    res = _designate(client, po, key, productType="TEST_REPORT", guide="결함 0건이면 통과로 적는다")
    assert res.status_code == 201, res.text

    row = _row(_screen(client, po), "2.1")
    [item] = row["designated"]
    assert (item["name"], item["productType"], item["status"]) == (
        "시험결과서", "TEST_REPORT", "MISSING"
    )
    assert item["needsRedesignation"] is False and item["wbsIdAt"] == "2.1"
    # 판정이 산출물 열(「시험결과서」) 대신 지정 항목으로 바뀐다
    assert (row["status"], row["rule"]) == ("OVERDUE", "DESIGNATED")


# ---------------------------------------------------------------- AC-033-2 · AC-033-3


@requires_db
def test_UC_033_S01_지정_양식_제출_반려_재제출_승인(client, client_token, env):
    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    did = _designate(client, po, env.task_key("2.1"), productType="TEST_REPORT").json()["id"]

    # 양식: 발주기관만 올리고, 누구나 받는다. 제출본이 아니다
    template = _xlsx("양식")
    up = client.post(
        f"{_base()}/{did}/template",
        files={"file": ("시험결과서-양식.xlsx", template, "application/octet-stream")},
        headers=_auth(pm),
    )
    assert up.status_code == 403
    up = client.post(
        f"{_base()}/{did}/template",
        files={"file": ("시험결과서-양식.xlsx", template, "application/octet-stream")},
        headers=_auth(po),
    )
    assert up.status_code == 204, up.text
    got = client.get(f"{_base()}/{did}/template", headers=_auth(pm))
    assert got.status_code == 200 and got.content == template
    row = _row(_screen(client, pm), "2.1")
    assert row["designated"][0]["templateFileName"] == "시험결과서-양식.xlsx"
    assert row["designated"][0]["status"] == "MISSING" and row["status"] == "OVERDUE"
    assert row["documents"] == []  # 양식은 문서 목록에도 없다

    # 올리기만 하면 등록이다. 확정해야 제출이다(DEC-14)
    doc1 = _upload(client, pm, did, "통합시험결과-v1.xlsx", _xlsx("v1"))
    row = _row(_screen(client, pm), "2.1")
    assert row["designated"][0]["status"] == "REGISTERED" and row["status"] == "OVERDUE"
    assert row["designated"][0]["versions"][0]["submit"] == "READY"  # 제출하러 갈 수 있다
    detail = client.get(f"/api/documents/{doc1['id']}", headers=_auth(pm)).json()
    assert detail["designatedName"] == "시험결과서" and detail["draftStatus"] == "PROPOSED"
    wp1 = _confirm(client, pm, doc1["id"], "1.0")
    row = _row(_screen(client, po), "2.1")
    assert row["designated"][0]["status"] == "SUBMITTED"
    assert (row["status"], row["ref"]) == ("SUBMITTED", "지정 산출물 1건 중 1건 제출")
    assert [d["confirmed"] for d in row["documents"]] == [True]  # 유형을 바꿔 확정해도 확정

    # 반려 사유가 항목 버전에 보인다
    res = client.post(f"/api/projects/{PID}/work-products/{wp1}/reject",
                      json={"reason": "결함 목록 누락"}, headers=_auth(po))
    assert res.status_code == 204, res.text
    v = _row(_screen(client, pm), "2.1")["designated"][0]
    assert v["status"] == "REJECTED" and v["versions"][0]["rejectReason"] == "결함 목록 누락"

    doc2 = _upload(client, pm, did, "통합시험결과-v2.xlsx", _xlsx("v2"))
    wp2 = _confirm(client, pm, doc2["id"], "1.1")
    assert client.post(f"/api/projects/{PID}/work-products/{wp2}/approve",
                       json={}, headers=_auth(po)).status_code == 204
    item = _row(_screen(client, pm), "2.1")["designated"][0]
    assert item["status"] == "APPROVED"
    assert [x["state"] for x in item["versions"]] == ["APPROVED", "REJECTED"]
    assert [x["version"] for x in item["versions"]] == ["1.1", "1.0"]
    assert item["versions"][1]["rejectReason"] == "결함 목록 누락"  # 지난 사유도 남는다


@requires_db
def test_UC_033_E2_다른_유형_제출은_막지_않고_항목_상태도_안_바꾼다(client, client_token, env):
    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    _designate(client, po, env.task_key("2.1"), productType="TEST_REPORT")
    res = client.post(
        f"/api/projects/{PID}/documents",
        files={"file": ("다른자료.xlsx", _xlsx("기타"), "application/octet-stream")},
        data={"wbsId": "2.1"},
        headers=_auth(pm),
    )
    assert res.status_code == 201, res.text
    _confirm(client, pm, res.json()["id"], "9.0")
    row = _row(_screen(client, po), "2.1")
    assert row["designated"][0]["status"] == "MISSING"
    assert row["status"] == "OVERDUE"  # 지정 항목이 안 왔으니 작업 판정도 제출이 아니다


# ---------------------------------------------------------------- AC-033-4


@requires_db
def test_UC_033_S02_정체가_이어지면_지정이_따라가고_끊기면_재지정_필요(client, client_token, env):
    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    did = _designate(client, po, env.task_key("2.1")).json()["id"]
    doc = _upload(client, pm, did, "통합시험결과-v1.xlsx", _xlsx("v1"))
    _confirm(client, pm, doc["id"], "1.0")

    # 실적만 바뀐 재업로드: 정체가 이어진다
    env.load([BASE[0], BASE[1], ("2.1", "통합 시험", "시험결과서", 0.5, 0.4)])
    row = _row(_screen(client, po), "2.1")
    assert [d["id"] for d in row["designated"]] == [did]

    # 작업명이 바뀌어 정체가 끊긴다: 지정은 지우지 않고 재지정 필요로 모은다
    env.load([BASE[0], BASE[1], ("2.1", "인수 시험", "시험결과서", 0.5, 0.0)])
    screen = _screen(client, po)
    assert _row(screen, "2.1")["designated"] == []
    [orphan] = screen["redesignation"]
    assert orphan["id"] == did and orphan["needsRedesignation"] is True
    assert orphan["taskNameAt"] == "통합 시험" and orphan["status"] == "SUBMITTED"
    assert len(orphan["versions"]) == 1  # 제출 이력은 남는다

    refused = client.post(
        f"/api/projects/{PID}/documents",
        files={"file": ("v2.xlsx", _xlsx("v2"), "application/octet-stream")},
        data={"designatedId": did}, headers=_auth(pm),
    )
    assert refused.status_code == 400 and "재지정" in refused.json()["message"]

    # 발주기관이 새 작업으로 다시 정한다
    res = client.patch(f"{_base()}/{did}", json={"taskKey": env.task_key("2.1")},
                       headers=_auth(po))
    assert res.status_code == 204, res.text
    screen = _screen(client, pm)
    assert screen["redesignation"] == []
    assert [d["id"] for d in _row(screen, "2.1")["designated"]] == [did]
    kinds = [e["kind"] for e in client.get(f"{_base()}/{did}/history", headers=_auth(pm)).json()]
    assert kinds == ["CREATED", "REASSIGNED"]


@requires_db
def test_지정을_거둬도_행과_제출_이력은_남는다(client, client_token, env):
    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    did = _designate(client, po, env.task_key("2.1")).json()["id"]
    assert client.patch(f"{_base()}/{did}", json={"name": "시험결과서(최종)"},
                        headers=_auth(po)).status_code == 204
    _upload(client, pm, did, "결과.xlsx", _xlsx("r"))
    assert client.delete(f"{_base()}/{did}", headers=_auth(pm)).status_code == 403
    assert client.delete(f"{_base()}/{did}", headers=_auth(po)).status_code == 204

    row = _row(_screen(client, po), "2.1")
    assert row["designated"] == [] and row["rule"] != "DESIGNATED"
    events = client.get(f"{_base()}/{did}/history", headers=_auth(po)).json()
    assert [e["kind"] for e in events] == ["CREATED", "UPDATED", "REMOVED"]
    assert events[1]["detail"]["after"] == {"name": "시험결과서(최종)"}
    with tx() as cur:
        cur.execute(
            "select count(*) as n from document_upload where designated_deliverable_id = %s",
            (did,),
        )
        assert cur.fetchone()["n"] == 1
    assert client.delete(f"{_base()}/{did}", headers=_auth(po)).status_code == 404
    assert client.get(f"{_base()}/not-a-uuid/history", headers=_auth(po)).status_code == 404
