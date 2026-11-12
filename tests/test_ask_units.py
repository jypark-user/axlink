"""AI 질의의 순수 계산. DB·모델 없이 돈다.

순위 융합, 수치 검문, 라우팅 결정, 스트림 조각 처리가 여기 있다.
DB 를 타는 흐름은 test_ask_api.py, 실모델은 test_rag_live.py 가 본다.
"""

import json

import httpx

from app.ai import llm
from app.ai.port import LlmResult
from app.config import settings
from app.rag import answer, number_guard, routing, search
from app.rag.search import RetrievedChunk
from app.semantic.catalog import Catalog, DimensionDef, MeasureDef
from app.semantic.models import WidgetColumn, WidgetDataResponse, WidgetRow

# ---------------------------------------------------------------- 검색


def test_rrf_는_두_목록에_다_있는_것을_위로_올린다():
    scores = search.rrf([["a", "b", "c"], ["c", "d"]], k=60)
    ranked = sorted(scores, key=scores.get, reverse=True)
    assert ranked[0] == "c"  # 벡터 3위 + 어휘 1위 > 벡터 1위 단독
    assert scores["a"] == 1 / 61
    assert scores["c"] == 1 / 63 + 1 / 61


def test_게이트는_코사인_유사도로_본다():
    chunk = _chunk("x", similarity=0.7)
    assert search.SearchResult([chunk], max_similarity=0.7, candidate_count=1).passes_gate(0.6)
    assert not search.SearchResult([chunk], max_similarity=0.5, candidate_count=1).passes_gate(0.6)
    assert not search.SearchResult([], max_similarity=0.9, candidate_count=0).passes_gate(0.6)


# ---------------------------------------------------------------- 수치 검문


def test_숫자_추출은_각주와_날짜를_뺀다():
    text = "이행률은 42.5% 이고[1] 2026-09-14 기준 1,200건 중 3건이다. 9월 보고서 [2]"
    assert number_guard.quantities(text) == [("42.5", "%"), ("1200", "건"), ("3", "건")]


def test_집계에_없는_숫자만_걸린다():
    facts = number_guard.facts_from_lines(
        ["- 요구사항 이행률: 42.5%", "- 전체: 1200건"], "집계", subject="요구사항 이행률"
    )
    ck = number_guard.Checker(facts)
    assert ck.check("이행률은 42.5% 로 1,200건 기준이다") == []
    assert [v.value for v in ck.check("이행률은 43% 로 1200건 기준이다")] == ["43"]
    # 소수 표기가 달라도 같은 값이면 통과한다
    assert ck.check("이행률은 42.50% 이다") == []


def test_집계_줄은_차원_라벨과_값을_같이_적는다():
    data = _data(
        dimensions=["issue_status"],
        columns=[
            WidgetColumn(key="d0", label="이슈 상태", type="string"),
            WidgetColumn(key="value", label="이슈 건수", type="number"),
        ],
        rows=[
            WidgetRow(values={"d0": "OPEN", "value": 7}),
            WidgetRow(values={"d0": "CLOSED", "value": 12.0}),
        ],
        total=WidgetRow(values={"value": 19}),
    )
    lines = answer.aggregate_lines(data)
    assert lines == ["- 이슈 상태 열림: 7건", "- 이슈 상태 종료: 12건", "- 이슈 건수 전체: 19건"]
    # 검문은 이 줄을 근거로 삼는다. 줄을 베낀 답은 통과한다.
    ck = number_guard.Checker(number_guard.facts_from_lines(lines, "집계", subject="이슈 건수"))
    assert ck.check("열린 이슈 7건, 닫힌 이슈 12건, 모두 19건") == []


def test_집계_값이_없으면_없다고_적는다():
    lines = answer.aggregate_lines(_data(dimensions=[], columns=[], rows=[], total=None))
    assert lines == ["- 이슈 건수: 집계된 값이 없음"]


def test_프롬프트는_근거에_번호와_원문_위치를_붙인다():
    chunk = _chunk("c1", heading=["3. 계약사항", "3.2 납품"], content="납품 산출물은 22종이다.")
    prompt = answer.user_prompt("납품 산출물은?", [chunk], None)
    assert "[1] 과업지시서 (3. 계약사항 > 3.2 납품)" in prompt
    assert "납품 산출물은 22종이다." in prompt
    assert "## 집계 값" not in prompt


