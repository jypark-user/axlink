"""일정 화면에서 WBS 파일을 바로 올린다(11-24). 저장소가 없는 사업(Redmine 만 쓰는 업체)의 WBS 창구.

올린 파일은 곧바로 사업수행계획서의 현행 버전이 되고 일정·진척(L1)이 그 파일을 읽는다.
저장소에서 WBS 를 읽는 사업은 받지 않는다.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.db import fetch_one, tx
from tests.conftest import requires_db
from tests.test_wbs import build
from tests.test_wbs_schedule_api import PID, _auth, no_plan, plan_file  # noqa: F401

_ROWS = [
    ["1", "분석", "", None, None, None, None, None],
    ["1.1", "요구사항 정의", "요구사항정의서", "2026-09-21", "2026-09-30", 0.4, None, 1.0],
    ["2", "개발", "", None, None, None, None, None],
    ["2.1", "예약 기능", "소스코드", "2026-10-19", "2026-11-20", 0.6, None, 0.5],
]


def _post(client, token, data: bytes, name: str = "WBS.xlsx", version: str | None = None):
    form = {"version": version} if version else {}
    return client.post(
        f"/api/projects/{PID}/wbs/plan",
        headers=_auth(token),
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )


@pytest.fixture
def cleanup():
    """시험이 올린 계획서·문서를 지운다. 시드 사업의 다른 산출물은 건드리지 않는다."""
    yield
    with tx() as cur:
        rows = cur.execute(
            "select wp.id, du.id as doc, du.stored_path from work_product wp "
            "join document_upload du on du.id = wp.document_upload_id "
            "where wp.project_id = %s and wp.type = 'PROJECT_PLAN' and wp.source_kind = 'DOCUMENT'",
            (PID,),
        ).fetchall()
        for r in rows:
            cur.execute("delete from wbs_item where work_product_id = %s", (r["id"],))
            cur.execute("delete from wbs_recognition where work_product_id = %s", (r["id"],))
            cur.execute("delete from work_product where id = %s", (r["id"],))
            cur.execute("delete from doc_chunk where source_id = %s", (r["doc"],))
            cur.execute("delete from document_upload where id = %s", (r["doc"],))
            Path(settings.document_root, r["stored_path"]).unlink(missing_ok=True)


@requires_db
def test_올린_WBS_가_곧바로_일정과_진척의_원천이_된다(client, client_token, no_plan, cleanup):  # noqa: F811
    token = client_token("r2")
    before = client.get(f"/api/projects/{PID}/wbs", headers=_auth(token)).json()
    assert before["planUpload"] is True

    res = _post(client, token, build(_ROWS), name="library-WBS.xlsx", version="v1.0")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["version"] == "v1.0" and body["leafCount"] == 2

    sched = client.get(f"/api/projects/{PID}/wbs?at=2026-11-24", headers=_auth(token)).json()
    assert sched["source"] == "WBS_FILE"
    assert sched["planVersion"] == "v1.0"
    # 보관 경로(해시)가 아니라 올린 파일 이름을 보인다
    assert sched["sourceFile"]["origin"] == "UPLOAD"
    assert sched["sourceFile"]["path"] == "library-WBS.xlsx"
    assert "library-WBS.xlsx" in sched["sourceLabel"]
    assert [i["wbsId"] for i in sched["items"]] == ["1", "1.1", "2", "2.1"]

    prog = client.get(f"/api/projects/{PID}/progress?at=2026-11-24", headers=_auth(token)).json()
    assert prog["level"] == "L1"
    assert prog["representative"] == pytest.approx(0.4 * 1.0 + 0.6 * 0.5)

    # 올린 계획서는 산출물이라 기타 자료 목록에 두지 않는다
    res = client.get(f"/api/projects/{PID}/documents?general=true&size=100", headers=_auth(token))
    assert res.status_code == 200, res.text
    docs = res.json()
    items = docs.get("content") or docs.get("items") or []
    assert docs["totalElements"] == len(items) or len(items) == 100
    assert body["documentId"] not in {d["id"] for d in items}


@requires_db
def test_새_버전을_올리면_그_판으로_바뀌고_버전을_비우면_오늘_날짜다(
    client, client_token, no_plan, cleanup  # noqa: F811
):
    token = client_token("r2")
    assert _post(client, token, build(_ROWS), version="v1.0").status_code == 201
    rows = [r[:] for r in _ROWS]
    rows[3][7] = 1.0  # 예약 기능 실적 50 → 100
    res = _post(client, token, build(rows))
    assert res.status_code == 201, res.text
    label = res.json()["version"]
    assert len(label) == 10 and label[4] == "-"  # YYYY-MM-DD
    with tx() as cur:
        current = fetch_one(
            cur,
            "select version from work_product where project_id = %s and type = 'PROJECT_PLAN' "
            "and is_current",
            (PID,),
        )
    assert current["version"] == label
    prog = client.get(f"/api/projects/{PID}/progress", headers=_auth(token)).json()
    assert prog["representative"] == pytest.approx(1.0)


@requires_db
def test_WBS_로_읽히지_않거나_엑셀이_아니면_받지_않는다(client, client_token, no_plan, cleanup):  # noqa: F811
    token = client_token("r2")
    res = _post(client, token, b"%PDF-1.4", name="WBS.pdf")
    assert res.status_code == 400 and ".xlsx" in res.json()["message"]
    res = _post(client, token, b"not a workbook", name="WBS.xlsx")
    assert res.status_code == 400 and "WBS 로 읽을 수 없습니다" in res.json()["message"]
    with tx() as cur:
        current = fetch_one(
            cur,
            "select 1 from work_product where project_id = %s and type = 'PROJECT_PLAN' "
            "and is_current",
            (PID,),
        )
    assert current is None


@requires_db
def test_저장소에서_WBS_를_읽는_사업은_올리기를_막는다(client, client_token, plan_file, cleanup):  # noqa: F811
    token = client_token("r2")
    sched = client.get(f"/api/projects/{PID}/wbs", headers=_auth(token)).json()
    assert sched["planUpload"] is False
    res = _post(client, token, build(_ROWS))
    assert res.status_code == 409
    assert res.json()["code"] == "PLAN_FROM_REPOSITORY"
