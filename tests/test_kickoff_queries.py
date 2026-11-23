"""착수보고 대표 질의세트 7종 중 11-23 실측에서 답이 빗나가던 질문들.

- 이슈 번호·요구사항 코드를 적은 질문은 글자 그대로 찾는다(lookup)
- 「이번 달 마일스톤 현황」은 마일스톤 표로 답한다(milestones)
- 「지난 보고 이후 변경된 사항」은 기간 안에 생긴 일을 센다(changes)
- 「미제출 산출물」은 미제출 산출물 수 카드와 같은 범위로 보인다
- 「리스크와 대응 상태」는 대응 칸을 보인다
"""

from datetime import date

import pytest

from app.db import tx
from app.rag import changes, entity_table, lookup, milestones, number_guard
from app.rag import service as ask_service
from app.rag.question_period import ActivityRange
from tests.conftest import requires_db
from tests.test_answer_blocks import (
    _ask,
    _Scripted,
    conversation,  # noqa: F401 — 픽스처
)

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업
NOBODY = "c0000000-0000-4000-8000-0000000000ff"  # 없는 사업. 범위가 비었을 때

TODAY = date(2020, 1, 20)


def test_질문에_적힌_이슈_번호와_요구사항_코드를_읽는다():
    keys, codes = lookup.refs("이슈 gh-23 과 RM-204, SWFR.CON.004 를 보여줘. GH-23 다시")
    assert keys == ["GH-23", "RM-204"]
    assert codes == ["SWFR.CON.004"]
    # 맨 #17 은 어느 도구인지 몰라 읽지 않는다(CLAUDE.md 3절). 버전 같은 말도 아니다
    assert lookup.refs("이슈 #17 과 v1.2 와 bge-m3") == ([], [])


def test_기간_길이는_날짜로_읽지_않는다():
    assert number_guard.dates_in("지난 7일 동안 문서가 올라왔다") == set()
    assert number_guard.dates_in("최근 30일 사이") == set()
    assert number_guard.dates_in("11월 7일에 올라왔다") == {(None, 11, 7)}


@pytest.fixture
def traced():
    """코드가 있는 요구사항 하나에 구현 이슈 하나와 시험 커밋 하나."""
    with tx() as cur:

        def one(sql: str, params: tuple) -> str:
            return str(cur.execute(sql + " returning id", params).fetchone()["id"])

        req = one(
            "insert into requirement (project_id, code, title, status, source_kind)"
            " values (%s, 'SWFR.TST.991', '대표 질의 시험 요구사항', 'DEFINED', 'MANUAL')",
            (PID,),
        )
        issue = one(
            "insert into issue (project_id, issue_key, title, status, severity, assignee,"
            " source_kind, source_created_at)"
            " values (%s, 'GH-8911', '대표 질의 시험 이슈', 'IN_PROGRESS', 'MAJOR', '홍길동',"
            " 'MANUAL', '2020-01-15T01:00:00Z')",
            (PID,),
        )
        commit = one(
            "insert into code_change (project_id, kind, title, ref_name, state, occurred_at)"
            " values (%s, 'COMMIT', '대표 질의 시험 커밋', 'abcdef1234', 'MERGED',"
            " '2020-01-16T01:00:00Z')",
            (PID,),
        )
        for from_type, from_id, kind in (
            ("ISSUE", issue, "IMPLEMENTS"),
            ("CODE_CHANGE", commit, "TESTS"),
        ):
            cur.execute(
                "insert into trace_link (project_id, from_type, from_id, to_type, to_id,"
                " link_kind, origin) values (%s, %s, %s, 'REQUIREMENT', %s, %s, 'MANUAL')",
                (PID, from_type, from_id, req, kind),
            )
    yield {"req": req, "issue": issue, "commit": commit}
    with tx() as cur:
        cur.execute("delete from trace_link where to_id = %s", (req,))
        cur.execute("delete from code_change where id = %s", (commit,))
        cur.execute("delete from issue where id = %s", (issue,))
        cur.execute("delete from requirement where id = %s", (req,))


