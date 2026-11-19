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


def test_올라오면_제출이고_항목_상태는_가장_최근_것이_정한다():
    """V70: 승인 단위는 올라온 산출물이다. 양식 자리에 올라오면 제출, 발주기관이 승인·반려한다."""
    assert designation.version_state({"review_status": None}) == "SUBMITTED"
    assert designation.version_state({"review_status": "SUBMITTED"}) == "SUBMITTED"
    assert designation.version_state({"review_status": "APPROVED"}) == "APPROVED"
    assert designation.version_state({"review_status": "REJECTED"}) == "REJECTED"
    assert designation.item_status([]) == "MISSING"
    assert designation.item_status(["SUBMITTED", "REJECTED"]) == "SUBMITTED"
    assert designation.item_status(["APPROVED", "REJECTED"]) == "APPROVED"
    assert designation.submit_readiness({"review_status": None}) is None
    assert designation.is_submitted("REJECTED") and not designation.is_submitted("MISSING")


def _item(wbs_id: str, deliverable_text: str | None, end: date, key: str) -> dict:
    return {"id": key, "wbs_id": wbs_id, "deliverable": deliverable_text, "weight": 0.5,
            "end_on": end, "task_key": key}


def test_예상_산출물_항목으로_판정한다():
    """예상 산출물(WBS 자동 + 요청)이 다 안 왔으면 제출이 아니다(UC-033 4단계, 11-19)."""
    items = [
        _item("1.1", "착수보고서", date(2026, 9, 30), "k1"),
        _item("1.2", None, date(2026, 9, 1), "k2"),  # 산출물 열이 비어도 요청으로 판정한다
        _item("1.3", None, date(2026, 9, 30), "k3"),
        _item("1.4", "보고서", date(2026, 9, 30), "k4"),  # 예상 산출물 행이 없으면 판정 없음
    ]
    cover = {
        "k1": designation.Coverage(3, 1),
        "k2": designation.Coverage(1, 0),
        "k3": designation.Coverage(1, 1),
    }
    out = {j.wbs_id: j for j in deliverable.judge(items, today=TODAY, designated=cover)}
    assert (out["1.1"].status, out["1.1"].rule) == ("MISSING", "DESIGNATED")
    assert out["1.1"].ref == "예상 산출물 3건 중 1건 제출"
    assert out["1.2"].status == "OVERDUE"
    assert (out["1.3"].status, out["1.3"].ref) == ("SUBMITTED", "예상 산출물 1건 중 1건 제출")
    assert out["1.4"].status == "NONE"


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
    [item] = _req(row)
    assert (item["name"], item["productType"], item["status"]) == (
        "시험결과서", "TEST_REPORT", "MISSING"
    )
    assert item["needsRedesignation"] is False and item["wbsIdAt"] == "2.1"
    # 판정이 산출물 열(「시험결과서」) 대신 지정 항목으로 바뀐다
    assert (row["status"], row["rule"]) == ("OVERDUE", "DESIGNATED")


# ---------------------------------------------------------------- AC-033-2 · AC-033-3


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
    assert res.status_code == 201, res.text  # 작업에 올리면 읽은 뒤 바로 제출이다(11-18)
    row = _row(_screen(client, po), "2.1")
    assert _req(row)[0]["status"] == "MISSING"
    assert row["status"] == "OVERDUE"  # 지정 항목이 안 왔으니 작업 판정도 제출이 아니다


# ---------------------------------------------------------------- AC-033-4


