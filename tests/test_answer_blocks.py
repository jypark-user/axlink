"""답변에 끼우는 인포 템플릿 블록 (ARC-013 · SWFR.RAG.001 · SWFR.WEB.001).

목록 질문의 값과 필터가 SQL 에서 나오는지, 본문의 그림 자리 표식이 제대로 오가는지를 본다.
09.17 실측에서 닫힌 이슈 3건이 "아직 작업이 안 된" 목록에 섞여 나왔고 근거 게이트도 수치
검문도 그것을 못 잡았다. 그 회귀를 여기서 막는다.
"""

import json
from collections.abc import Iterator

import pytest

from app.ai.port import LlmResult
from app.config import settings
from app.db import tx
from app.rag import answer, blocks, entity_table
from app.rag import service as ask_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업


@pytest.fixture
def issues():
    """열린 것 둘, 닫힌 것 하나. 수집 없이 표준 모델에 넣고 끝나면 지운다."""
    rows = [
        ("GH-8801", "열린 이슈 가", "OPEN", "MAJOR"),
        ("GH-8802", "열린 이슈 나", "IN_PROGRESS", "MINOR"),
        ("GH-8803", "닫힌 이슈 다", "CLOSED", "MINOR"),
        ("GH-8804", "열린 이슈 라", "OPEN", "BLOCKER"),
    ]
    with tx() as cur:
        for key, title, status, severity in rows:
            cur.execute(
                """
                insert into issue (project_id, issue_key, title, status, severity,
                                   source_kind, source_updated_at)
                values (%s, %s, %s, %s, %s, 'MANUAL', '2026-09-01T00:00:00Z')
                """,
                (PID, key, title, status, severity),
            )
    yield {"open": 3, "closed": 1}
    with tx() as cur:
        cur.execute(
            "delete from issue where issue_key in ('GH-8801','GH-8802','GH-8803','GH-8804')"
        )


# ---------------------------------------------------------------- 표 만들기


@requires_db
def test_처리_중_이슈만_고르면_닫힌_것은_안_들어온다(issues):
    with tx() as cur:
        open_table = entity_table.build(cur, "ISSUE", entity_table.OPEN, [PID], 50)
        all_table = entity_table.build(cur, "ISSUE", entity_table.ALL, [PID], 50)
        closed_table = entity_table.build(cur, "ISSUE", entity_table.CLOSED, [PID], 50)

    assert open_table is not None and all_table is not None
    titles = [r.values["title"] for r in open_table.data.rows]
    assert {"열린 이슈 가", "열린 이슈 나", "열린 이슈 라"} <= set(titles)
    assert "닫힌 이슈 다" not in titles
    # 급한 것이 위로. "가장 급한 작업" 이 이 순서를 그대로 읽는다
    order = [titles.index(t) for t in ("열린 이슈 라", "열린 이슈 가", "열린 이슈 나")]
    assert order == sorted(order)
    statuses = {r.values["status"] for r in open_table.data.rows}
    assert not (statuses & {"RESOLVED", "CLOSED"})
    closed_total = closed_table.total if closed_table else 0
    assert open_table.total + closed_total == all_table.total
    # 상태가 표의 열로 들어가야 사람이 눈으로 확인할 수 있다
    assert [c.key for c in open_table.data.columns][:2] == ["title", "status"]
    assert "처리 중 이슈" in open_table.title


@requires_db
def test_범위_문장은_전체인지_일부인지_말한다(issues):
    with tx() as cur:
        whole = entity_table.build(cur, "ISSUE", entity_table.ALL, [PID], 50)
        clipped = entity_table.build(cur, "ISSUE", entity_table.ALL, [PID], 2)
    assert whole is not None
    assert f"전체 {whole.total}건" in whole.scope_line
    assert clipped is not None and "앞 2건" in clipped.scope_line
    assert clipped.data.truncated is True


@requires_db
def test_값이_없으면_표를_만들지_않는다():
    with tx() as cur:
        assert entity_table.build(cur, "ISSUE", entity_table.OPEN, [], 50) is None
        assert entity_table.build(cur, "NOPE", entity_table.ALL, [PID], 50) is None


def test_아는_종류만_표로_간다():
    assert entity_table.FROM_SOURCE_TYPE["DOCUMENT_UPLOAD"] == "WORK_PRODUCT"
    assert set(entity_table.FROM_SOURCE_TYPE.values()) <= set(entity_table.ENTITIES)


