"""WBS 항목 표 (ARC-016 1단계). 파일은 계획서 버전마다 한 번만 읽고, 그 뒤로는 행만 본다.

계획서를 다시 올리면 같은 번호는 갱신되고 빠진 번호는 active=false 로 남는다. 확인 요청이
가리키던 항목이 사라지지 않는다.
"""

import hashlib
import uuid
from datetime import date
from pathlib import Path

import pytest

from app.config import settings
from app.dashboard import service as dashboard_service
from app.db import fetch_all, tx
from app.standard import wbs_repository
from tests.conftest import requires_db
from tests.test_wbs import build
from tests.test_wbs_schedule_api import no_plan  # noqa: F401  (fixture)

PID = "c0000000-0000-4000-8000-000000000001"

FIRST = [
    ["1", "사업관리", "", None, None, None, None, None],
    ["1.1", "착수보고", "착수보고서.md", "2026-08-11", "2026-08-11", 0.2, None, 1.0],
    ["1.2", "중간보고", "중간보고서.md", "2026-09-22", "2026-09-30", 0.3, None, 0.5],
    ["2", "개발", "", None, None, None, None, None],
    ["2.1", "연계 수집", "커넥터.py", "2026-09-01", "2026-09-12", 0.5, None, 0.0],
]
SECOND = [
    ["1", "사업관리", "", None, None, None, None, None],
    ["1.1", "착수보고", "착수보고서.md", "2026-08-11", "2026-08-11", 0.2, None, 1.0],
    ["2", "개발", "", None, None, None, None, None],
    ["2.1", "연계 수집", "커넥터.py", "2026-09-01", "2026-09-12", 0.4, None, 0.6],
    ["2.2", "문서 추출", "추출기.py", "2026-09-10", "2026-09-20", 0.4, None, 0.2],
]


def _install_plan(rows) -> tuple[str, Path]:
    """WBS 파일을 보관 위치에 두고 현행 계획서 행으로 잇는다. 이전 현행은 내린다."""
    data = build(rows)
    sha = hashlib.sha1(data).hexdigest()
    folder = Path(settings.document_root) / PID / "repo"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha}.xlsx"
    path.write_bytes(data)
    wp_id = str(uuid.uuid4())
    with tx() as cur:
        cur.execute(
            "update work_product set is_current = false "
            "where project_id = %s and type = 'PROJECT_PLAN'",
            (PID,),
        )
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
    return wp_id, path


@pytest.fixture
def clean_items(no_plan):  # noqa: F811
    with tx() as cur:
        cur.execute("delete from wbs_item where project_id = %s", (PID,))
    made: list[tuple[str, Path]] = []
    yield made
    with tx() as cur:
        cur.execute("delete from wbs_item where project_id = %s", (PID,))
        for wp_id, _ in made:
            cur.execute("delete from work_product where id = %s", (wp_id,))
    for _, path in made:
        path.unlink(missing_ok=True)


def _items() -> list[dict]:
    with tx() as cur:
        return fetch_all(
            cur,
            "select wbs_id, parent_wbs_id, weight, actual, active, work_product_id "
            "from wbs_item where project_id = %s order by line_no",
            (PID,),
        )


@requires_db
def test_첫_산정이_파일을_읽어_행으로_남기고_그_뒤로는_파일을_안_본다(clean_items):
    wp_id, path = _install_plan(FIRST)
    clean_items.append((wp_id, path))

    with tx() as cur:
        first = dashboard_service.compute(cur, PID, date(2026, 9, 21))
    rows = _items()
    assert [r["wbs_id"] for r in rows] == ["1", "2", "1.1", "1.2", "2.1"]
    assert [r["parent_wbs_id"] for r in rows if r["wbs_id"] == "1.1"] == ["1"]
    assert all(str(r["work_product_id"]) == wp_id for r in rows)
    groups = [r for r in rows if r["weight"] is None]
    assert [g["wbs_id"] for g in groups] == ["1", "2"]

    # 파일을 지워도 같은 버전이면 행으로 답한다. 값이 같아야 한다
    path.unlink()
    with tx() as cur:
        again = dashboard_service.compute(cur, PID, date(2026, 9, 21))
    assert again.wbs.value == first.wbs.value and again.wbsPlanned == first.wbsPlanned
    assert again.behind == first.behind
    assert not any("읽지 못했습니다" in w for w in again.warnings)


@requires_db
def test_계획서를_다시_올리면_같은_번호는_갱신되고_빠진_번호는_남는다(clean_items):
    wp1, path1 = _install_plan(FIRST)
    clean_items.append((wp1, path1))
    with tx() as cur:
        dashboard_service.compute(cur, PID, date(2026, 9, 21))

    wp2, path2 = _install_plan(SECOND)
    clean_items.append((wp2, path2))
    with tx() as cur:
        result = dashboard_service.compute(cur, PID, date(2026, 9, 21))

    by_id = {r["wbs_id"]: r for r in _items()}
    assert float(by_id["2.1"]["actual"]) == 0.6 and by_id["2.1"]["active"] is True
    assert by_id["2.2"]["active"] is True
    assert by_id["1.2"]["active"] is False  # 사라졌지만 행은 남는다
    assert all(str(r["work_product_id"]) == wp2 for r in by_id.values() if r["active"])

    # 진척은 새 계획서의 활성 행으로만 센다: 0.2*1.0 + 0.4*0.6 + 0.4*0.2 = 0.52
    assert result.wbs.value == pytest.approx(0.52, abs=0.001)
    with tx() as cur:
        assert [r.wbs_id for r in dashboard_service.current_wbs_rows(cur, PID)] == [
            "1.1", "2.1", "2.2",
        ]


@requires_db
def test_행이_없으면_None_이고_말단_없는_묶음만으로는_계획이_아니다(clean_items):
    with tx() as cur:
        assert wbs_repository.load_plan(cur, PID) is None
        assert wbs_repository.loaded_version(cur, PID) is None