@requires_db
def test_UC_033_S02_정체가_이어지면_지정이_따라가고_끊기면_재지정_필요(client, client_token, env):
    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    did = _designate(client, po, env.task_key("2.1"), productType="TEST_REPORT").json()["id"]
    _upload(client, pm, did, "통합시험결과-v1.xlsx", _xlsx("v1"))  # 올리면 제출이다(11-18)

    # 실적만 바뀐 재업로드: 정체가 이어진다
    env.load([BASE[0], BASE[1], ("2.1", "통합 시험", "시험결과서", 0.5, 0.4)])
    row = _row(_screen(client, po), "2.1")
    assert [d["id"] for d in _req(row)] == [did]

    # 작업명이 바뀌어 정체가 끊긴다: 지정은 지우지 않고 재지정 필요로 모은다
    env.load([BASE[0], BASE[1], ("2.1", "인수 시험", "시험결과서", 0.5, 0.0)])
    screen = _screen(client, po)
    assert _req(_row(screen, "2.1")) == []  # 새 작업에는 WBS 자동 항목만 생긴다
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
    assert [d["id"] for d in _req(_row(screen, "2.1"))] == [did]
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
    assert _req(row) == []  # WBS 자동 항목은 남는다
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


def _req(row: dict) -> list[dict]:
    """발주기관이 요청한 항목만. WBS 산출물 열에서 저절로 만든 항목(V73)은 뺀다."""
    return [d for d in row["designated"] if d.get("origin") != "WBS"]


def _review(client, token, doc_id: str, action: str, reason: str | None = None):
    body = {"reason": reason} if reason else {}
    return client.post(f"/api/projects/{PID}/documents/{doc_id}/{action}", json=body,
                       headers=_auth(token))


@requires_db
def test_UC_033_S01_양식_올리기_반려_다시_올리기_승인(client, client_token, env):
    """V70: 양식 자리에 올리면 바로 제출이다. 발주기관은 올라온 산출물 하나하나를 승인·반려한다."""
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
    assert client.get(f"{_base()}/{did}/template", headers=_auth(pm)).content == template
    row = _row(_screen(client, pm), "2.1")
    assert _req(row)[0]["status"] == "MISSING" and row["status"] == "OVERDUE"
    assert row["documents"] == [] and row["review"] == []  # 양식은 산출물이 아니다

    doc1 = _upload(client, pm, did, "통합시험결과-v1.xlsx", _xlsx("v1"))
    row = _row(_screen(client, po), "2.1")
    assert _req(row)[0]["status"] == "SUBMITTED"
    # WBS 산출물(시험결과서)도 예상 산출물이라 아직 다 낸 것이 아니다(11-19)
    assert (row["status"], row["ref"]) == ("OVERDUE", "예상 산출물 2건 중 1건 제출")
    assert [(r["documentId"], r["status"], r["name"]) for r in row["review"]] == [
        (doc1["id"], "SUBMITTED", "시험결과서")
    ]

    # 반려는 발주기관만, 사유가 필요하다
    assert _review(client, pm, doc1["id"], "approve").status_code == 403
    assert _review(client, po, doc1["id"], "reject").status_code == 400
    assert _review(client, po, doc1["id"], "reject", "결함 목록 누락").status_code == 204
    v = _req(_row(_screen(client, pm), "2.1"))[0]
    assert v["status"] == "REJECTED" and v["versions"][0]["rejectReason"] == "결함 목록 누락"

    # 다시 올리면 새 판이다. 지난 판은 latest 가 아니다
    doc2 = _upload(client, pm, did, "통합시험결과-v2.xlsx", _xlsx("v2"))
    assert _review(client, po, doc2["id"], "approve").status_code == 204
    row = _row(_screen(client, pm), "2.1")
    item = _req(row)[0]
    assert item["status"] == "APPROVED"
    assert [x["state"] for x in item["versions"]] == ["APPROVED", "REJECTED"]
    assert [(r["documentId"], r["latest"]) for r in row["review"]] == [
        (doc2["id"], True), (doc1["id"], False)
    ]