# ---------------------------------------------------------------- 그림 자리


def test_표식은_각주와_섞이지_않는다():
    text = "이슈는 7건이다[1]. 목록은 다음과 같다.\n[그림 1]\n추이는 [그림 2] 와 같다."
    assert blocks.used_slots(text) == {1, 2}
    assert blocks.used_slots("근거는 [1] 과 [12] 다") == set()
    assert blocks.marker_for(3) == "[그림 3]"


def test_안_쓴_그림은_끝에_붙는다():
    made = [
        blocks.Block(slot=1, template="DATA_TABLE", title="가", data=None, lines=[]),
        blocks.Block(slot=2, template="BAR_CHART", title="나", data=None, lines=[]),
    ]
    assert blocks.append_missing("본문 [그림 1] 끝", made) == "\n\n[그림 2]"
    assert blocks.append_missing("[그림 1][그림 2]", made) == ""
    assert blocks.append_missing("표식 없음", made) == "\n\n[그림 1]\n[그림 2]"


def test_표식의_번호는_수치로_세지_않는다():
    """[그림 1] 의 1 을 지어낸 수치로 보면 멀쩡한 답에 경고가 붙는다."""
    assert answer.numbers_in("이슈 현황이다 [그림 1]") == set()
    assert answer.ungrounded_numbers("[그림 2] 를 보라", ["근거"]) == []
    assert answer.numbers_in("이슈 7건 [그림 1]") == {"7"}


def test_프롬프트에는_앞부분만_넣는다():
    """본문은 목록을 다시 나열하지 않으므로 성격을 알 만큼만 있으면 된다. 전체를 넣으면
    프롬프트가 불어나 모델이 시간 초과로 끊긴다 (09.17 실측, 요구사항 41건)."""
    many = blocks.Block(
        slot=1, template="DATA_TABLE", title="요구사항 목록", data=None,
        lines=[f"- 코드 R-{i:03d}" for i in range(41)], note="요구사항 목록 전체 41건",
    )
    section = blocks.prompt_section(many)
    assert section.count("- 코드 ") == blocks.PROMPT_ROWS
    assert f"나머지 {41 - blocks.PROMPT_ROWS}개는 그림에 있다" in section
    assert "전체 41건" in section  # 건수는 잘리지 않는다


def test_프롬프트_절은_범위와_자리를_같이_준다():
    block = blocks.Block(
        slot=1, template="DATA_TABLE", title="처리 중 이슈", data=None,
        lines=["- 제목 가 · 상태 OPEN"], note="처리 중 이슈 전체 3건",
    )
    section = blocks.prompt_section(block)
    assert "## 그림 1 (처리 중 이슈)" in section
    assert "전체 3건" in section and "제목 가" in section
    rule = blocks.placement_rule([block])
    assert "그림 1: 처리 중 이슈" in rule
    assert "[그림 1] 라고만 쓴다" in rule
    assert "등호나 제목을 붙이지" in rule  # 모델이 예시를 베껴 "[그림 1]=제목" 을 쓰던 것을 막는다
    assert "다시 나열하지" in rule


# ---------------------------------------------------------------- 끝단


class _Scripted:
    def __init__(self, route: dict, text: str) -> None:
        self.route, self.text = route, text
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, *, json_schema=None) -> LlmResult:
        return LlmResult(text=json.dumps(self.route, ensure_ascii=False), model="scripted")

    def stream(self, system: str, user: str, *, json_schema=None) -> Iterator[str]:
        self.prompts.append(user)
        raw = json.dumps({"answer": self.text}, ensure_ascii=False) if json_schema else self.text
        for i in range(0, len(raw), 9):
            yield raw[i : i + 9]


def _events(res) -> list[tuple[str, dict]]:
    out, event = [], None
    for line in res.iter_lines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:") and event:
            out.append((event, json.loads(line[5:])))
    return out


def _ask(client, token: str, conversation_id: str, question: str):
    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/messages",
        json={"question": question, "projectScope": []},
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
    ) as res:
        assert res.status_code == 200, res.read()
        return _events(res)


