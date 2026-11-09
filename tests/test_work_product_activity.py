"""산출물 활동 구분은 유형이 정한다 (SWFR.PIP.001).

ISO/IEC 29110 의 PM·SI 활동은 산출물 유형마다 하나로 정해져 있다. 사람이 고르지 않고,
수집·문서 확정이 새 버전을 만들 때도 유형 표(work_product_type.ACTIVITIES)에서 읽는다.
앞 버전에 다른 값이 들어 있어도 물려받지 않는다. DB 시험은 끝나면 롤백한다.
"""

import uuid

import pytest

from app.db import fetch_one, tx
from app.standard import repository as standard_repo
from app.standard import work_product_type
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


class _Rollback(Exception):
    """시험 데이터를 남기지 않으려고 트랜잭션을 일부러 깬다."""


def _activity(cur, wp_id: str) -> tuple[str | None, str | None]:
    row = fetch_one(
        cur, "select pm_activity, si_activity from work_product where id = %s", (wp_id,)
    )
    return row["pm_activity"], row["si_activity"]


def test_유형마다_활동이_하나씩_정해져_있다():
    assert set(work_product_type.ACTIVITIES) == set(work_product_type.DISPLAY_NAMES)
    for pm, si in work_product_type.ACTIVITIES.values():
        assert (pm is None) != (si is None)
    assert work_product_type.activity_of("SOFTWARE_DESIGN") == (None, "SI_3")
    assert work_product_type.activity_of("ACCEPTANCE_RECORD") == ("PM_4", None)


@requires_db
def test_목록_항목_없이_수집이_먼저_닿아도_유형의_활동이_들어간다():
    """예전에는 PM_1(계획)로 채웠다. 유지보수문서가 계획 단계로 보이던 경로다."""
    with pytest.raises(_Rollback), tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn_id = str(uuid.uuid4())
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'GITHUB', 'TST', 'https://api.github.invalid/',
                    'activity/test', 'x', 'x', 'ACTIVE')
            """,
            (conn_id, PID, org["id"]),
        )
        cur.execute(
            "delete from work_product where project_id = %s and type = 'MAINTENANCE_DOC'", (PID,)
        )
        rec = {
            "type": "MAINTENANCE_DOC", "version": "A1", "title": "유지보수 안내",
            "file_uri": "docs/maint.md", "external_url": None, "source_revision": "abc",
        }
        wp_id = standard_repo.upsert_work_product(cur, PID, conn_id, "docs/maint.md", rec)
        assert _activity(cur, wp_id) == (None, "SI_6")
        raise _Rollback


@requires_db
def test_문서로_올린_새_버전은_앞_버전의_활동을_물려받지_않는다():
    with pytest.raises(_Rollback), tx() as cur:
        cur.execute(
            """
            update work_product set pm_activity = 'PM_1', si_activity = null
             where project_id = %s and type = 'SOFTWARE_DESIGN' and is_current
            """,
            (PID,),
        )
        rec = {
            "type": "SOFTWARE_DESIGN", "title": "설계서", "version": "ACT-1",
            "status": "SUBMITTED", "authored_at": None, "file_uri": "x",
        }
        wp_id = standard_repo.place_document_work_product(cur, PID, None, None, rec)
        assert _activity(cur, wp_id) == (None, "SI_3")
        raise _Rollback


@requires_db
def test_파일을_예전_내용으로_되돌리면_그_판을_현행으로_되살린다():
    """DEF-V033. 되돌림 커밋은 같은 blob(같은 버전)을 다시 만든다. 새 행을 넣으면 버전 유일
    제약에 걸려 수집 전체가 500 이었다. 그 판의 행을 현행으로 되살리고 승인 이력은 그대로 둔다."""
    with pytest.raises(_Rollback), tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn_id = str(uuid.uuid4())
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'GITHUB', 'TST', 'https://api.github.invalid/',
                    'revert/test', 'x', 'x', 'ACTIVE')
            """,
            (conn_id, PID, org["id"]),
        )
        cur.execute(
            "delete from work_product where project_id = %s and type = 'MAINTENANCE_DOC'", (PID,)
        )

        def put(version: str, sha: str) -> str:
            rec = {
                "type": "MAINTENANCE_DOC", "version": version, "title": f"유지보수 안내 {version}",
                "file_uri": "docs/maint.md", "external_url": None, "source_revision": sha,
            }
            return standard_repo.upsert_work_product(cur, PID, conn_id, "docs/maint.md", rec)

        first = put("A1", "c1")
        cur.execute(
            "update work_product set status = 'APPROVED', approved_at = now() where id = %s",
            (first,),
        )
        second = put("B2", "c2")
        assert second != first
        again = put("A1", "c3")  # c3 은 c1 의 내용으로 되돌린 커밋
        assert again == first
        rows = cur.execute(
            "select id::text, version, is_current, status, source_revision from work_product "
            "where project_id = %s and type = 'MAINTENANCE_DOC' order by version",
            (PID,),
        ).fetchall()
        assert [(r["version"], r["is_current"]) for r in rows] == [("A1", True), ("B2", False)]
        assert rows[0]["status"] == "APPROVED" and rows[0]["source_revision"] == "c3"
        raise _Rollback