@requires_db
def test_산출물_진척은_양식_기준으로_제출률과_승인률을_센다(client, client_token, env):
    """작업에 요청 산출물이 2개면 분모 2, 하나만 올라와도 1건 제출이다. 승인은 따로 센다.
    WBS 산출물 열의 이름도 한 건이다. 요청이 있는 작업도 둘 다 센다(11-19). BASE 는 세 작업 모두
    WBS 산출물이 있어 3건 + 요청 3건 = 6건이다."""
    from app.dashboard import service as dashboard_service

    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    a = _designate(client, po, env.task_key("2.1"), name="시험결과서").json()["id"]
    _designate(client, po, env.task_key("2.1"), name="결함 목록")
    _designate(client, po, env.task_key("1.1"), name="착수보고서")

    def units() -> tuple[int, int, int]:
        with tx() as cur:
            return dashboard_service.deliverable_units(cur, PID, TODAY)

    assert units() == (0, 0, 6)
    doc = _upload(client, pm, a, "결과.xlsx", _xlsx("결과"))
    assert units() == (1, 0, 6)
    assert _review(client, po, doc["id"], "approve").status_code == 204
    assert units() == (1, 1, 6)

    res = client.post(
        f"/api/projects/{PID}/documents",
        files={"file": ("회의.xlsx", _xlsx("회의"), "application/octet-stream")},
        data={"wbsId": "1.2"}, headers=_auth(pm),
    )
    assert res.status_code == 201, res.text
    plain = _row(_screen(client, po), "1.2")["review"]
    assert [(r["status"], r["fileName"]) for r in plain] == [("SUBMITTED", "회의.xlsx")]
    assert units() == (2, 1, 6)  # 요청 없이 작업에 올리면 1.2 의 WBS 자동 항목에 잇는다
    assert _review(client, po, res.json()["id"], "approve").status_code == 204
    assert units() == (2, 2, 6)

    # 시맨틱 지표(카드)도 같은 셈이다
    def card(measure: str) -> float:
        body = client.post("/api/widgets/preview", json={"spec": {
            "template": "STAT_CARD", "title": "t",
            "query": {"measure": measure, "dimensions": [], "filters": [],
                      "projectScope": [PID], "limit": None},
            "options": None}}, headers=_auth(po)).json()
        row = body["rows"][0] if body["rows"] else body["total"]
        return float(row["values"]["value"])

    assert card("deliverable_submission_rate") == 33.33
    assert card("deliverable_approval_rate") == 33.33


@requires_db
def test_저장소_WBS_가_있으면_올린_문서로_계획서를_바꾸지_않는다(client, client_token, env):
    """11-18 개발 DB 에서 산출물로 올린 발표자료가 사업수행계획서로 확정돼 저장소 WBS 가 현행에서
    내려갔다. 저장소 WBS 가 원천이면 올린 문서를 사업수행계획서로 확정하지 않는다."""
    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    did = _designate(client, po, env.task_key("2.1"), productType="PROJECT_PLAN").json()["id"]
    doc = _upload(client, pm, did, "발표.xlsx", _xlsx("발표"))
    res = client.post(
        f"/api/documents/{doc['id']}/draft/confirm",
        json={"type": "PROJECT_PLAN", "title": "발표", "version": "9.0", "requirements": []},
        headers=_auth(pm),
    )
    assert res.status_code == 409 and res.json()["code"] == "PLAN_FROM_REPOSITORY", res.text
    with tx() as cur:
        cur.execute(
            "select source_kind from work_product "
            "where project_id = %s and type = 'PROJECT_PLAN' and is_current",
            (PID,),
        )
        assert cur.fetchone()["source_kind"] == "TOOL"