@pytest.fixture
def conversation(client, client_token):
    made: list[tuple[str, str]] = []

    def _new() -> tuple[str, str]:
        token = client_token("r2")
        res = client.post(
            "/api/conversations",
            json={"title": "블록 시험", "projectScope": [PID]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201, res.text
        made.append((res.json()["id"], token))
        return made[-1]

    yield _new
    for cid, token in made:
        client.delete(f"/api/conversations/{cid}", headers={"Authorization": f"Bearer {token}"})


@requires_db
def test_목록_질문은_표를_싣고_상태_조건이_지켜진다(client, conversation, monkeypatch, issues):
    with tx() as cur:
        row = cur.execute(
            "select count(*) filter (where status in ('RESOLVED','CLOSED')) as closed, "
            "count(*) filter (where status not in ('RESOLVED','CLOSED')) as open from issue "
            "where project_id = %s",
            (PID,),
        ).fetchone()

    scripted = _Scripted(
        {"route": "DOCUMENT", "list": "ISSUE", "listFilter": "OPEN", "query": "작업 안 된 이슈"},
        "처리 중인 이슈는 다음과 같습니다.\n[그림 1]",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "아직 작업이 안 된 이슈목록 조회해줘")
    names = [e for e, _ in events]
    assert names[-1] == "done" and events[-1][1]["finishReason"] == "STOP"
    assert names.index("infographic") > names.index("sources")

    routing_info = events[0][1]["routing"]
    assert routing_info["listing"] == "ISSUE" and routing_info["listingStatus"] == "OPEN"
    assert routing_info["viz"] == "DATA_TABLE"

    block = next(d for e, d in events if e == "infographic")
    assert block["slot"] == 1 and block["template"] == "DATA_TABLE"
    assert len(block["data"]["rows"]) == row["open"]
    statuses = {r["values"]["status"] for r in block["data"]["rows"]}
    assert not (statuses & {"RESOLVED", "CLOSED"})  # 닫힌 것이 섞이면 안 된다
    assert str(row["open"]) in (block["note"] or "")

    # 표의 행이 프롬프트에 들어가고, 본문은 표식만 남긴다
    assert "## 그림 1" in scripted.prompts[0]
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "[그림 1]" in text and "※" not in text

    saved = client.get(
        f"/api/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    ).json()[1]
    assert len(saved["infographics"]) == 1
    assert saved["infographics"][0]["template"] == "DATA_TABLE"
    # 소요 시간은 화면에 작게 보인다. 끝난 답에는 늘 있다
    assert isinstance(saved["latencyMs"], int) and saved["latencyMs"] >= 0


@requires_db
def test_본문이_표식을_빠뜨리면_끝에_붙는다(client, conversation, monkeypatch, issues):
    scripted = _Scripted(
        {"route": "DOCUMENT", "list": "ISSUE", "listFilter": "ALL", "query": "이슈"},
        "이슈 현황입니다.",  # 표식을 안 썼다
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈 목록")
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert text.strip().endswith("[그림 1]")


@requires_db
def test_집계와_목록을_같이_물으면_그림이_둘이다(client, conversation, monkeypatch, issues):
    scripted = _Scripted(
        {"route": "AGGREGATE", "measure": "issue_count", "dimensions": ["issue_status"],
         "template": "BAR_CHART", "title": "상태별 이슈", "list": "ISSUE", "listFilter": "ALL"},
        "요약입니다. [그림 1] 목록은 [그림 2] 입니다.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈 몇 건이고 목록도 줘")
    made = [d for e, d in events if e == "infographic"]
    assert [b["slot"] for b in made] == [1, 2]
    assert [b["template"] for b in made] == ["BAR_CHART", "DATA_TABLE"]


def test_값이_하나뿐인_집계는_그림을_안_그린다():
    from app.semantic.models import WidgetColumn, WidgetDataResponse, WidgetRow

    def data(rows, dims):
        return WidgetDataResponse(
            measure="m", measureLabel="지표", unit="건", dimensions=dims,
            columns=[WidgetColumn(key="value", label="값", type="number")],
            rows=[WidgetRow(values=v) for v in rows], total=None, previousTotal=None,
            target=None, appliedProjectIds=[], truncated=False, generatedAt="",
        )

    assert blocks.worth_drawing(data([{"value": 7}], [])) is False
    assert blocks.worth_drawing(data([], [])) is False
    assert blocks.worth_drawing(data([{"d0": "OPEN", "value": 5}], ["issue_status"])) is False
    two = data([{"d0": "OPEN", "value": 5}, {"d0": "CLOSED", "value": 2}], ["issue_status"])
    assert blocks.worth_drawing(two) is True
    trend = data([{"d0": "2026-08", "value": 3}, {"d0": "2026-09", "value": 4}], ["period_month"])
    assert blocks.worth_drawing(trend) is True