def test_원문_위치는_표제_쪽_행을_잇고_걸치면_범위로_쓴다():
    # 쪽·행 범위는 청크 meta 에서 온다 (SWFR.RAG.003). 화면과 프롬프트가 같은 문장을 쓴다
    with_heading = _chunk("c", heading=["3. 계약사항"], page_no=7)
    assert answer.location_text(with_heading) == "3. 계약사항 / p.7"
    assert answer.location_text(_chunk("c", page_no=7, page_end=9)) == "p.7~9"
    assert answer.location_text(_chunk("c", page_no=7, page_end=7)) == "p.7"
    assert (
        answer.location_text(_chunk("c", heading=["시트: WBS"], row_start=12, row_end=18))
        == "시트: WBS / 12~18행"
    )
    assert answer.location_text(_chunk("c", row_start=12, row_end=12)) == "12행"
    assert answer.location_text(_chunk("c")) is None
    assert answer.location_label(_chunk("c", page_no=2)) == " (p.2)"


def test_HWP_원문_위치는_쪽_대신_문단과_표_행으로_쓴다():
    # DEC-21. 없는 쪽 번호는 만들지 않는다
    assert (
        answer.location_text(
            _chunk("c", para_start=3, para_end=4, table_no=1, table_row_start=2, table_row_end=2)
        )
        == "문단 3~4 / 표 1 · 2행"
    )
    assert (
        answer.location_text(_chunk("c", heading=["2. 검토 결과"], para_start=5, para_end=5))
        == "2. 검토 결과 / 문단 5"
    )
    assert answer.location_text(_chunk("c", table_no=1, table_end=2)) == "표 1~2"


def test_XLSX_표_조각은_질문이_가리키는_행만_남기고_위치를_좁힌다():
    # 시트 하나가 조각 하나면 출처가 「2~7행」이 되고 답인 행이 잘린다(AC-060-11, DEF-V031)
    table = "\n".join([
        "시트: WBS",
        "| 행 | WBS ID | 업무분류 | 산출물 |",
        "| --- | --- | --- | --- |",
        "| 4 | 3.2 | 설계 | SW설계서 |",
        "| 5 | 3.3 | 구현 | 프로그램 목록 |",
        "| 6 | 3.4 | 시험 | 시험결과서 |",
    ])
    chunk = _chunk("c", heading=["시트: WBS"], content=table, row_start=4, row_end=6)
    focused = answer.focus_rows(chunk, "WBS 3.3 산출물")
    assert answer.location_text(focused) == "시트: WBS / 5행"
    assert "프로그램 목록" in focused.content and "SW설계서" not in focused.content
    assert "| 행 | WBS ID |" in focused.content  # 머리글은 남긴다
    # 맞는 행이 없거나 모두 맞으면, 표가 아닌 조각이면 그대로다
    assert answer.focus_rows(chunk, "일정 지연") is chunk
    assert answer.focus_rows(chunk, "| 3") is chunk
    plain = _chunk("d", content="3.3 구현")
    assert answer.focus_rows(plain, "3.3") is plain


def test_출처_조각은_위치를_앞에_두고_길이를_자른다():
    chunk = _chunk("c1", heading=["1장"], content="가 " * 400)
    text = answer.snippet(chunk, limit=50)
    assert text.startswith("1장\n")
    assert text.endswith("…")
    assert len(text) < 60


# ---------------------------------------------------------------- 생각 블록


def test_생각_블록은_조각_경계에_걸려도_걷어낸다():
    pieces = ["<thi", "nk>속으로 생각</th", "ink>답은 ", "이것", "이다."]
    assert "".join(answer.strip_think(iter(pieces))) == "답은 이것이다."


def test_생각_블록이_없으면_그대로_흘린다():
    pieces = ["답은 ", "<b>굵게</b> ", "이다."]
    assert "".join(answer.strip_think(iter(pieces))) == "답은 <b>굵게</b> 이다."


# ---------------------------------------------------------------- 라우팅


def test_읽을_수_없는_답은_문서_경로다():
    decision = routing.from_choice(_catalog(), None)
    assert decision.type == routing.DOCUMENT and decision.measure is None


def test_카탈로그에_없는_지표는_문서_경로로_내려간다():
    choice = {"route": "AGGREGATE", "measure": "no_such_measure", "query": "핵심어"}
    decision = routing.from_choice(_catalog(), choice)
    assert decision.type == routing.DOCUMENT
    assert decision.rewritten == "핵심어"


