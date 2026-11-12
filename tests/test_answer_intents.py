"""일정 질문·답의 종류·권장 질문 (SWFR.RAG.005 · SWFR.RAG.007).

고정 응답 모델로 본다. 분류 결과는 대본으로 주입하고, 값은 진척 카드와 같은 산정에서 오는지,
막힌 이유가 종류별로 갈리는지, 권장 질문이 검증을 거치는지를 확인한다. 실모델 평가는 따로 한다.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.config import settings
from app.dashboard import service as progress_service
from app.db import fetch_all, tx
from app.rag import intents, routing
from app.rag import service as ask_service
from tests.conftest import requires_db
from tests.test_ask_api import ScriptedLlm, _auth, _events
from tests.test_wbs_schedule_api import no_plan, plan_file  # noqa: F401 (fixture)
from tests.test_widget_generation import _catalog

PID = "c0000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------- 판정 (DB 없음)


def test_일정_질문_판정은_묶음과_기간을_검증한다():
    d = routing.from_choice(
        _catalog(),
        {
            "route": "INTENT",
            "intent": "plan_vs_actual",
            "related": ["intent:BEHIND_TASKS", "measure:없는지표", "intent:PLAN_VS_ACTUAL"],
        },
    )
    assert d.type == routing.INTENT and d.intent == intents.PLAN_VS_ACTUAL
    # 없는 지표는 버리고, 이번에 답하는 것은 권장에서 뺀다
    assert d.related == ["intent:BEHIND_TASKS"]

    month = routing.from_choice(
        _catalog(), {"route": "INTENT", "intent": "PROGRESS_CHANGE", "period": "MONTH"}
    )
    assert month.intent == intents.PROGRESS_CHANGE and month.period == intents.MONTH
    # 기간이 틀리면 지난주로 본다. 묶음이 틀리면 문서 경로다
    odd = routing.from_choice(
        _catalog(), {"route": "INTENT", "intent": "PROGRESS_CHANGE", "period": "YEAR"}
    )
    assert odd.period == intents.WEEK
    assert routing.from_choice(_catalog(), {"route": "INTENT", "intent": "X"}).type == "DOCUMENT"


def test_되묻기는_검증된_선택지가_둘_이상일_때만_선다():
    ok = routing.from_choice(
        _catalog(), {"route": "CLARIFY", "options": ["intent:PLAN_VS_ACTUAL", "overview"]}
    )
    assert ok.type == routing.CLARIFY and ok.options == ["intent:PLAN_VS_ACTUAL", "overview"]
    one = routing.from_choice(
        _catalog(), {"route": "CLARIFY", "options": ["intent:PLAN_VS_ACTUAL", "measure:없음"]}
    )
    assert one.type == routing.DOCUMENT


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("intent:PLAN_VS_ACTUAL", "intent:PLAN_VS_ACTUAL"),
        ("intent:progress_change", "intent:PROGRESS_CHANGE:WEEK"),
        ("overview", "overview"),
        ("list:issue:open", "list:ISSUE:OPEN"),
        ("measure:open_issue_count", "measure:open_issue_count"),
        ("intent:BEHIND_TASKS:WEEK", None),  # 기간은 기간 변화에만
        ("measure:없는지표", None),
        ("list:ISSUE:SOMETIMES", None),
        ("list:WIKI", None),
        ("drop table", None),
        (123, None),
    ],
)
def test_권장_질문_키는_서버가_다시_검증한다(raw, key):
    target = routing.parse_key(_catalog(), raw)
    assert (target.key if target else None) == key


def test_라우팅_프롬프트가_일정_질문을_현황과_가른다():
    prompt = routing.system_prompt(_catalog())
    assert '"route": "INTENT"' in prompt and '"route": "CLARIFY"' in prompt
    for example in ("계획보다 늦고 있어?", "일정대로 가고 있어?", "지난주보다 얼마나 진행됐어?"):
        assert example in prompt
    # 산출물 제출률과 완료 확인율을 가르는 안내가 있다
    assert "wbs_completion_rate" in prompt and "산출물까지 확인된 진척" in prompt
    # 10-07 비교에서 빗나간 질문들. 건수는 집계, 대상이 다른 지표는 쓰지 않고 목록, 전체 상태는 현황
    for example in ("이슈가 몇 건이야?", "요구사항이 몇 개야?", "전체적으로 괜찮은 거야?",
                    "심각한 이슈 있어?", "지연된 작업 있어?"):
        assert example in prompt


def test_지난달_같은_날이_없으면_그달_말일이다():
    assert intents._back(date(2026, 3, 31), intents.MONTH) == date(2026, 2, 28)
    assert intents._back(date(2026, 1, 15), intents.MONTH) == date(2025, 12, 15)
    assert intents._back(date(2026, 10, 7), intents.WEEK) == date(2026, 9, 30)


def test_차이는_부호와_함께_적는다():
    assert intents._signed(-0.78) == "-0.78"
    assert intents._signed(1.5) == "+1.5"
    assert intents._signed(0.0) == "0"
    assert intents.format_value(74.0) == "74" and intents.format_value(74.18) == "74.18"


# ---------------------------------------------------------------- 질문 (DB)


@pytest.fixture
def no_snapshots():
    """시드 사업의 스냅샷을 잠시 걷는다. 다른 시험이 남긴 값에 흔들리지 않게."""
    with tx() as cur:
        saved = fetch_all(cur, "select * from progress_snapshot where project_id = %s", (PID,))
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))
    yield
    with tx() as cur:
        cur.execute("delete from progress_snapshot where project_id = %s", (PID,))
        for row in saved:
            cols = list(row)
            cur.execute(
                f"insert into progress_snapshot ({', '.join(cols)}) "
                f"values ({', '.join(['%s'] * len(cols))})",
                [row[c] for c in cols],
            )


def _snapshot(day: date, rep: float, actual=None, planned=None, level="L1") -> None:
    with tx() as cur:
        cur.execute(
            """
            insert into progress_snapshot (project_id, snapshot_date, level, representative_pct,
                                           wbs_actual_pct, wbs_planned_pct)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (PID, day, level, rep, actual, planned),
        )


