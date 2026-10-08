"""건수 질문의 0건과 셀 자료 없음 (GH-127).

"열린 이슈 몇 건이야" 를 사업의 수집 상태별로 묻는다. 다른 시험의 연결·이슈가 섞이지 않게
시험마다 새 사업을 만든다. 판정은 10-07 에 값 없음으로 끝났던 것과 같은 꼴(심각도별 막대로
바뀌는 BULLET_CHART)로 준다.
"""

# 픽스처 ask 를 가져와 같은 이름으로 쓴다. 인자 이름이 가져온 이름을 가리는 것은 의도다
# ruff: noqa: F811

import uuid

import pytest

from app.common import errors
from app.db import fetch_one, tx
from app.rag import service as ask_service
from tests.conftest import requires_db
from tests.test_answer_intents import _finish, _text, ask  # noqa: F401

PID = "c0000000-0000-4000-8000-000000000001"
ROUTE = {"route": "AGGREGATE", "measure": "open_issue_count", "template": "BULLET_CHART"}
QUESTION = "열린 이슈 몇 건이야"


@pytest.fixture
def project():
    """시드 사업과 같은 발주기관의 빈 사업. 발주사 계정(r2)이 볼 수 있다."""
    with tx() as cur:
        row = fetch_one(
            cur,
            """
            insert into project (client_org_id, name, start_date, end_date, description)
            select client_org_id, '건수 시험 사업', start_date, end_date, '건수 질문 시험용 사업'
              from project where id = %s
            returning id
            """,
            (PID,),
        )
    pid = str(row["id"])
    yield pid
    with tx() as cur:
        cur.execute("delete from issue where project_id = %s", (pid,))
        cur.execute("delete from tool_connection where project_id = %s", (pid,))
        cur.execute("delete from project where id = %s", (pid,))


def _connect(pid: str, last_job: str | None) -> None:
    with tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        cid = str(uuid.uuid4())
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'GITHUB', '건수 시험', 'https://api.github.invalid/', %s,
                    'x', 'x', 'ACTIVE')
            """,
            (cid, pid, org["id"], f"test/{cid}"),
        )
        if last_job:
            cur.execute(
                """
                insert into sync_job (tool_connection_id, kind, status, started_at, finished_at)
                values (%s, 'POLL', %s, now() - interval '1 minute', now())
                """,
                (cid, last_job),
            )


def _issues(pid: str, statuses: list[str]) -> None:
    with tx() as cur:
        for i, status in enumerate(statuses):
            cur.execute(
                """
                insert into issue (project_id, issue_key, title, status, severity,
                                   source_kind, source_updated_at)
                values (%s, %s, '건수 시험 이슈', %s, 'MAJOR', 'MANUAL', '2026-09-01T00:00:00Z')
                """,
                (pid, f"GH-97{i:02d}", status),
            )


def _search_stopped(monkeypatch) -> list[int]:
    """검색 모델 불일치(ARC-022)처럼 문서 검색이 막힌 상태. 집계 답은 그대로여야 한다."""
    calls: list[int] = []

    def stopped(*a, **k):
        calls.append(1)
        raise errors.ApiError(503, "AI_EMBEDDING_MISMATCH", "검색 모델이 색인과 다릅니다")

    monkeypatch.setattr(ask_service.search, "search_with_vector", stopped)
    return calls


# --- a. 수집됐고 이슈가 있다 → 실제 건수 ------------------------------------------


@requires_db
def test_수집된_사업의_열린_이슈는_실제_건수로_답한다(ask, project):
    _connect(project, "SUCCEEDED")
    _issues(project, ["OPEN", "IN_PROGRESS", "CLOSED"])
    ev, scripted = ask(ROUTE, "열린 이슈는 2건입니다.", question=QUESTION, scope=[project])
    assert _finish(ev) == "STOP"
    assert "2건" in _text(ev)  # 집계 값이 2 가 아니면 수치 검문이 지운다
    assert scripted.stream_calls == 1


@requires_db
def test_검색이_멈춰도_실제_건수로_답한다(ask, project, monkeypatch):
    calls = _search_stopped(monkeypatch)
    _connect(project, "SUCCEEDED")
    _issues(project, ["OPEN", "OPEN", "OPEN"])
    ev, _ = ask(ROUTE, "열린 이슈는 3건입니다.", question=QUESTION, scope=[project])
    assert _finish(ev) == "STOP" and "3건" in _text(ev)
    assert calls  # 문서 검색은 실제로 막혔다


# --- b. 수집됐고 이슈가 없다 → 0건 ------------------------------------------------


@requires_db
def test_수집됐는데_이슈가_없으면_0건으로_답한다(ask, project):
    _connect(project, "SUCCEEDED")
    _issues(project, ["CLOSED"])
    ev, scripted = ask(ROUTE, "열린 이슈는 0건입니다.", question=QUESTION, scope=[project])
    assert _finish(ev) == "STOP"
    assert "0건" in _text(ev)
    assert "값이 아직 없어" not in _text(ev)
    assert scripted.stream_calls == 1


@requires_db
def test_검색이_멈춰도_0건으로_답한다(ask, project, monkeypatch):
    calls = _search_stopped(monkeypatch)
    _connect(project, "SUCCEEDED")
    ev, _ = ask(ROUTE, "열린 이슈는 0건입니다.", question=QUESTION, scope=[project])
    assert _finish(ev) == "STOP" and "0건" in _text(ev)
    assert calls


# --- c. 미연동·미수집·수집 실패·조회 실패 → 그 이유 ---------------------------------


@requires_db
def test_연동한_도구가_없으면_0건이라고_하지_않는다(ask, project):
    ev, scripted = ask(ROUTE, "안 불려야 한다", question=QUESTION, scope=[project])
    assert _finish(ev) == "NO_DATA"
    text = _text(ev)
    assert "연동한 도구가 없어" in text and "0건이라는 뜻은 아닙니다" in text
    assert scripted.stream_calls == 0


@requires_db
def test_아직_수집되지_않았으면_그렇게_말한다(ask, project):
    _connect(project, None)
    ev, scripted = ask(ROUTE, "안 불려야 한다", question=QUESTION, scope=[project])
    assert _finish(ev) == "NO_DATA"
    assert "아직 수집이 끝나지 않아" in _text(ev)
    assert scripted.stream_calls == 0


@requires_db
def test_마지막_수집이_실패했으면_그렇게_말한다(ask, project):
    _connect(project, "FAILED")
    ev, scripted = ask(ROUTE, "안 불려야 한다", question=QUESTION, scope=[project])
    assert _finish(ev) == "NO_DATA"
    assert "마지막 수집이 실패해" in _text(ev)
    assert scripted.stream_calls == 0


@requires_db
def test_조회가_실패하면_조회_오류로_알린다(ask, project, monkeypatch):
    _connect(project, "SUCCEEDED")

    def broken(*a, **k):
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(ask_service.semantic, "run", broken)
    ev, scripted = ask(ROUTE, "안 불려야 한다", question=QUESTION, scope=[project])
    assert _finish(ev) == "QUERY_ERROR"
    assert scripted.stream_calls == 0