@requires_db
def test_이슈_번호로_찾으면_상태와_연결_요구사항을_표로(traced):
    with tx() as cur:
        found = lookup.find(cur, "이슈 GH-8911 의 내용과 처리 상태를 알려줘", [PID], 1)
        elsewhere = lookup.find(cur, "이슈 GH-8911 상태", [NOBODY], 1)
    assert found and not elsewhere  # 범위 밖 사업의 이슈는 찾지 않는다
    block = found.blocks[0]
    row = block.data.rows[0].values
    assert block.title == "이슈 GH-8911"
    assert row["status"] == "진행중" and row["severity"] == "중대"
    assert row["assignee"] == "홍길동" and row["requirements"] == "SWFR.TST.991"


@requires_db
def test_요구사항_코드로_찾으면_설계_구현_시험_칸별_건수를_준다(traced):
    with tx() as cur:
        found = lookup.find(cur, "SWFR.TST.991 과 연결된 설계·시험 항목", [PID], 1)
    block = found.blocks[0]
    assert block.title == "SWFR.TST.991 추적 연결"
    kinds = [r.values["kind"] for r in block.data.rows]
    assert kinds == ["구현", "시험"]  # 화면의 칸 순서
    assert block.data.rows[0].values["state"] == "진행중"
    # 0건인 칸도 줄로 있어야 「설계 연결은 없다」를 검문이 통과시킨다
    assert "- 설계 연결 0건" in block.lines and "- 시험 연결 1건" in block.lines
    checker = number_guard.Checker(
        ask_service._facts(None, found.blocks, [], None), question="SWFR.TST.991"
    )
    assert checker.check("구현 1건과 시험 1건이 연결되어 있고 설계는 0건입니다.") == []
    assert checker.check("시험 항목은 3건입니다.") != []