def test_집계_경로는_허용_차원만_남기고_템플릿을_정한다():
    choice = {
        "route": "aggregate",
        "measure": "issue_count",
        "dimensions": ["issue_status", "not_allowed"],
        "template": "bar_chart",
        "title": "이슈 상태별 건수",
    }
    decision = routing.from_choice(_catalog(), choice)
    assert decision.type == routing.AGGREGATE
    assert decision.measure is not None and decision.measure.key == "issue_count"
    assert decision.dimensions == ["issue_status"]
    assert decision.template == "BAR_CHART"
    assert decision.title == "이슈 상태별 건수"


def test_템플릿을_안_주면_차원_모양으로_고른다():
    choice = {"route": "AGGREGATE", "measure": "issue_count"}
    assert routing.from_choice(_catalog(), choice).template == "STAT_CARD"
    choice["dimensions"] = ["issue_status"]
    assert routing.from_choice(_catalog(), choice).template == "BAR_CHART"


def test_라우팅_프롬프트는_카탈로그_키를_그대로_싣는다():
    prompt = routing.system_prompt(_catalog())
    assert "issue_count" in prompt and "issue_status" in prompt
    assert "AGGREGATE" in prompt and "DOCUMENT" in prompt


# ---------------------------------------------------------------- LLM 스트림


def test_페이크_스트림을_이어_붙이면_complete_와_같다():
    port = llm.FakeLlm()
    assert "".join(port.stream("s", "u v w")) == port.complete("s", "u v w").text


