"""산출물 화면 API (ARC-016 2단계). WBS 항목에 바로 올린 문서가 판정과 목록에 붙는가."""

import hashlib
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.db import fetch_one, tx
from tests.conftest import requires_db
from tests.test_wbs import build
from tests.test_wbs_schedule_api import no_plan  # noqa: F401  (fixture)

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def plan(no_plan):  # noqa: F811
    """말단 둘. 1.1 은 종료일이 지났고 파일이 없다. 2.1 은 아직이다."""
    data = build([
        ["1", "사업관리", "", None, None, None, None, None],
        ["1.1", "착수보고", "착수보고서.hwp", "2026-08-11", "2026-08-11", 0.5, None, 1.0],
        ["2", "개발", "", None, None, None, None, None],
        ["2.1", "연계 수집", "docs/커넥터-설계.md", "2026-09-01", "2026-12-31", 0.5, None, 0.0],
    ])
    sha = hashlib.sha1(data).hexdigest()
    folder = Path(settings.document_root) / PID / "repo"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha}.xlsx"
    path.write_bytes(data)
    wp_id = str(uuid.uuid4())
    with tx() as cur:
        cur.execute("delete from wbs_item where project_id = %s", (PID,))
        cur.execute(
            """
            insert into work_product (id, project_id, type, version, title, status, is_current,
                                      source_kind, file_uri, source_revision, external_url,
                                      pm_activity)
            values (%s, %s, 'PROJECT_PLAN', %s, 'WBS', 'SUBMITTED', true, 'TOOL',
                    'docs/WBS.xlsx', %s, 'https://example.invalid/WBS.xlsx', 'PM_1')
            """,
            (wp_id, PID, sha[:12], sha),
        )
    yield
    with tx() as cur:
        cur.execute(
            "delete from document_upload where project_id = %s and wbs_item_id is not null",
            (PID,),
        )
        cur.execute("delete from wbs_item where project_id = %s", (PID,))
        cur.execute("delete from work_product where id = %s", (wp_id,))
    path.unlink(missing_ok=True)


@requires_db
def test_항목에_올린_문서는_이름이_달라도_제출이고_목록에_붙는다(client, client_token, plan):
    token = client_token("r3")  # 용역사가 올린다
    before = client.get(f"/api/projects/{PID}/wbs/deliverables?at=2026-09-22", headers=_auth(token))
    assert before.status_code == 200, before.text
    by_id = {i["wbsId"]: i for i in before.json()["items"]}
    assert list(by_id) == ["1.1", "2.1"]  # 묶음은 안 나온다
    assert by_id["1.1"]["status"] == "OVERDUE" and by_id["2.1"]["status"] == "MISSING"
    assert before.json()["summary"] == {"submitted": 0, "missing": 1, "overdue": 1, "none": 0}

    data = build([["1", "x", "", None, None, None, None, None],
                  ["1.1", "y", "z.md", "2026-01-01", "2026-01-02", 1.0, None, 1.0]])
    res = client.post(
        f"/api/projects/{PID}/documents",
        files={"file": ("2026-09 착수 보고 최종.xlsx", data, "application/octet-stream")},
        data={"wbsId": "1.1"},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    doc_id = res.json()["id"]
    with tx() as cur:
        row = fetch_one(cur, "select wbs_item_id from document_upload where id = %s", (doc_id,))
        assert row["wbs_item_id"] is not None

    after = client.get(f"/api/projects/{PID}/wbs/deliverables?at=2026-09-22", headers=_auth(token))
    item = next(i for i in after.json()["items"] if i["wbsId"] == "1.1")
    assert item["status"] == "SUBMITTED" and item["rule"] == "LINKED_DOC"
    assert item["ref"] == "2026-09 착수 보고 최종.xlsx"
    assert item["url"] == f"/api/documents/{doc_id}/content"
    assert [d["id"] for d in item["documents"]] == [doc_id]
    assert after.json()["summary"] == {"submitted": 1, "missing": 1, "overdue": 0, "none": 0}

    # 일정 화면도 같은 판정을 본다. 두 화면이 다른 값을 보이면 안 된다
    schedule = client.get(f"/api/projects/{PID}/wbs?at=2026-09-22", headers=_auth(token))
    row = next(i for i in schedule.json()["items"] if i["wbsId"] == "1.1")
    assert row["deliverableStatus"] == "SUBMITTED" and row["deliverableRule"] == "LINKED_DOC"


@requires_db
def test_없는_WBS_번호로_올리면_거절한다(client, client_token, plan):
    data = build([["1", "x", "", None, None, None, None, None],
                  ["1.1", "y", "z.md", "2026-01-01", "2026-01-02", 1.0, None, 1.0]])
    res = client.post(
        f"/api/projects/{PID}/documents",
        files={"file": ("엉뚱.xlsx", data, "application/octet-stream")},
        data={"wbsId": "9.9"},
        headers=_auth(client_token("r3")),
    )
    assert res.status_code == 400
    assert "9.9" in res.json()["message"]