@pytest.fixture
def ask(client, client_token, monkeypatch):
    """대본 모델로 한 번 묻는다. (이벤트, 대본) 을 돌려준다."""
    created: list[tuple[str, str]] = []
    # 대본마다 판정이 다르다. 같은 질문 문장의 앞 판정을 캐시에서 다시 쓰지 않게 한다
    monkeypatch.setattr(settings, "rag_route_cache", False)

    def _ask(route, text="", question="질문", hint=None, scope=None, status=200):
        scripted = ScriptedLlm(route, text)
        scripted.complete_calls = 0
        original = scripted.complete

        def counting(*a, **k):
            scripted.complete_calls += 1
            return original(*a, **k)

        scripted.complete = counting
        monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
        token = client_token("r2")
        cid = client.post(
            "/api/conversations", json={"title": "일정", "projectScope": [PID]},
            headers=_auth(token),
        ).json()["id"]
        created.append((cid, token))
        body = {"question": question, "projectScope": scope or [], "hint": hint}
        with client.stream(
            "POST", f"/api/conversations/{cid}/messages", json=body,
            headers={**_auth(token), "Accept": "text/event-stream"},
        ) as res:
            assert res.status_code == status, res.read()
            if status != 200:
                return res.read(), scripted
            events = _events(res)
        events_by = {}
        for name, data in events:
            events_by.setdefault(name, []).append(data)
        events_by["_cid"] = cid
        events_by["_token"] = token
        return events_by, scripted

    yield _ask
    for cid, token in created:
        client.delete(f"/api/conversations/{cid}", headers=_auth(token))


def _text(ev) -> str:
    return "".join(d["text"] for d in ev.get("delta", []))