@requires_db
def test_저장소_파일을_골라_올리면_그_작업의_산출물이_된다(client, client_token, env, monkeypatch):
    """11-19: 저장소에 커밋한 산출물은 저절로 제출이 아니다. 올리기에서 골라야 제출이고, 고른
    파일은 올린 문서와 똑같이 업로드 자료·승인 대상이 된다. 트리에 없는 경로는 받지 않는다."""
    import base64
    import json

    from app.document import repo_source

    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    data = _xlsx("저장소 설계서")
    calls: list[tuple[str, str | None]] = []

    class FakeConnector:
        def fetch_file(self, base_url, target, secret, path, ref=None):
            calls.append((path, ref))
            return {"path": path, "content": base64.b64encode(data).decode("ascii")}

    monkeypatch.setattr(repo_source.port, "get_connector", lambda tool: FakeConnector())
    monkeypatch.setattr(repo_source.crypto, "decrypt", lambda value: "token")
    cid = str(uuid.uuid4())
    tree = {"sha": "t1", "commit": "c1", "paths": ["docs/설계서.xlsx", "app/main.py"]}
    with tx() as cur:
        org = fetch_all(cur, "select id from organization where type = 'CONTRACTOR' limit 1")[0]
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'GITHUB', '저장소 고르기', 'https://api.github.invalid/', %s,
                    'x', 'x', 'ACTIVE')
            """,
            (cid, PID, org["id"], f"pick/{cid}"),
        )
        cur.execute(
            "insert into raw_artifact (tool_connection_id, external_id, object_kind, payload_jsonb,"
            " content_hash) values (%s, 'tree:HEAD', 'tree', %s, %s)",
            (cid, json.dumps(tree), "0" * 64),
        )
    try:
        # 문서 형식만 고를 수 있다
        res = client.get(f"/api/projects/{PID}/repository-files", headers=_auth(pm))
        assert res.status_code == 200 and res.json()["paths"] == ["docs/설계서.xlsx"], res.text
        # 커밋만 한 상태로는 제출이 아니다
        assert _row(_screen(client, po), "1.2")["status"] in ("MISSING", "OVERDUE")

        bad = client.post(f"/api/projects/{PID}/documents/from-repository",
                          json={"path": "docs/없는.xlsx", "wbsId": "1.2"}, headers=_auth(pm))
        assert bad.status_code == 400 and calls == []

        res = client.post(f"/api/projects/{PID}/documents/from-repository",
                          json={"path": "docs/설계서.xlsx", "wbsId": "1.2"}, headers=_auth(pm))
        assert res.status_code == 201, res.text
        assert calls == [("docs/설계서.xlsx", "c1")]  # 수집한 커밋의 본문이다
        row = _row(_screen(client, po), "1.2")
        assert row["status"] == "SUBMITTED"
        assert [d["fileName"] for d in row["documents"]] == ["설계서.xlsx"]
        review = [(r["status"], r["fileName"]) for r in row["review"]]
        assert review == [("SUBMITTED", "설계서.xlsx")]
    finally:
        with tx() as cur:
            cur.execute("delete from tool_connection where id = %s", (cid,))


@requires_db
def test_29110_충족_현황은_계획_여부와_제출_승인을_네_상태로_가른다(client, client_token, env):
    """11-19: 인도 점검표 대신 22종 충족 현황. 예상 산출물에 없으면 「계획 없음」이다.
    분류는 발주사가 정한 것 > 이름(22종 이름·별칭) > 올라온 문서 분류 순으로 본다."""
    env.load(BASE)
    po, pm = client_token("r2"), client_token("r3")
    did = _designate(client, po, env.task_key("1.1"), name="착수 자료",
                     productType="REQUIREMENTS_SPEC").json()["id"]

    def coverage() -> dict[str, dict]:
        res = client.get(f"/api/projects/{PID}/wbs/iso29110", headers=_auth(pm))
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["items"]) == 22 and sum(body["counts"].values()) == 22
        return {i["type"]: i for i in body["items"]}

    c = coverage()
    assert c["TEST_REPORT"]["status"] == "PLANNED"  # 2.1 WBS 「시험결과서」 이름으로
    assert [(s["wbsId"], s["origin"]) for s in c["TEST_REPORT"]["sources"]] == [("2.1", "WBS")]
    assert c["REQUIREMENTS_SPEC"]["status"] == "PLANNED"  # 발주사 요청의 분류로
    assert c["SOFTWARE_DESIGN"]["status"] == "UNPLANNED" and c["SOFTWARE_DESIGN"]["sources"] == []
    assert c["REQUIREMENTS_SPEC"]["process"] == "SI" and c["PROJECT_PLAN"]["process"] == "PM"

    doc = _upload(client, pm, did, "요구사항.xlsx", _xlsx("요구"))
    assert coverage()["REQUIREMENTS_SPEC"]["status"] == "SUBMITTED"
    assert _review(client, po, doc["id"], "approve").status_code == 204
    assert coverage()["REQUIREMENTS_SPEC"]["status"] == "APPROVED"