def test_올라마_스트림은_NDJSON_조각을_순서대로_준다(monkeypatch):
    lines = [
        {"message": {"content": "안녕"}, "done": False},
        {"message": {"content": "하세요"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        body = "\n".join(json.dumps(line) for line in lines) + "\n"
        return httpx.Response(200, content=body.encode())

    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: real(transport=transport))

    port = llm.OllamaLlm("http://localhost:11434", "qwen3:4b", 5)
    assert list(port.stream("지시", "질문")) == ["안녕", "하세요"]
    assert seen["stream"] is True
    assert seen["think"] is False


# ---------------------------------------------------------------- 도우미


def _chunk(
    chunk_id: str,
    similarity: float = 0.8,
    heading: list[str] | None = None,
    content: str = "본문",
    **where,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        project_id="p",
        project_name="사업",
        source_type="DOCUMENT_UPLOAD",
        source_id="s",
        source_title="과업지시서",
        source_uri=None,
        chunk_index=0,
        content=content,
        heading_path=heading or [],
        page_no=where.pop("page_no", None),
        similarity=similarity,
        **where,
    )


def test_후속_질문은_앞_대화와_함께_모델에_가고_캐시되지_않는다():
    previous = routing.PreviousTurn(
        question="요구사항 이행률을 높이려면 어떻게 해야돼?",
        answer="시험 결과서를 올려 검증완료로 바꿔야 합니다. " * 40,
        measure_key="requirement_fulfillment_rate",
    )
    earlier = routing.PreviousTurn(
        question="미제출 산출물 목록 보여줘", answer="46건입니다.", topic="미제출 산출물"
    )
    content = routing.user_content("흐름을 그림으로 보여줘", [earlier, previous])
    assert content.startswith("## 앞 대화 (마지막이 직전)\n질문: 미제출 산출물 목록 보여줘")
    assert "답 (주제어 미제출 산출물): 46건입니다." in content
    assert "답 (지표 requirement_fulfillment_rate): 시험 결과서를" in content
    assert content.endswith("## 이번 질문\n흐름을 그림으로 보여줘")
    assert len(previous.excerpt()) <= routing.PREVIOUS_ANSWER_CHARS + 1  # 말줄임표
    # 앞 대화가 없으면 질문 문장 그대로다(캐시 키와 같은 문자열)
    assert routing.user_content("진척률은?", None) == "진척률은?"
    assert routing.user_content("진척률은?", []) == "진척률은?"
    # followUp 표식은 판정에 남고, 본문 프롬프트에도 앞 대화 절이 붙는다
    choice = {"route": "AGGREGATE", "measure": "open_issue_count", "followUp": True}
    assert routing.from_choice(_catalog(), choice).follow_up is True
    assert routing.from_choice(_catalog(), {"route": "OVERVIEW"}).follow_up is False
    prompt = answer.user_prompt("흐름을 그림으로 보여줘", [], None, previous=[previous])
    assert "## 앞 대화 (마지막이 직전)\n질문: 요구사항 이행률을 높이려면" in prompt
    assert "## 근거" in prompt


def test_단계_번호는_수치가_아니다():
    steps = "1) 시험 케이스에 코드를 적는다 → 2) 결과서를 올린다 → 3) 검증완료. 3단계면 끝."
    assert number_guard.quantities(steps) == []
    # 문장 속 건수는 여전히 잡는다
    assert number_guard.quantities("1) 결과서 3건을 올린다") == [("3", "건")]


def test_비율_지표는_분자_분모와_산출_근거를_같이_편다():
    data = _data(
        dimensions=[], columns=[WidgetColumn(key="value", label="요구사항 이행률", type="percent")],
        rows=[WidgetRow(values={"value": 0.0, "numerator": 0, "denominator": 41})], total=None,
    )
    data.basis = "검증완료 요구사항 수를 전체로 나눈 값이다. 시험 결과가 없으면 0% 다."
    lines = answer.aggregate_lines(data)
    assert lines[0] == "- 이슈 건수: 0건 (0건 / 41건)"  # _data 도우미의 지표명·단위
    assert lines[-1].startswith("- 산출 근거: 검증완료")
    # 검문은 분자·분모 숫자와 산출 근거 문장의 숫자(0%)도 근거로 안다
    ck = number_guard.Checker(number_guard.facts_from_lines(lines, "집계", subject="요구사항"))
    assert ck.check("검증된 요구사항이 41건 중 0건이라 0%입니다.") == []
    # 줄에 없는 비율은 나눗셈으로 만든 값이다
    assert [v.reason for v in ck.check("검증된 요구사항은 100%입니다.")] == ["근거에 없는 값"]


def _data(dimensions, columns, rows, total) -> WidgetDataResponse:
    return WidgetDataResponse(
        measure="issue_count",
        measureLabel="이슈 건수",
        unit="건",
        dimensions=dimensions,
        columns=columns,
        rows=rows,
        total=total,
        previousTotal=None,
        target=None,
        appliedProjectIds=["p"],
        truncated=False,
        generatedAt="2026-09-14T00:00:00Z",
    )


def _catalog() -> Catalog:
    catalog = Catalog()
    catalog.measures["issue_count"] = MeasureDef(
        key="issue_count",
        label="이슈 건수",
        description="이슈 수",
        base_table="issue",
        join_clause=None,
        row_filter=None,
        value_expr="count(*)",
        value_type="COUNT",
        unit="건",
        allowed_dimensions=("issue_status", "period_month"),
        allowed_filters=(),
        default_dimension="issue_status",
        target_value=None,
        status="ACTIVE",
    )
    catalog.dimensions["issue_status"] = DimensionDef(
        key="issue_status",
        label="이슈 상태",
        description="상태",
        select_expr="e.status",
        label_expr=None,
        requires_join=None,
        value_type="CATEGORY",
        status="ACTIVE",
    )
    catalog.dimensions["period_month"] = DimensionDef(
        key="period_month",
        label="월",
        description="월",
        select_expr="date_trunc('month', <TIME_COL>)",
        label_expr=None,
        requires_join=None,
        value_type="TIME",
        status="ACTIVE",
    )
    return catalog


class _Recorder:
    """LlmPort 흉내. complete 가 무엇을 받았는지 남긴다."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, json_schema=None) -> LlmResult:
        self.calls.append((system, user, json_schema))
        return LlmResult(text=self.text, model="recorder")

    def stream(self, system: str, user: str, *, json_schema=None):
        yield self.text


def test_decide_는_질문을_그대로_모델에_넘긴다():
    recorder = _Recorder('{"route": "DOCUMENT", "query": "납품 산출물"}')
    decision = routing.decide(_catalog(), recorder, "납품 산출물이 뭐지?")
    assert decision.type == routing.DOCUMENT and decision.rewritten == "납품 산출물"
    assert recorder.calls[0][1] == "납품 산출물이 뭐지?"
    assert recorder.calls[0][2] == routing.CHOICE_SCHEMA  # 라우팅은 출력 형식을 못 박는다


def test_올라마_스키마_모드는_format_과_온도를_박는다(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"model": "m", "message": {"content": "{}"}})

    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: real(transport=transport))

    # 문맥 길이는 모델별 설정에서 온다(ARC-011). 기본값도 근거 청크 5개는 담아야 한다.
    port = llm.OllamaLlm("http://x", "m", 5, num_ctx=settings.llm_num_ctx)
    port.complete("s", "u", json_schema=answer.ANSWER_SCHEMA)
    assert seen["format"] == answer.ANSWER_SCHEMA and seen["options"]["temperature"] == 0
    assert seen["options"]["num_ctx"] >= 4096

    seen.clear()
    port.complete("s", "u")
    assert "format" not in seen and "temperature" not in seen["options"]


# ---------------------------------------------------------------- JSON 답변 풀기


def test_JSON_답변은_문자열_값만_흘리고_이스케이프를_푼다():
    raw = json.dumps({"answer": '첫 줄 "인용"\n둘째 줄 \\ 끝'}, ensure_ascii=False)
    pieces = [raw[i : i + 3] for i in range(0, len(raw), 3)]  # 이스케이프가 조각에 걸린다
    assert "".join(answer.decode_answer(iter(pieces))) == '첫 줄 "인용"\n둘째 줄 \\ 끝'


def test_JSON_답변은_유니코드_이스케이프도_푼다():
    raw = json.dumps({"answer": "한글 😀 끝"})  # ensure_ascii 라 \\uXXXX 와 서러게이트 쌍
    pieces = [raw[i : i + 5] for i in range(0, len(raw), 5)]
    assert "".join(answer.decode_answer(iter(pieces))) == "한글 😀 끝"


def test_JSON_답변이_중간에_끊기면_받은_데까지_준다():
    pieces = ['{"answer": "여기까지 왔', "고 그다음은 없다"]
    assert "".join(answer.decode_answer(iter(pieces))) == "여기까지 왔고 그다음은 없다"


def test_JSON_형식을_벗어난_답은_그대로_준다():
    assert "".join(answer.decode_answer(iter(["그냥 문장이다"]))) == "그냥 문장이다"


def test_페이크_스트림은_스키마를_주면_JSON_으로_싼다():
    port = llm.FakeLlm()
    raw = "".join(port.stream("s", "u", json_schema=answer.ANSWER_SCHEMA))
    assert json.loads(raw) == {"answer": port.complete("s", "u").text}
    decoded = "".join(answer.decode_answer(port.stream("s", "u", json_schema=answer.ANSWER_SCHEMA)))
    assert decoded == port.complete("s", "u").text


# ---------------------------------------------------------------- 융합 순서


def test_융합은_RRF_로_후보를_고르고_코사인으로_줄을_세운다(monkeypatch):
    """벡터 1순위가 어휘 목록에 없다는 이유로 밀리면 안 된다(09.14 실측)."""
    rows = {
        "top": _row("top", 0.663), "both": _row("both", 0.604), "lex": _row("lex", 0.523),
        "v2": _row("v2", 0.636), "v3": _row("v3", 0.633),
    }
    monkeypatch.setattr(
        search, "vector_candidates",
        lambda *a, **k: [rows["top"], rows["v2"], rows["v3"], rows["both"]],
    )
    monkeypatch.setattr(
        search, "lexical_candidates", lambda *a, **k: [rows["lex"], rows["both"]]
    )
    monkeypatch.setattr(search.embedding_guard, "require_match", lambda *a, **k: None)
    found = search.search_with_vector(None, [0.0], "q", ["p"], top_k=3)
    assert [c.id for c in found.chunks] == ["top", "v2", "v3"]
    assert found.max_similarity == 0.663 and found.candidate_count == 5


def _row(chunk_id: str, similarity: float) -> dict:
    return {
        "id": chunk_id, "project_id": "p", "project_name": "사업", "source_type": "ISSUE",
        "source_id": "s", "source_title": chunk_id, "source_uri": None, "chunk_index": 0,
        "content": "본문", "meta_json": {}, "similarity": similarity,
    }


# ---------------------------------------------------------------- 목록 질문


def test_문서_경로의_list_는_아는_종류만_남긴다():
    choice = {"route": "DOCUMENT", "list": "issue", "query": "이슈 목록"}
    decision = routing.from_choice(_catalog(), choice)
    assert decision.type == routing.DOCUMENT
    assert decision.listing == "ISSUE"
    assert decision.rewritten == "이슈 목록"

    unknown = routing.from_choice(_catalog(), {"route": "DOCUMENT", "list": "COMMIT"})
    assert unknown.listing is None


def test_집계와_목록은_함께_올_수_있다():
    """숫자와 목록을 같이 묻는 질문이 있다. 둘은 따로 판정해 그림 두 장이 된다 (ARC-013)."""
    choice = {"route": "AGGREGATE", "measure": "issue_count", "list": "ISSUE"}
    decision = routing.from_choice(_catalog(), choice)
    assert decision.type == routing.AGGREGATE
    assert decision.listing == "ISSUE"


def test_목록_상태_조건은_아는_값만_남긴다():
    ok = routing.from_choice(
        _catalog(), {"route": "DOCUMENT", "list": "ISSUE", "listFilter": "open"}
    )
    assert ok.listing_status == "OPEN"
    unknown = routing.from_choice(
        _catalog(), {"route": "DOCUMENT", "list": "ISSUE", "listFilter": "미정"}
    )
    assert unknown.listing_status == "ALL"


def test_라우팅_프롬프트는_목록_종류를_알려준다():
    prompt = routing.system_prompt(_catalog())
    assert '"list"' in prompt
    # 무엇부터 할지 묻는 질문은 열린 이슈의 목록이다. 문서 검색으로 보내면 근거가 없어 막힌다
    assert "가장 급한 작업" in prompt and "listFilter OPEN" in prompt
    for key, label in routing.LISTABLE.items():
        assert f"{key}({label})" in prompt


def test_목록_범위_줄은_전체인지_일부인지_말한다():
    assert "전체 3건" in answer.listing_scope("이슈", 3, 3)
    partial = answer.listing_scope("요구사항", 60, 80)
    assert "총 80건" in partial and "앞 60건" in partial
    # 이 줄의 숫자는 근거로 친다. 답변이 총 건수를 말해도 지어낸 숫자가 아니다.
    ck = number_guard.Checker(number_guard.facts_from_lines([partial], "목록 범위"))
    assert ck.check("요구사항은 총 80건이다.") == []


def test_목록_프롬프트는_범위_절을_근거_앞에_둔다():
    scope = "사업 범위 안의 이슈 전체 0건이 아래 근거다."
    prompt = answer.user_prompt("이슈 목록", [], None, scope)
    assert prompt.index("## 목록 범위") < prompt.index("## 근거")


def test_차원_없이_막대만_고르면_나눠_세되_그림은_안_붙인다():
    """「일반 이슈가 몇 건이야」에 모델이 막대 템플릿만 적었다. 기본 차원(상태)으로 나눠 센
    값은 프롬프트에 들어가지만 나눠 보기를 묻지 않았으니 그림은 없다(UC-060-S02, 실모델)."""
    choice = {
        "route": "AGGREGATE", "measure": "issue_count", "dimensions": [], "template": "BAR_CHART",
    }
    decision = routing.from_choice(_catalog(), choice)
    assert decision.dimensions == ["issue_status"] and decision.breakdown is False
    # 나눠 보기를 물으면 그림까지
    choice["dimensions"] = ["issue_status"]
    assert routing.from_choice(_catalog(), choice).breakdown is True
    # 추이 템플릿은 그 자체가 나눠 보기다
    trend = {"route": "AGGREGATE", "measure": "issue_count", "template": "LINE_CHART"}
    assert routing.from_choice(_catalog(), trend).breakdown is True


def test_집계_줄의_상태_코드는_발주기관_어휘로_적는다():
    data = _data(
        dimensions=["issue_status"],
        columns=[
            WidgetColumn(key="d0", label="일반 이슈 상태", type="string"),
            WidgetColumn(key="value", label="이슈 건수", type="number"),
        ],
        rows=[
            WidgetRow(values={"d0": "IN_PROGRESS", "value": 2}),
            WidgetRow(values={"d0": "CLOSED", "value": 6}),
        ],
        total=None,
    )
    lines = answer.aggregate_lines(data)
    assert lines[:2] == ["- 일반 이슈 상태 진행중: 2건", "- 일반 이슈 상태 종료: 6건"]
    assert "IN_PROGRESS" not in "\n".join(lines)


def test_이슈_근거는_지금_상태를_머리에_싣는다():
    """이슈 본문에는 상태가 없어 모델이 본문의 계획 문장으로 상태를 말했다(UC-060-S16 실모델)."""
    prompt = answer.user_prompt(
        "외부 연계 규격 협의 이슈 상태", [_chunk("c1", content="규격을 확정한다", status="진행중")],
        None,
    )
    assert "[1] 과업지시서 · 지금 상태 진행중\n규격을 확정한다" in prompt