def _finish(ev) -> str:
    return ev["done"][0]["finishReason"]


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_계획_대비_진척은_같은_기준일의_계획_보고_차이를_함께_낸다(ask):
    with tx() as cur:
        progress = progress_service.compute(cur, PID, intents.today())
    planned = round(progress.wbsPlanned * 100, 2)
    actual = round(progress.wbs.value * 100, 2)
    diff = round(actual - planned, 2)
    p, a, d = (intents.format_value(x) for x in (planned, actual, abs(diff)))
    answer = f"계획 진척률(추정)은 {p}%, 보고 진척률은 {a}%로 {d}%p 차이입니다."
    ev, scripted = ask({"route": "INTENT", "intent": "PLAN_VS_ACTUAL"}, answer)

    assert ev["start"][0]["routing"]["type"] == "INTENT"
    assert ev["start"][0]["routing"]["intent"] == "PLAN_VS_ACTUAL"
    assert _finish(ev) == "STOP", _text(ev)
    # 진척 카드와 같은 값이 그대로 나간다. 모델 문장의 수치는 검문을 통과했다
    text = _text(ev)
    assert f"{p}%" in text and f"{d}%p" in text
    # 추정이라는 설명은 서버가 붙인다. 모델이 빠뜨려도 보인다
    assert text.rstrip().endswith(intents.PLAN_FOOTNOTE)
    # 사업 하나면 표가 문장을 되풀이할 뿐이라 그리지 않는다
    assert "infographic" not in ev
    # 프롬프트에 기준일·추정·단위·본문 지시가 함께 간다. 문서 검색은 하지 않는다
    prompt = scripted.prompts[0]
    assert "계획 진척률(추정)" in prompt and "%p" in prompt
    assert intents.today().isoformat() in prompt and "첫 문장에" in prompt
    assert ev["start"][0]["retrievedChunkCount"] == 0
    # 이어 볼 질문은 셋 이하이고 이번 질문을 되풀이하지 않는다
    items = ev["suggestions"][0]["items"]
    assert 1 <= len(items) <= 3
    assert all(i["hint"] != "intent:PLAN_VS_ACTUAL" for i in items)
    assert "intent:BEHIND_TASKS" in [i["hint"] for i in items]


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_근거에_없는_수치는_일정_답에서도_막힌다(ask):
    ev, _ = ask({"route": "INTENT", "intent": "PLAN_VS_ACTUAL"}, "계획보다 37.5%p 늦습니다.")
    assert _finish(ev) == "NUMBER_GUARD"
    assert "37.5" not in _text(ev)


@pytest.fixture
def one_submission(no_plan):  # noqa: F811 (픽스처 이름)
    """계획서 말고 제출본을 하나 둔다. 제출본이 하나도 없으면 산출물 갈래(L4)가 서지 않는다
    (DEF-V003). no_plan 이 걷어 내는 계획서가 빈 시험 DB 의 유일한 제출본이다."""
    with tx() as cur:
        row = cur.execute(
            "select id, status from work_product where project_id = %s and is_current "
            "and applicable and type <> 'PROJECT_PLAN' order by type limit 1",
            (PID,),
        ).fetchone()
        cur.execute("update work_product set status = 'SUBMITTED' where id = %s", (row["id"],))
    yield
    with tx() as cur:
        cur.execute("update work_product set status = %s where id = %s", (row["status"], row["id"]))


@requires_db
@pytest.mark.usefixtures("one_submission")
def test_WBS_가_없으면_대표_진척률을_기준과_함께_일부만_답한다(ask, no_snapshots):
    """WBS 없이도 대표 진척률이 이슈·산출물 갈래로 선다(제출본 하나). 계획 비교는 못 한다."""
    ev, scripted = ask({"route": "INTENT", "intent": "PLAN_VS_ACTUAL"}, "안 불려야 한다")
    assert _finish(ev) == "PARTIAL"
    # 비교한 사업이 없으면 모델을 부르지 않고 서버가 있는 값과 기준만 말한다(되풀이 없음)
    assert scripted.stream_calls == 0
    text = _text(ev)
    assert "계획과 비교할 수 없습니다" in text and "대표 진척률은" in text and " 기준 " in text
    assert text.count("비교할 수 없") == 1
    assert "infographic" not in ev


