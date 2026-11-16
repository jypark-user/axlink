"""WBS 작업 완료 확인과 완료 확인율 (ARC-019) 수용시험.

계획서 버전은 파일 대신 wbs_repository.replace_plan 으로 직접 싣는다. 현행 계획서 산출물 id 와
적재 버전이 같으면 화면·스냅샷이 그 행을 그대로 읽는다(dashboard.service._load_plan).
"""

import uuid
from datetime import date

import pytest

from app.dashboard import wbs
from app.db import fetch_all, fetch_one, tx
from app.review import repository as review_repo
from app.standard import wbs_repository
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
OTHER_CLIENT_ORG = "a0000000-0000-4000-8000-000000000001"
D = date(2026, 9, 1)

BASE = [
    ("1.1", "착수보고", "착수보고서.md", 0.2, 1.0),
    ("1.2", "중간보고", "중간보고서.md", 0.3, 0.5),
    ("2.1", "연계 수집", "커넥터.py", 0.5, 0.0),
]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


class Env:
    def __init__(self):
        self.plans: list[str] = []

    def load(self, rows, groups=("1", "2"), *, rows_now: bool = True) -> str:
        """계획서 새 버전을 현행으로 두고 행을 싣는다.

        rows_now=False 면 수집 직후처럼 산출물만 현행으로 바꾸고 행은 그대로 둔다.
        """
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
                (wp_id, PID, f"v{len(self.plans) + 1}"),
            )
            if rows_now:
                wbs_repository.replace_plan(cur, PID, wp_id, _plan(rows, groups))
        self.plans.append(wp_id)
        return wp_id

    def item(self, wbs_id: str) -> dict:
        with tx() as cur:
            return fetch_one(
                cur, "select * from wbs_item where project_id = %s and wbs_id = %s", (PID, wbs_id)
            )


def _clean(cur):
    cur.execute("delete from wbs_completion_record where project_id = %s", (PID,))
    cur.execute("delete from review_request where project_id = %s", (PID,))
    cur.execute("delete from wbs_item where project_id = %s", (PID,))


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


# ---------------------------------------------------------------- 도우미


