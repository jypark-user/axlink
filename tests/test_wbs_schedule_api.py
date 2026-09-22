"""일정 화면의 원천 — 용역사 WBS 파일, 없으면 Redmine 이슈 일정, 둘 다 없으면 고지.
표준 산출물 목록으로 WBS 를 흉내 내던 것을 걷어낸 자리다(SWFR.PIP.010).
"""

import hashlib
import uuid
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from app.config import settings
from app.db import fetch_one, tx
from tests.conftest import requires_db
from tests.test_wbs import build

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def no_plan():
    """현행 사업수행계획서 행을 잠시 걷어 둔다. 다른 시험이 남긴 파일에 흔들리지 않게."""
    with tx() as cur:
        rows = cur.execute(
            "select id, is_current from work_product "
            "where project_id = %s and type = 'PROJECT_PLAN'",
            (PID,),
        ).fetchall()
        cur.execute(
            "update work_product set is_current = false "
            "where project_id = %s and type = 'PROJECT_PLAN'",
            (PID,),
        )
    yield
    with tx() as cur:
        for r in rows:
            cur.execute(
                "update work_product set is_current = %s where id = %s", (r["is_current"], r["id"])
            )


@pytest.fixture
def plan_file(no_plan):
    """WBS 파일을 보관 위치(<root>/<project>/repo/<sha>.xlsx)에 두고 현행 산출물로 잇는다."""
    data = build(
        [
            ["1", "사업관리", "", None, None, None, None, None],
            ["1.1", "착수보고", "착수보고서.md", "2026-08-11", "2026-08-11", 0.2, None, 1.0],
            ["1.2", "중간보고", "중간보고서.md", "2026-09-22", "2026-09-30", 0.3, None, 0.5],
            ["2", "개발", "", None, None, None, None, None],
            ["2.1", "연계 수집", "커넥터.py", "2026-09-01", "2026-09-12", 0.5, None, 0.0],
        ]
    )
    sha = hashlib.sha1(data).hexdigest()
    folder = Path(settings.document_root) / PID / "repo"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha}.xlsx"
    path.write_bytes(data)
    wp_id = str(uuid.uuid4())
    with tx() as cur:
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
    yield wp_id
    with tx() as cur:
        cur.execute("delete from work_product where id = %s", (wp_id,))
    path.unlink(missing_ok=True)


@pytest.fixture
def redmine_issues(no_plan):
    """Redmine 연결 하나와 이슈 원시본 셋. 날짜가 없는 이슈는 일정이 아니다."""
    with tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn_id = str(uuid.uuid4())
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'REDMINE', 'TST', 'https://redmine.example.invalid/',
                    'axlink', 'x', 'x', 'ACTIVE')
            """,
            (conn_id, PID, org["id"]),
        )
        payloads = [
            {"id": 11, "subject": "설계", "start_date": "2026-09-01", "due_date": "2026-09-10",
             "done_ratio": 100, "assigned_to": {"name": "김설계"}},
            {"id": 12, "subject": "구현", "start_date": "2026-09-11", "due_date": "2026-09-30",
             "done_ratio": 30, "parent": {"id": 11}},
            {"id": 13, "subject": "날짜 없는 이슈", "done_ratio": 0},
        ]
        for p in payloads:
            cur.execute(
                """
                insert into raw_artifact (tool_connection_id, external_id, object_kind,
                                          payload_jsonb, content_hash)
                values (%s, %s, 'issue', %s, %s)
                """,
                (conn_id, str(p["id"]), Jsonb(p), hashlib.sha256(str(p).encode()).hexdigest()),
            )
    yield conn_id
    with tx() as cur:
        cur.execute("delete from raw_artifact where tool_connection_id = %s", (conn_id,))
        cur.execute("delete from tool_connection where id = %s", (conn_id,))


@requires_db
def test_WBS_가_없으면_작업_줄_없이_고지한다(client, client_token, no_plan):
    res = client.get(f"/api/projects/{PID}/wbs", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "NONE"
    assert body["items"] == []
    assert "핵심 입력" in body["notice"] and "WBS" in body["notice"]


@requires_db
def test_용역사_WBS_파일이_그대로_작업_줄이_된다(client, client_token, plan_file):
    res = client.get(f"/api/projects/{PID}/wbs?at=2026-09-26", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "WBS_FILE"
    assert body["notice"] is None
    assert body["sourceUrl"] == "https://example.invalid/WBS.xlsx"
    by_id = {i["wbsId"]: i for i in body["items"]}
    assert list(by_id) == ["1", "1.1", "1.2", "2", "2.1"]  # 번호 순, 상위 항목 포함
    assert by_id["1"]["level"] == 0 and by_id["1.1"]["level"] == 1
    assert by_id["1.2"] == {
        "wbsId": "1.2", "name": "중간보고", "level": 1, "owner": "", "deliverable": "중간보고서.md",
        "startDate": "2026-09-22", "endDate": "2026-09-30", "weight": 0.3,
        "progress": 50, "planned": 50, "externalUrl": None,
        # 산출물 "중간보고서.md" 는 저장소에도 문서에도 없다. 종료일(09.30)이 안 지났으니 미제출
        "deliverableStatus": "MISSING", "deliverableRule": None, "deliverableRef": None,
        "deliverableUrl": None,
    }
    # 1.1(08.11 종료)·2.1(09.12 종료)은 지났고 파일이 없으니 지연, 1.2 만 미제출
    assert body["deliverables"] == {"submitted": 0, "missing": 1, "overdue": 2, "none": 0}
    assert by_id["2.1"]["deliverableStatus"] == "OVERDUE"
    # 상위 항목은 하위의 가중 평균. (0.2×1.0 + 0.3×0.5) / 0.5 = 0.7
    assert by_id["1"]["progress"] == 70
    assert by_id["1"]["startDate"] == "2026-08-11" and by_id["1"]["endDate"] == "2026-09-30"
    assert by_id["2.1"]["progress"] == 0 and by_id["2.1"]["planned"] == 100  # 종료일이 지났다


@requires_db
def test_WBS_파일이_없으면_Redmine_이슈_일정으로_대신한다(client, client_token, redmine_issues):
    res = client.get(f"/api/projects/{PID}/wbs?at=2026-09-20", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "REDMINE"
    assert body["notice"] is None
    assert any("기준선(L1)은 아닙니다" in w for w in body["warnings"])
    ids = [i["wbsId"] for i in body["items"]]
    assert ids == ["#11", "#12"]  # 날짜 없는 #13 은 빠진다
    first, second = body["items"]
    assert first["owner"] == "김설계" and first["progress"] == 100 and first["level"] == 0
    assert second["level"] == 1 and second["progress"] == 30
    assert second["externalUrl"] == "https://redmine.example.invalid/issues/12"


@requires_db
def test_용역사는_배정된_사업만_본다(client, client_token, no_plan):
    other = "c0000000-0000-4000-8000-000000000002"
    res = client.get(f"/api/projects/{other}/wbs", headers=_auth(client_token("r3")))
    assert res.status_code in (403, 404), res.text