@requires_db
@pytest.mark.usefixtures("no_plan")
def test_보고값도_없으면_무엇이_없는지_말한다(ask, no_snapshots, monkeypatch):
    empty = SimpleNamespace(
        wbsPlanned=None, wbs=SimpleNamespace(value=None), representative=None, basis="NONE",
        baseDate=intents.today().isoformat(),
    )
    monkeypatch.setattr(intents.progress_service, "compute", lambda *a, **k: empty)
    ev, scripted = ask({"route": "INTENT", "intent": "PLAN_VS_ACTUAL"}, "안 불려야 한다")
    assert _finish(ev) == "NO_DATA"
    assert "WBS" in _text(ev) and "커밋하면" in _text(ev)
    assert scripted.stream_calls == 0
    assert "infographic" not in ev
    # WBS 가 있어야 답하는 질문은 권장하지 않는다
    hints = [i["hint"] for i in ev.get("suggestions", [{"items": []}])[0]["items"]]
    assert "intent:BEHIND_TASKS" not in hints and "intent:DELAY_CAUSE" not in hints


@requires_db
@pytest.mark.usefixtures("no_plan")
def test_WBS_가_없어도_허용된_보고값이_있으면_날짜와_함께_일부만_답한다(ask, no_snapshots):
    _snapshot(date(2026, 9, 30), 41.5, actual=41.5, planned=44.0)
    ev, scripted = ask({"route": "INTENT", "intent": "PLAN_VS_ACTUAL"}, "안 불려야 한다")
    assert _finish(ev) == "PARTIAL"
    assert scripted.stream_calls == 0
    assert "2026-09-30 스냅샷의 41.5%" in _text(ev)


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_늦은_작업은_계획선_기준이고_차이가_큰_순이다(ask):
    ev, _ = ask({"route": "INTENT", "intent": "BEHIND_TASKS"}, "늦은 작업은 [그림 1] 입니다.")
    assert _finish(ev) == "STOP"
    rows = [r["values"] for r in ev["infographic"][0]["data"]["rows"]]
    at = intents.today()
    with tx() as cur:
        expected = [
            r for r in progress_service.current_wbs_rows(cur, PID)
            if r.actual + 0.01 < r.planned_at(at)
        ]
    assert len(rows) == len(expected) >= 1
    diffs = [float(r["diff"].rstrip("%p")) for r in rows]
    assert diffs == sorted(diffs)


@requires_db
def test_지난주와_비교할_날이_없으면_가까운_앞_날짜를_밝힌다(ask, no_snapshots):
    _snapshot(date(2026, 9, 22), 50.0)
    _snapshot(date(2026, 10, 1), 60.0)
    ev, scripted = ask(
        {"route": "INTENT", "intent": "PROGRESS_CHANGE", "period": "WEEK"},
        "지난주보다 10%p 올랐습니다.",
    )
    assert _finish(ev) == "STOP", _text(ev)
    prompt = scripted.prompts[0]
    assert "2026-09-22" in prompt and "2026-10-01" in prompt and "+10%p" in prompt
    assert "2026-09-24 스냅샷이 없어 가장 가까운 앞 날짜" in prompt


