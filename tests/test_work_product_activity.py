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