def _summary(client, token) -> dict:
    res = client.get(f"/api/projects/{PID}/wbs/completion", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


def _item(summary: dict, wbs_id: str) -> dict:
    return next(i for i in summary["items"] if i["wbsId"] == wbs_id)


SCOPE = "착수보고 자료 제출과 보고회 개최"


def _request(client, token, wbs_id, *, purpose="WBS_COMPLETION", scope=SCOPE):
    return client.post(
        f"/api/projects/{PID}/review-requests",
        json={"targetType": "WBS_ITEM", "targetKey": wbs_id, "title": f"{wbs_id} 완료 확인",
              "purpose": purpose, "completionScope": scope},
        headers=_auth(token),
    )


EVIDENCE = [{"kind": "MEETING", "ref": "착수보고회 회의록 2026-08-11", "note": "발주기관 참석"}]


def _report(client, token, rid, evidence=EVIDENCE):
    return client.post(
        f"/api/review-requests/{rid}/report",
        json={"body": "착수보고를 마쳤습니다.", "evidence": evidence},
        headers=_auth(token),
    )


def _confirm(client, token, rid, ack=True):
    return client.post(
        f"/api/review-requests/{rid}/confirm",
        json={"acknowledgeCompletion": ack, "note": "보고회 참석 확인"},
        headers=_auth(token),
    )


def _confirmed(client, client_token, wbs_id) -> str:
    """요청 → 근거 보고 → 완료 확인까지. 요청 id 를 돌려준다."""
    r2, r3 = client_token("r2"), client_token("r3")
    created = _request(client, r2, wbs_id)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    assert _report(client, r3, rid).status_code == 200
    res = _confirm(client, r2, rid)
    assert res.status_code == 200, res.text
    return rid


def _records(rid: str) -> list[dict]:
    with tx() as cur:
        return review_repo.completion_records(cur, rid)


# ---------------------------------------------------------------- 산정


@requires_db
def test_AT3_WBS_가_없으면_산출_불가_있고_확인이_없으면_0(client, client_token, env):
    token = client_token("r2")
    empty = _summary(client, token)
    assert empty["completionRate"] is None and empty["reportedPct"] is None
    assert empty["leafCount"] == 0

    env.load(BASE)
    s = _summary(client, token)
    assert s["completionRate"] == 0.0
    assert "완료 확인 기록 기준" in s["basis"] and "현재 WBS" in s["basis"]
    assert s["reportedPct"] == pytest.approx(0.2 * 1.0 + 0.3 * 0.5)
    assert s["reported100Count"] == 1 and s["reported100Pending"] == 1


@requires_db
def test_AT3b_확인이_없으면_시맨틱_지표도_0_이다(client, client_token, env):
    """화면은 0% 인데 지표는 값 없음이라 AI 가 "값이 아직 없다" 고 답했다(V48)."""
    token = client_token("r2")
    spec = {"template": "STAT_CARD", "title": "완료 확인율",
            "query": {"measure": "wbs_completion_rate", "dimensions": [],
                      "filters": [], "projectScope": [PID]},
            "options": {}}

    def value():
        res = client.post("/api/widgets/preview", json={"spec": spec}, headers=_auth(token))
        assert res.status_code == 200, res.text
        data = res.json()
        row = data["total"] or (data["rows"][0] if data["rows"] else None)
        return None if row is None else row["values"]["value"]

    assert value() is None  # 말단 작업이 없으면 산출 불가
    env.load(BASE)
    assert value() == 0.0


@requires_db
def test_AT1_일반_확인_요청은_완료_확인율에_들지_않는다(client, client_token, env):
    env.load(BASE)
    r2, r3 = client_token("r2"), client_token("r3")
    created = _request(client, r2, "1.1", purpose="GENERAL", scope=None)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    assert created.json()["purpose"] == "GENERAL"
    assert client.post(f"/api/review-requests/{rid}/report", json={"body": "했습니다"},
                       headers=_auth(r3)).status_code == 200
    assert client.post(f"/api/review-requests/{rid}/confirm", headers=_auth(r2)).status_code == 200
    s = _summary(client, r2)
    assert s["completionRate"] == 0.0 and s["confirmedCount"] == 0
    assert _records(rid) == []


@requires_db
def test_AT2_AT10_완료_확인은_그_작업_가중치만_더하고_지표와_같다(client, client_token, env):
    env.load(BASE)
    rid = _confirmed(client, client_token, "1.1")
    token = client_token("r2")
    s = _summary(client, token)
    assert s["completionRate"] == pytest.approx(0.2)
    item = _item(s, "1.1")
    assert item["completionStatus"] == "CONFIRMED" and item["confirmedBy"]
    assert item["weightAtConfirm"] == pytest.approx(0.2) and item["planVersionAtConfirm"] == "v1"

    # 시맨틱 지표(질의·위젯)가 같은 뷰에서 같은 값을 낸다
    res = client.post(
        "/api/widgets/preview",
        json={"spec": {"template": "STAT_CARD", "title": "완료 확인율",
                       "query": {"measure": "wbs_completion_rate", "dimensions": [],
                                 "filters": [], "projectScope": [PID]},
                       "options": {}}},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    row = data["total"] or data["rows"][0]
    assert row["values"]["value"] == pytest.approx(20.0)

    # 기록에 그때의 작업·보고 실적·근거·확인자가 고정됐다
    [rec] = _records(rid)
    assert rec["kind"] == "CONFIRMED" and float(rec["reported_actual"]) == 1.0
    assert rec["item_json"]["name"] == "착수보고"
    assert rec["completion_scope"] == "착수보고 자료 제출과 보고회 개최"
    facts = rec["evidence_json"]["facts"]
    # 산출물 항목이 없으니 제출·승인은 모른다. 파일 대조 결과로 대신하지 않는다
    assert facts["submission"] == "UNKNOWN" and facts["approval"] == "UNKNOWN"
    assert rec["evidence_json"]["reported"] == EVIDENCE


@requires_db
def test_AT4_보고_50퍼센트_작업도_확인하면_반영되고_보고값은_그대로(client, client_token, env):
    env.load(BASE)
    rid = _confirmed(client, client_token, "1.2")
    s = _summary(client, client_token("r2"))
    assert s["completionRate"] == pytest.approx(0.3)
    assert float(env.item("1.2")["actual"]) == 0.5
    assert float(_records(rid)[0]["reported_actual"]) == 0.5


@requires_db
def test_AT5_AT8_근거가_개정돼도_기록은_남고_승인만으로는_안_바뀐다(client, client_token, env):
    env.load(BASE)
    rid = _confirmed(client, client_token, "1.1")
    before = _records(rid)[0]["evidence_json"]
    # 확인 뒤 같은 이름의 산출물이 올라오고 발주기관이 승인했다
    with tx() as cur:
        wp = fetch_one(
            cur,
            "select id, status, version, title from work_product "
            "where project_id = %s and type = 'MEETING_RECORD' and is_current",
            (PID,),
        )
        cur.execute(
            "update work_product set status = 'APPROVED', title = '착수보고서', version = 'R2', "
            "approved_at = now() where id = %s",
            (wp["id"],),
        )
    try:
        s = _summary(client, client_token("r2"))
        item = _item(s, "1.1")
        assert item["fileCheck"] == "MATCHED" and item["submission"] == "SUBMITTED"
        assert item["approval"] == "APPROVED" and item["productVersion"] == "R2"
        assert item["evidenceRevised"] is True  # 확인 후 근거 개정됨
        assert item["completionStatus"] == "CONFIRMED"
        assert s["completionRate"] == pytest.approx(0.2)  # 승인이 율을 바꾸지 않는다
        assert _records(rid)[0]["evidence_json"] == before  # 지난 기록 불변

        # 다른 작업(2.1)의 산출물이 승인돼도 그 작업은 확인되지 않는다
        assert _item(s, "2.1")["completionStatus"] == "NONE"
    finally:
        with tx() as cur:
            cur.execute(
                "update work_product set status = %s, version = %s, title = %s, "
                "approved_at = null where id = %s",
                (wp["status"], wp["version"], wp["title"], wp["id"]),
            )


@requires_db
def test_AT9_철회는_한_줄을_더하고_분자에서_뺀다(client, client_token, env):
    env.load(BASE)
    rid = _confirmed(client, client_token, "1.1")
    r2 = client_token("r2")
    res = client.post(f"/api/review-requests/{rid}/withdraw-completion",
                      json={"reason": "회의록 서명 누락"}, headers=_auth(r2))
    assert res.status_code == 200, res.text
    kinds = [r["kind"] for r in res.json()["completionRecords"]]
    assert kinds == ["CONFIRMED", "WITHDRAWN"]
    s = _summary(client, r2)
    assert s["completionRate"] == 0.0 and _item(s, "1.1")["completionStatus"] == "WITHDRAWN"
    # 두 번 철회되지 않는다
    again = client.post(f"/api/review-requests/{rid}/withdraw-completion",
                        json={"reason": "x"}, headers=_auth(r2))
    assert again.status_code == 409
    assert len(_records(rid)) == 2
    # 철회 뒤에는 새 요청으로 다시 확인할 수 있다
    rid2 = _confirmed(client, client_token, "1.1")
    assert rid2 != rid
    assert _summary(client, r2)["completionRate"] == pytest.approx(0.2)


# ---------------------------------------------------------------- 작업 식별과 범위


@requires_db
def test_AT6_범위가_바뀌면_재확인이고_이전_기록은_남는다(client, client_token, env):
    env.load(BASE)
    rid = _confirmed(client, client_token, "1.1")
    key = env.item("1.1")["task_key"]
    env.load([("1.1", "착수보고", "착수보고서_v2.pptx", 0.2, 1.0)] + BASE[1:])
    assert env.item("1.1")["task_key"] == key  # 같은 작업이다(번호·이름 동일)
    s = _summary(client, client_token("r2"))
    assert _item(s, "1.1")["completionStatus"] == "RECONFIRM"
    assert s["completionRate"] == 0.0 and s["reconfirmCount"] == 1
    assert len(_records(rid)) == 1


@pytest.mark.parametrize(
    ("second", "groups", "reason"),
    [
        # 이름이 바뀐 같은 번호. 다른 작업일 수 있다
        ([("1.1", "착수 회의", "착수보고서.md", 0.2, 1.0)] + BASE[1:], ("1", "2"), "RENAMED"),
        # 같은 이름이 번호를 바꿔 들어옴(동명 작업 교차). 1.1 자리는 남의 이름이다
        ([("1.1", "중간보고", "중간보고서.md", 0.2, 1.0),
          ("1.2", "착수보고", "착수보고서.md", 0.3, 0.5), BASE[2]], ("1", "2"), "RENAMED"),
        # 분할. 1.1 이 묶음이 되고 아래에 말단 둘
        ([("1.1.1", "착수보고 자료", "착수보고서.md", 0.1, 1.0),
          ("1.1.2", "착수보고회", "회의록.md", 0.1, 1.0)] + BASE[1:],
         ("1", "1.1", "2"), "LEAF_CHANGED"),
        # 병합. 1.2 가 빠지고 1.1 이 그 가중치를 가져감(이름·산출물은 그대로)
        ([("1.1", "착수보고", "착수보고서.md", 0.5, 1.0), BASE[2]], ("1", "2"), "RESTRUCTURED"),
    ],
)
@requires_db
def test_AT6b_식별을_잇지_못하면_승계하지_않는다(client, client_token, env, second, groups, reason):
    env.load(BASE)
    _confirmed(client, client_token, "1.1")
    old_key = env.item("1.1")["task_key"]
    env.load(second, groups)
    now = env.item("1.1")
    assert now["task_key"] != old_key and now["key_reason"] == reason
    s = _summary(client, client_token("r2"))
    assert s["completionRate"] == 0.0
    if now["weight"] is not None:  # 분할이면 1.1 은 묶음이라 화면 행이 없다
        item = _item(s, "1.1")
        assert item["completionStatus"] == "NONE" and item["predecessorConfirmed"] is True


@requires_db
def test_AT6c_삭제_뒤_재생성은_새_작업이다(client, client_token, env):
    env.load(BASE)
    _confirmed(client, client_token, "1.1")
    old_key = env.item("1.1")["task_key"]
    env.load(BASE[1:])  # 1.1 이 빠진 버전
    env.load(BASE)  # 같은 이름으로 다시 들어옴
    now = env.item("1.1")
    assert now["task_key"] != old_key and now["key_reason"] == "REAPPEARED"
    assert _summary(client, client_token("r2"))["completionRate"] == 0.0


@requires_db
def test_AT6d_가중치만_조정하거나_재업로드하면_확인을_잇고_현재_가중치로_센다(
    client, client_token, env
):
    env.load(BASE)
    _confirmed(client, client_token, "1.1")
    key = env.item("1.1")["task_key"]
    env.load(BASE)  # 같은 내용 재업로드
    assert env.item("1.1")["task_key"] == key and env.item("1.1")["key_reason"] == "CONTINUED"
    env.load([("1.1", "착수보고", "착수보고서.md", 0.25, 1.0), ("1.2", "중간보고",
              "중간보고서.md", 0.3, 0.5), ("2.1", "연계 수집", "커넥터.py", 0.45, 0.0)])
    assert env.item("1.1")["task_key"] == key
    s = _summary(client, client_token("r2"))
    item = _item(s, "1.1")
    assert item["completionStatus"] == "CONFIRMED"
    assert s["completionRate"] == pytest.approx(0.25)  # 현재 WBS 가중치
    assert item["weightAtConfirm"] == pytest.approx(0.2) and item["planVersionAtConfirm"] == "v1"
    assert "v3" in s["basis"]


@requires_db
def test_AT13_요청_뒤_작업이_바뀌면_확인을_막는다(client, client_token, env):
    env.load(BASE)
    r2, r3 = client_token("r2"), client_token("r3")
    rid = _request(client, r2, "1.1").json()["id"]
    assert _report(client, r3, rid).status_code == 200
    env.load([("1.1", "착수보고", "착수보고서_v2.pptx", 0.2, 1.0)] + BASE[1:])
    res = _confirm(client, r2, rid)
    assert res.status_code == 409 and res.json()["code"] == "SCOPE_CHANGED"
    env.load([("1.1", "착수 회의", "착수보고서.md", 0.2, 1.0)] + BASE[1:])
    res = _confirm(client, r2, rid)
    assert res.status_code == 409 and res.json()["code"] == "TASK_CHANGED"
    with tx() as cur:
        assert review_repo.find_by_id(cur, rid)["status"] == "REPORTED"
    assert _records(rid) == []


@pytest.fixture
def plan_file(monkeypatch, tmp_path):
    """수집한 계획서 파일 대역. 파일을 열면 정해 둔 계획을 돌려준다."""
    from app.dashboard import service as dashboard_service

    holder: dict[str, wbs.WbsPlan] = {}
    path = tmp_path / "WBS.xlsx"
    path.write_bytes(b"x")
    monkeypatch.setattr(dashboard_service, "_plan_path", lambda project_id, row, cur=None: path)
    monkeypatch.setattr(wbs, "parse", lambda data: holder["plan"])
    return holder


@requires_db
def test_AT15_수집_뒤_화면을_열기_전에도_새_계획서로_판정한다(client, client_token, env, plan_file):
    """일정·진척 화면을 거치지 않고 완료 확인부터 봐도 현행 계획서 기준이다."""
    env.load(BASE)
    r2, r3 = client_token("r2"), client_token("r3")
    _confirmed(client, client_token, "1.1")
    rid = _request(client, r2, "1.2").json()["id"]
    assert _report(client, r3, rid).status_code == 200

    changed = [("1.1", "착수보고", "착수보고서_v2.pptx", 0.2, 1.0),
               ("1.2", "중간보고", "중간보고서_v2.pptx", 0.3, 0.5), BASE[2]]
    plan_file["plan"] = _plan(changed)
    env.load(changed, rows_now=False)

    res = _confirm(client, r2, rid)
    assert res.status_code == 409 and res.json()["code"] == "SCOPE_CHANGED", res.text
    s = _summary(client, r2)
    assert _item(s, "1.1")["completionStatus"] == "RECONFIRM"
    assert s["completionRate"] == 0.0


# ---------------------------------------------------------------- 중복·일관성·권한


@requires_db
def test_AT11_중복_요청과_중복_확인은_한_번만_반영된다(client, client_token, env):
    env.load(BASE)
    r2, r3 = client_token("r2"), client_token("r3")
    first = _request(client, r2, "1.1")
    assert first.status_code == 201
    dup = _request(client, r2, "1.1")
    assert dup.status_code == 409 and dup.json()["code"] == "COMPLETION_REQUEST_OPEN"
    rid = first.json()["id"]

    assert _report(client, r3, rid, evidence=[]).status_code == 400  # 근거 없는 보고
    assert _report(client, r3, rid).status_code == 200
    assert _confirm(client, r2, rid, ack=False).status_code == 400  # 완료 인정 표시 없음
    assert _confirm(client, r2, rid).status_code == 200
    again = _confirm(client, r2, rid)
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_DECIDED"
    assert len(_records(rid)) == 1
    assert _summary(client, r2)["completionRate"] == pytest.approx(0.2)

    # 이미 확인된 작업에 새 완료 확인 요청은 안 된다(철회가 먼저)
    later = _request(client, r2, "1.1")
    assert later.status_code == 409 and later.json()["code"] == "ALREADY_CONFIRMED"

    # 확인할 완료 내용이 없거나 WBS 가 아닌 대상은 요청이 안 된다
    assert _request(client, r2, "1.2", scope="  ").status_code == 400
    assert _request(client, r2, "9.9").status_code == 400


@requires_db
def test_AT12_기록_저장이_실패하면_상태도_바뀌지_않는다(client, client_token, env, monkeypatch):
    env.load(BASE)
    r2, r3 = client_token("r2"), client_token("r3")
    rid = _request(client, r2, "1.1").json()["id"]
    assert _report(client, r3, rid).status_code == 200

    def boom(*args, **kwargs):
        raise RuntimeError("기록 저장 실패")

    monkeypatch.setattr(review_repo, "insert_completion_record", boom)
    with pytest.raises(RuntimeError):
        _confirm(client, r2, rid)
    monkeypatch.undo()
    with tx() as cur:
        assert review_repo.find_by_id(cur, rid)["status"] == "REPORTED"
        events = [e["kind"] for e in review_repo.list_events(cur, rid)]
    assert "CONFIRMED" not in events
    assert _records(rid) == []
    # 다시 시도하면 정상으로 한 번만 들어간다
    assert _confirm(client, r2, rid).status_code == 200
    assert len(_records(rid)) == 1


@pytest.fixture
def foreign_project():
    with tx() as cur:
        pid = str(fetch_one(
            cur,
            """
            insert into project (client_org_id, name, start_date, end_date, description)
            values (%s, %s, '2026-08-01', '2026-11-30', '완료 확인 권한 시험') returning id
            """,
            (OTHER_CLIENT_ORG, f"완료 확인 권한 시험 {uuid.uuid4().hex[:6]}"),
        )["id"])
    yield pid
    with tx() as cur:
        cur.execute("delete from project where id = %s", (pid,))


@requires_db
def test_AT7_완료_확인은_그_사업_발주기관만(client, client_token, env, foreign_project):
    env.load(BASE)
    r1, r2, r3 = client_token("r1"), client_token("r2"), client_token("r3")
    assert _request(client, r3, "1.1").status_code == 403  # 용역사
    assert _request(client, r1, "1.1").status_code == 403  # 최고관리자도 완료 확인은 못 연다
    # 일반 확인 요청도 최고관리자는 열지 않는다(DEC-05 2026-11-16, ARC-032). 예전엔 열었다
    res = _request(client, r1, "1.2", purpose="GENERAL", scope=None)
    assert res.status_code == 403, res.text
    assert "플랫폼 관리자는" in res.json()["message"]

    rid = _request(client, r2, "1.1").json()["id"]
    assert _report(client, r3, rid).status_code == 200
    assert _confirm(client, r1, rid).status_code == 403
    assert _confirm(client, r3, rid).status_code == 403
    assert _confirm(client, r2, rid).status_code == 200
    w = {"reason": "x"}
    assert client.post(f"/api/review-requests/{rid}/withdraw-completion", json=w,
                       headers=_auth(r1)).status_code == 403
    assert client.post(f"/api/review-requests/{rid}/withdraw-completion", json=w,
                       headers=_auth(r3)).status_code == 403

    # 다른 발주기관 사업의 화면·요청은 못 본다
    assert client.get(f"/api/projects/{foreign_project}/wbs/completion",
                      headers=_auth(r2)).status_code == 403
    assert client.get(f"/api/projects/{PID}/wbs/completion").status_code == 401


@requires_db
def test_AT14_산출물_버전_근거는_그때_버전과_상태로_고정된다(
    client, client_token, env, foreign_project
):
    plan_id = env.load(BASE)
    r2, r3 = client_token("r2"), client_token("r3")
    rid = _request(client, r2, "1.1").json()["id"]

    # 다른 사업의 산출물·글 근거의 빈 위치는 받지 않는다
    with tx() as cur:
        from app.standard import repository as standard_repo

        standard_repo.create_checklist(cur, foreign_project)
        other = fetch_one(
            cur, "select id from work_product where project_id = %s limit 1", (foreign_project,)
        )
    bad = [{"kind": "WORK_PRODUCT", "workProductId": str(other["id"])}]
    assert _report(client, r3, rid, evidence=bad).status_code == 400
    assert _report(client, r3, rid, evidence=[{"kind": "TEST", "ref": " "}]).status_code == 400

    good = [
        {"kind": "WORK_PRODUCT", "workProductId": plan_id, "note": "WBS 계획서"},
        {"kind": "TEST", "ref": "CI #120 통과"},
    ]
    res = _report(client, r3, rid, evidence=good)
    assert res.status_code == 200, res.text
    reported = next(e for e in res.json()["events"] if e["kind"] == "REPORTED")["evidence"]
    assert reported[0]["version"] == "v1" and reported[0]["statusAtReport"] == "SUBMITTED"
    assert reported[0]["ref"] == "WBS v1"

    assert _confirm(client, r2, rid).status_code == 200
    # 확인 뒤 그 산출물이 승인돼도 확인 기록의 상태는 확인 시점 그대로다
    with tx() as cur:
        cur.execute(
            "update work_product set status = 'APPROVED', approved_at = now() where id = %s",
            (plan_id,),
        )
    [rec] = _records(rid)
    at_confirm = rec["evidence_json"]["work_products_at_confirm"]
    assert at_confirm == [
        {"workProductId": plan_id, "version": "v1", "status": "SUBMITTED", "approvedAt": None}
    ]