@requires_db
def test_지난달_스냅샷이_없으면_비교할_수_없다고_한다(ask, no_snapshots):
    _snapshot(date(2026, 9, 22), 50.0)
    _snapshot(date(2026, 10, 1), 60.0)
    ev, scripted = ask(
        {"route": "INTENT", "intent": "PROGRESS_CHANGE", "period": "MONTH"}, "안 불려야 한다"
    )
    assert _finish(ev) == "NO_DATA"
    assert scripted.stream_calls == 0
    text = _text(ev)
    assert "2026-09-01 이전 스냅샷이 없어 지난달과 비교할 수 없습니다" in text
    assert "가장 오래된 스냅샷은 2026-09-22" in text and "60%" in text


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_지연_사유_문서가_없으면_늦은_작업까지만_답하고_그렇다고_말한다(ask, monkeypatch):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)
    ev, _ = ask({"route": "INTENT", "intent": "DELAY_CAUSE"}, "늦은 작업은 [그림 1] 입니다.")
    assert _finish(ev) == "PARTIAL"
    assert "지연 사유를 적은 문서·이슈는 찾지 못했습니다" in _text(ev)
    assert ev["infographic"][0]["template"] == "DATA_TABLE"


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_되묻기는_모델_본문_없이_선택지를_낸다(ask):
    ev, scripted = ask(
        {"route": "CLARIFY", "options": ["intent:PLAN_VS_ACTUAL", "overview"]}, "안 불려야 한다"
    )
    assert _finish(ev) == "CLARIFY"
    assert scripted.stream_calls == 0
    hints = [i["hint"] for i in ev["suggestions"][0]["items"]]
    assert hints == ["intent:PLAN_VS_ACTUAL", "overview"]
    assert ev["start"][0]["routing"]["type"] == "CLARIFY"


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_권장_질문을_누르면_다시_분류하지_않고_그_대상으로_답한다(ask):
    ev, scripted = ask(
        {"route": "OFF_TOPIC"}, "[그림 1]", question="계획보다 늦은 작업은 무엇인가요?",
        hint="intent:BEHIND_TASKS",
    )
    assert scripted.complete_calls == 0  # 분류 모델을 부르지 않았다
    assert ev["start"][0]["routing"]["intent"] == "BEHIND_TASKS"
    assert _finish(ev) == "STOP"


@requires_db
def test_권장_질문의_키가_틀리면_받지_않는다(ask):
    body, scripted = ask({"route": "DOCUMENT"}, "x", hint="measure:없는지표", status=400)
    assert scripted.complete_calls == 0


@requires_db
def test_권장_질문을_눌러도_범위_밖_사업은_막힌다(ask):
    body, _ = ask(
        {"route": "DOCUMENT"}, "x", hint="intent:PLAN_VS_ACTUAL",
        scope=["c0000000-0000-4000-8000-0000000000ff"], status=403,
    )


@requires_db
def test_값이_없는_지표는_문서로_돌리지_않고_값_없음이다(ask, no_snapshots, monkeypatch):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.0)  # 문서가 있어도 쓰지 않는다
    route = {"route": "AGGREGATE", "measure": "progress_planned_pct", "template": "STAT_CARD"}
    ev, scripted = ask(route, "안 불려야 한다")
    assert _finish(ev) == "NO_DATA"
    assert "계획 진척률 값이 아직 없어" in _text(ev)
    assert scripted.stream_calls == 0
    assert ev["start"][0]["routing"]["type"] in ("AGGREGATE", "MIXED")


