"""진척 산정이 wbs_item 행을 잠그지 않는다 (5174 원격 시나리오 GET /wbs 시간 초과, SWFR.PIP.010).

원격 시험은 시험 프로세스의 트랜잭션 안에서 일별 스냅샷(진척 산정)을 찍은 채, 대상 서버에
수집과 일정 화면(GET /wbs)을 요청한다. 진척 산정이 wbs_item 에 산출물 연결을 쓰면 그 트랜잭션이
끝날 때까지 행 잠금이 남고, 같은 행의 판정을 갱신하는 일정 화면 요청이 끝없이 기다린다.
여기서는 그 모양을 프로세스 안에서 만든다. 별도 연결로 스냅샷을 찍어 둔 채(커밋 전) 일정 화면을
부르고, 제한 시간 안에 답하는지 본다.
"""

import threading
from datetime import date

import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.dashboard import snapshot as snapshot_service
from app.db import tx
from tests.conftest import requires_db
from tests.test_wbs_schedule_api import PID, _auth, no_plan, plan_file  # noqa: F401

AT = "2026-09-26"
DAY = date(2026, 9, 26)


def _stale_link(cur) -> None:
    """판정과 다른 산출물 연결을 남겨 둔다. 진척 산정이 이를 「고치려」 쓰면 잠금이 생긴다."""
    other = cur.execute(
        "select id from work_product where project_id = %s and type <> 'PROJECT_PLAN' limit 1",
        (PID,),
    ).fetchone()
    cur.execute(
        "update wbs_item set deliverable_product_id = %s where project_id = %s and active",
        (other["id"], PID),
    )


@requires_db
def test_진척_산정_중에도_일정_화면이_막히지_않는다(client, client_token, plan_file):  # noqa: F811
    token = client_token("r2")
    # 계획서를 행으로 적재하고 판정을 한 번 남긴다
    assert client.get(f"/api/projects/{PID}/wbs?at={AT}", headers=_auth(token)).status_code == 200
    with tx() as cur:
        _stale_link(cur)

    holder = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        cur = holder.cursor()
        # 커밋하지 않은 채로 둔다. 원격 시험의 seed.s1() 이 이렇게 스냅샷을 찍고 서버를 부른다
        snapshot_service.take_unchecked(cur, PID, DAY, None)
        locked = cur.execute(
            "select count(*) as n from pg_locks l join pg_class c on c.oid = l.relation "
            "where l.pid = pg_backend_pid() and c.relname = 'wbs_item' "
            "and l.mode = 'RowExclusiveLock'"
        ).fetchone()["n"]

        result: dict = {}

        def call() -> None:
            result["res"] = client.get(f"/api/projects/{PID}/wbs?at={AT}", headers=_auth(token))

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        worker.join(timeout=15)
        hung = worker.is_alive()
    finally:
        holder.rollback()  # 막혔더라도 풀어 준다
        holder.close()
    if hung:
        worker.join(timeout=15)
    assert not hung, "스냅샷 트랜잭션이 열린 동안 GET /wbs 가 15초 안에 답하지 못했다(행 잠금 대기)"
    assert locked == 0, "진척 산정(스냅샷)이 wbs_item 에 썼다. 읽기 경로는 쓰지 않아야 한다"
    assert result["res"].status_code == 200, result["res"].text


@requires_db
def test_산출물_확인_요청_상태_뜨기도_쓰지_않는다(client, client_token, plan_file):  # noqa: F811
    """WORK_PRODUCT 대상 상태(산출물 승인률 포함)를 떠도 판정·연결을 쓰지 않는다."""
    from app.dashboard import service as dashboard_service

    token = client_token("r2")
    assert client.get(f"/api/projects/{PID}/wbs?at={AT}", headers=_auth(token)).status_code == 200
    with tx() as cur:
        _stale_link(cur)
        before = cur.execute(
            "select count(*) as n from wbs_item where project_id = %s "
            "and deliverable_product_id is not null",
            (PID,),
        ).fetchone()["n"]
        dashboard_service.deliverable_approval_now(cur, PID, DAY)
        after = cur.execute(
            "select count(*) as n from wbs_item where project_id = %s "
            "and deliverable_product_id is not null",
            (PID,),
        ).fetchone()["n"]
    assert after == before