@requires_db
def test_이슈_번호를_물으면_유사도_게이트에_막히지_않는다(
    client, conversation, monkeypatch, traced  # noqa: F811
):
    scripted = _Scripted(
        {"route": "DOCUMENT", "query": "GH-8911"}, "이슈 GH-8911 은 진행중입니다.\n[그림 1]"
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈 GH-8911의 내용과 처리 상태를 알려줘")
    assert events[-1][1]["finishReason"] == "STOP"
    block = next(d for e, d in events if e == "infographic")
    assert block["title"] == "이슈 GH-8911"
    assert "## 그림 1 (이슈 GH-8911)" in scripted.prompts[0]


@requires_db
def test_미제출_산출물은_미제출_수_카드와_같은_범위다():
    with tx() as cur:
        table = entity_table.build(cur, "WORK_PRODUCT", entity_table.MISSING, [PID], 100)
        n = cur.execute(
            "select count(*) filter (where status = 'NONE') as n from work_product"
            " where project_id = %s and is_current and applicable",
            (PID,),
        ).fetchone()["n"]
    if n == 0:
        assert table is None
        return
    assert table is not None and table.total == n
    assert table.title == "미제출 산출물"
    rows = [r.values for r in table.data.rows]
    assert {r["status"] for r in rows} == {"미제출"}
    # 유형은 코드가 아니라 화면의 이름이다
    assert not any(r["type"].isupper() for r in rows)


@requires_db
def test_리스크_표에_대응_칸이_있다():
    keys = [k for k, _, _ in entity_table.ENTITIES["RISK"].columns]
    assert "mitigation" in keys
    with tx() as cur:
        rid = cur.execute(
            "insert into risk (project_id, title, severity, mitigation, owner, source_kind)"
            " values (%s, '대표 질의 시험 리스크', 'HIGH', '대체 장비 확보', '박담당', 'MANUAL')"
            " returning id",
            (PID,),
        ).fetchone()["id"]
    try:
        with tx() as cur:
            table = entity_table.build(cur, "RISK", entity_table.OPEN, [PID], 100)
        row = next(
            r.values for r in table.data.rows if r.values["title"] == "대표 질의 시험 리스크"
        )
        assert row["mitigation"] == "대체 장비 확보"
    finally:
        with tx() as cur:
            cur.execute("delete from risk where id = %s", (rid,))


@pytest.fixture
def stones():
    rows = (
        # (제목, 기한, 상태, 닫힌 시각)
        ("시험 M1", "2020-01-05", "CLOSED", "2020-01-04T10:00:00Z"),
        ("시험 M2", "2020-01-10", "CLOSED", "2020-01-12T10:00:00Z"),
        ("시험 M3", "2020-01-15", "OPEN", None),
        ("시험 M4", "2020-01-31", "OPEN", None),
        ("시험 M5", "2020-02-20", "OPEN", None),
    )
    with tx() as cur:
        ids = [
            str(
                cur.execute(
                    "insert into milestone (project_id, external_id, title, due_on, state,"
                    " closed_at) values (%s, %s, %s, %s, %s, %s) returning id",
                    (PID, f"kickoff-test-{i}", t, d, s, c),
                ).fetchone()["id"]
            )
            for i, (t, d, s, c) in enumerate(rows)
        ]
    yield ids
    with tx() as cur:
        cur.execute("delete from milestone where id = any(%s::uuid[])", (ids,))


@requires_db
def test_마일스톤_현황은_한_줄씩_상태를_준다(stones):
    with tx() as cur:
        block, text = milestones.build(cur, "마일스톤 현황 알려줘", [PID], 1, TODAY)
    assert text is None and block.title == "마일스톤 현황"
    state = {r.values["title"]: r.values["state"] for r in block.data.rows}
    assert state["시험 M1"] == "기한 안 닫힘"
    assert state["시험 M2"] == "늦게 닫힘"
    assert state["시험 M3"] == "기한 지남"
    assert state["시험 M4"] == "진행 중"


@requires_db
def test_이번_달_마일스톤은_이달_말_기한까지_본다(stones):
    with tx() as cur:
        block, _ = milestones.build(cur, "이번 달 마일스톤 현황은?", [PID], 1, TODAY)
        none, text = milestones.build(cur, "이번 달 마일스톤 현황은?", [NOBODY], 1, TODAY)
    titles = {r.values["title"] for r in block.data.rows}
    assert {"시험 M1", "시험 M4"} <= titles and "시험 M5" not in titles
    assert block.title == "2020-01-01~2020-01-31 기한 마일스톤"
    assert none is None and "마일스톤" in text


def test_준수율을_물으면_마일스톤_표로_가로채지_않는다():
    assert milestones.asks("이번 달 마일스톤 현황은?")
    assert not milestones.asks("마일스톤 일정 준수율은?")


@requires_db
def test_마일스톤을_물으면_모델이_지표를_골라도_표로_답한다(
    client, conversation, monkeypatch, stones  # noqa: F811
):
    scripted = _Scripted(
        {"route": "AGGREGATE", "measure": "schedule_compliance_rate", "template": "STAT_CARD",
         "query": "마일스톤"},
        "마일스톤 현황입니다.\n[그림 1]",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "마일스톤 현황은?")
    block = next(d for e, d in events if e == "infographic")
    assert block["data"]["measure"] == "entity_milestone"


def test_변경_질문을_알아본다():
    assert changes.asks("지난 보고 이후 변경된 사항을 요약해줘")
    assert changes.asks("최근 30일 동안 바뀐 것 알려줘")
    assert not changes.asks("변경 요청서 몇 건이야")
    assert not changes.asks("진척률이 지난주보다 얼마나 바뀌었어")


@requires_db
def test_변경_사항은_기간_안에_생긴_일을_센다(traced):
    with tx() as cur:
        block = changes.build(cur, "최근 7일 동안 바뀐 것", [PID], 1, TODAY)
        default = changes.build(cur, "지난 보고 이후 변경된 사항", [PID], 1, TODAY)
    lines = set(block.lines)
    assert block.title == "2020-01-13~2020-01-20 변경 사항"
    assert "- 새로 등록된 이슈 1건" in lines and "- 커밋 1건" in lines
    assert "- 활동이 있는 요구사항 1건" in lines
    # 질문에 기간이 없으면 7일로 보고 그렇다고 적는다
    assert "지난 보고 날짜는 시스템에 없어 7일 전부터" in default.note
    assert changes.window("최근 3일", TODAY)[0] == ActivityRange(date(2020, 1, 17), TODAY)


@requires_db
def test_결함을_물으면_결함만_꺼내고_없으면_없다고_한다(
    client, conversation, monkeypatch  # noqa: F811
):
    scripted = _Scripted(
        {"route": "DOCUMENT", "list": "ISSUE", "listFilter": "OPEN", "query": "결함"},
        "처리 중 결함입니다.\n[그림 1]",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    with tx() as cur:
        had = cur.execute(
            "select count(*) as n from issue where project_id = %s and issue_kind = 'DEFECT'"
            " and status not in ('RESOLVED', 'CLOSED')",
            (PID,),
        ).fetchone()["n"]
    conversation_id, token = conversation()
    if had == 0:
        events = _ask(client, token, conversation_id, "미해결 결함 중 심각도가 높은 건을 알려줘")
        assert events[-1][1]["finishReason"] == "NO_DATA"
        text = "".join(d["text"] for e, d in events if e == "delta")
        assert "처리 중인 결함으로 분류된 이슈가 없습니다" in text
        assert scripted.prompts == []  # 이슈 조각으로 내려가 모델을 부르지 않는다

    with tx() as cur:
        iid = cur.execute(
            "insert into issue (project_id, issue_key, title, status, severity, issue_kind,"
            " source_kind) values (%s, 'GH-8921', '대표 질의 시험 결함', 'OPEN', 'CRITICAL',"
            " 'DEFECT', 'MANUAL') returning id",
            (PID,),
        ).fetchone()["id"]
    try:
        events = _ask(client, token, conversation_id, "미해결 결함 중 심각도가 높은 건을 알려줘")
        block = next(d for e, d in events if e == "infographic")
        assert block["title"] == "처리 중 결함"
        assert "대표 질의 시험 결함" in {r["values"]["title"] for r in block["data"]["rows"]}
        with tx() as cur:
            general = entity_table.build(cur, "ISSUE", entity_table.ALL, [PID], 500)
        titles = {r.values["title"] for r in general.data.rows} if general else set()
        assert "대표 질의 시험 결함" not in titles  # 일반 이슈는 결함을 뺀다(DEC-02)
    finally:
        with tx() as cur:
            cur.execute("delete from issue where id = %s", (iid,))


@pytest.fixture
def unmet():
    """검증·인수 전 요구사항 셋(기능 둘, 품질 하나)과 검증된 것 하나."""
    with tx() as cur:
        ids = [
            str(cur.execute(
                "insert into requirement (project_id, code, title, status, source_kind)"
                " values (%s, %s, %s, %s, 'MANUAL') returning id",
                (PID, code, f"미달성 시험 {code}", status),
            ).fetchone()["id"])
            for code, status in (
                ("SWFR.TST.981", "DEFINED"), ("SWFR.TST.982", "IMPLEMENTED"),
                ("QUR.TST.983", "DEFINED"), ("SWFR.TST.984", "VERIFIED"),
            )
        ]
    yield ids
    with tx() as cur:
        cur.execute("delete from requirement where id = any(%s::uuid[])", (ids,))


@requires_db
def test_미달성_요구사항_표는_검증_인수_전이고_묶음별_건수를_서버가_센다(unmet):
    with tx() as cur:
        table = entity_table.build(cur, "REQUIREMENT", entity_table.OPEN, [PID], 100)
    assert table is not None and table.title == "검증·인수 전 요구사항"
    codes = {r.values["code"] for r in table.data.rows}
    assert {"SWFR.TST.981", "SWFR.TST.982", "QUR.TST.983"} <= codes
    assert "SWFR.TST.984" not in codes
    groups = [line for line in table.lines if line.startswith(("- 종류", "- 영역", "- 상태"))]
    assert any(line.startswith("- 종류 품질: ") for line in groups), groups
    # 묶음 건수는 한 줄에 하나다. 검문이 라벨을 섞지 않는다
    assert all(line.count("건") == 1 for line in groups)
    facts = number_guard.facts_from_lines(table.lines, "그림 1", subject=table.title)
    n_quality = next(line for line in groups if line.startswith("- 종류 품질"))
    value = n_quality.rsplit(": ", 1)[1].removesuffix("건")
    checker = number_guard.Checker(facts, question="현재 미달성된 요구사항 정리")
    assert checker.check(f"품질 요구사항은 {value}건입니다.") == []


@requires_db
def test_목록_질문에는_문서_조각을_답_재료로_넣지_않는다(
    client, conversation, monkeypatch, unmet  # noqa: F811
):
    """11-23: 요구사항정의서 조각의 41건·14개를 끌어와 문장을 짓다 검문에 막혔다."""
    scripted = _Scripted(
        {"route": "DOCUMENT", "list": "REQUIREMENT", "listFilter": "OPEN", "query": "미달성"},
        "검증·인수 전 요구사항 목록입니다.\n[그림 1]",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "현재 미달성된 요구사항 정리")
    assert events[-1][1]["finishReason"] == "STOP"
    sources = next(d for e, d in events if e == "sources")["sources"]
    assert sources == []
    assert "## 그림 1 (검증·인수 전 요구사항)" in scripted.prompts[0]