@requires_db
def test_조회_오류는_값_없음으로_말하지_않는다(ask, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(ask_service.semantic, "run", broken)
    route = {"route": "AGGREGATE", "measure": "open_issue_count", "template": "STAT_CARD"}
    ev, scripted = ask(route, "안 불려야 한다")
    assert _finish(ev) == "QUERY_ERROR"
    text = _text(ev)
    assert "조회 중 오류" in text and "값이 없다는 뜻은 아닙니다" in text
    assert scripted.stream_calls == 0


@requires_db
def test_일정_조회_오류도_오류로_알린다(ask, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ask_service.intents, "run", broken)
    ev, _ = ask({"route": "INTENT", "intent": "PLAN_VS_ACTUAL"}, "x")
    assert _finish(ev) == "QUERY_ERROR"


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_답의_종류와_권장_질문은_메시지에_남는다(client, ask):
    ev, _ = ask({"route": "INTENT", "intent": "BEHIND_TASKS"}, "[그림 1]")
    messages = client.get(
        f"/api/conversations/{ev['_cid']}/messages", headers=_auth(ev["_token"])
    ).json()
    last = messages[-1]
    assert last["finishReason"] == "STOP"
    assert last["suggestions"] == ev["suggestions"][0]["items"]
    assert last["routing"]["type"] == "INTENT"


@requires_db
def test_일정_진척_계획대비_지표가_스냅샷에서_값을_낸다(client, client_token, no_snapshots):
    """대시보드 추천 구성과 저장 위젯이 쓰는 키. 채우는 경로 없는 표를 읽어 늘 비어 있었다."""
    _snapshot(date(2026, 9, 30), 70.0, actual=70.0, planned=72.5)
    _snapshot(date(2026, 10, 1), 71.0, actual=71.0, planned=73.25)
    spec = {
        "template": "STAT_CARD", "title": "t",
        "query": {"measure": "schedule_variance_pct", "dimensions": [], "filters": [],
                  "projectScope": [PID], "limit": None},
        "options": None,
    }
    res = client.post(
        "/api/widgets/preview", json={"spec": spec}, headers=_auth(client_token("r2"))
    )
    assert res.status_code == 200, res.text
    body = res.json()
    value = body["rows"][0]["values"]["value"] if body["rows"] else body["total"]["values"]["value"]
    assert float(value) == -2.25  # 가장 최근 스냅샷의 실적 - 계획
    assert body["unit"] == "%p"


@requires_db
def test_지금_답변_모델을_누구나_확인한다(client, client_token):
    res = client.get("/api/ai/runtime", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    body = res.json()
    # 시험은 고정 응답 모델로 돈다. 화면은 이 값으로 "실제 모델 답이 아님" 을 알린다
    assert body["fixed"] is True and body["llmProvider"] == "fake"


@requires_db
def test_실행_코드_이름표를_같이_보인다(client, client_token, monkeypatch):
    monkeypatch.setattr(settings, "build_label", "dc78303+v47+v48")
    res = client.get("/api/ai/runtime", headers=_auth(client_token("r2")))
    assert res.json()["codeVersion"] == "dc78303+v47+v48"


@requires_db
def test_계획선이_없는_날의_지연_작업_수는_0_이_아니라_값_없음이다(
    client, client_token, no_snapshots
):
    """WBS 없는 사업의 스냅샷에도 기본값 0 이 들어가 "지연 작업 0건" 으로 읽혔다(V48)."""
    _snapshot(date(2026, 10, 1), 10.0, level="L4")
    spec = {
        "template": "STAT_CARD", "title": "t",
        "query": {"measure": "progress_behind_task_count", "dimensions": [], "filters": [],
                  "projectScope": [PID], "limit": None},
        "options": None,
    }
    res = client.post(
        "/api/widgets/preview", json={"spec": spec}, headers=_auth(client_token("r2"))
    )
    assert res.status_code == 200, res.text
    body = res.json()
    values = [r["values"]["value"] for r in body["rows"]]
    total = (body["total"] or {}).get("values", {}).get("value")
    assert all(v is None for v in values) and total is None


def _data(unit: str, rows: list[tuple[str, float]], truncated: bool = False):
    from app.semantic.models import WidgetColumn, WidgetDataResponse, WidgetRow

    return WidgetDataResponse(
        measure="issue_count", measureLabel="일반 이슈 건수", unit=unit,
        dimensions=["issue_status"],
        columns=[WidgetColumn(key="d0", label="상태", type="string"),
                 WidgetColumn(key="value", label="값", type="number")],
        rows=[WidgetRow(values={"d0": k, "value": v}) for k, v in rows],
        total=None, previousTotal=None, target=None, appliedProjectIds=[PID],
        truncated=truncated, generatedAt="2026-10-07T01:00:00Z",
    )


def test_건수를_나눠_받으면_서버가_전체를_더해_준다():
    """10-07 "이슈가 몇 건이야?": 상태별 7·5 를 받은 모델이 12 를 만들어 수치 검문에 막혔다."""
    from app.rag import answer, number_guard

    data = _data("건", [("OPEN", 7), ("CLOSED", 5)])
    lines = answer.aggregate_lines(data)
    assert "- 일반 이슈 건수 전체(항목 합): 12건" in lines
    checker = number_guard.Checker(
        number_guard.facts_from_lines(lines, "집계", subject="일반 이슈 건수"),
        question="이슈가 몇 건이야?",
    )
    assert checker.check("일반 이슈는 모두 12건입니다.") == []
    # 비율은 더하지 않는다. 잘린 목록도 더하지 않는다(합이 전체가 아니다)
    rate = answer.aggregate_lines(_data("%", [("A", 50), ("B", 30)]))
    cut = answer.aggregate_lines(_data("건", [("A", 1)], True))
    assert not any("항목 합" in x for x in rate + cut)


@requires_db
def test_검색_모델이_색인과_다르면_검색_멈춤으로_알린다(ask, monkeypatch):
    """ARC-022. 조회 오류나 근거 없음과 섞지 않는다. 모델은 부르지 않는다."""
    from app.ai import embedding_guard
    from app.common import errors

    def mismatch(*a, **k):
        raise errors.ApiError(503, embedding_guard.MISMATCH, "검색 모델이 색인과 다릅니다")

    monkeypatch.setattr(ask_service.search.embedding_guard, "require_match", mismatch)
    ev, scripted = ask({"route": "DOCUMENT"}, "안 불려야 한다")
    assert _finish(ev) == "SEARCH_DISABLED"
    assert "문서 검색이 멈춰" in _text(ev)
    assert scripted.stream_calls == 0


@requires_db
def test_검색이_멈춰도_집계_질문은_값으로_답한다(ask, monkeypatch):
    """ARC-022 기능 격리. 열린 이슈 수는 DB 집계라 임베딩 불일치와 상관없이 답해야 한다."""
    from app.ai import embedding_guard
    from app.common import errors

    keys = ("GH-8811", "GH-8812")
    with tx() as cur:
        for key in keys:
            cur.execute(
                """
                insert into issue (project_id, issue_key, title, status, severity,
                                   source_kind, source_updated_at)
                values (%s, %s, '격리 시험 이슈', 'OPEN', 'MAJOR', 'MANUAL', '2026-09-01T00:00:00Z')
                """,
                (PID, key),
            )
    calls = []

    def mismatch(*a, **k):
        calls.append(1)
        raise errors.ApiError(503, embedding_guard.MISMATCH, "검색 모델이 색인과 다릅니다")

    monkeypatch.setattr(ask_service.search.embedding_guard, "require_match", mismatch)
    try:
        route = {"route": "AGGREGATE", "measure": "open_issue_count", "template": "STAT_CARD"}
        ev, scripted = ask(route, "열린 이슈가 있습니다", question="열린 이슈 몇 건이야")
        assert _finish(ev) not in ("SEARCH_DISABLED", "NO_DATA", "QUERY_ERROR")
        assert scripted.stream_calls == 1  # 값을 받아 모델이 문장을 썼다
        assert calls  # 문서 검색은 실제로 막혔다
    finally:
        with tx() as cur:
            cur.execute("delete from issue where issue_key = any(%s)", (list(keys),))


@requires_db
@pytest.mark.usefixtures("plan_file")
def test_지연_사유_질문의_지연은_종료일이_지나고_실적이_100이_아닌_작업이다(ask, monkeypatch):
    """IM-009 5.1: 지연 = 종료일 < 기준일 and 실적 < 100%. 계획선보다 뒤처졌지만 종료일이 남은
    작업(계획 뒤짐)은 지연이 아니다. 09-29 기준 1.2(종료 09-30, 실적 50%, 계획선 87.5%)는
    계획 뒤짐이지만 지연이 아니고, 2.1(종료 09-12, 실적 0%)만 지연이다(UC-060-S07 실모델)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.common import clock

    at = datetime(2026, 9, 29, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    monkeypatch.setattr(clock, "now", lambda: at)
    ev, _ = ask({"route": "INTENT", "intent": "DELAY_CAUSE"}, "지연 작업은 [그림 1] 입니다.")
    table = ev["infographic"][0]
    assert table["title"] == "지연 작업"
    assert [r["values"]["task"] for r in table["data"]["rows"]] == ["2.1 연계 수집"]
    behind, _ = ask({"route": "INTENT", "intent": "BEHIND_TASKS"}, "[그림 1]")
    tasks = {r["values"]["task"] for r in behind["infographic"][0]["data"]["rows"]}
    assert {"1.2 중간보고", "2.1 연계 수집"} <= tasks
