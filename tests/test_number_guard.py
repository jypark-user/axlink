"""수치 검문 (QUR.RAG.002, ARC-017). 모델 없이 도는 단위 시험이다."""

import pytest

from app.rag import number_guard as g

AS_OF = g.as_of_date("2026-10-02T03:00:00Z")  # 서울 10-02 12:00


def _checker(question: str = "") -> g.Checker:
    facts = g.facts_from_lines(
        ["- 이슈 상태 OPEN: 7건", "- 이슈 상태 CLOSED: 12건", "- 전체: 19건"],
        "집계",
        subject="이슈 건수",
        as_of=AS_OF,
    )
    facts += g.facts_from_lines(
        ["- 대표 진척률: 29.7%", "- 산출 근거: 검증완료 요구사항 수를 전체로 나눈다 (0건 / 41건)"],
        "그림 1",
        subject="진척률 요구사항 이행률",
        as_of=AS_OF,
    )
    facts += g.facts_from_chunk(1, "총사업비는 18,000,000원이다. 2026년 11월 30일까지 수행한다.")
    subjects = g.DOMAIN_TERMS | g.keywords("이슈 건수 진척률 요구사항 이행률")
    return g.Checker(facts, question=question, subjects=subjects)


def _reasons(checker: g.Checker, sentence: str) -> list[str]:
    return [f"{v.value}{v.unit}:{v.reason}" for v in checker.check(sentence)]


# ---------------------------------------------------------------- 정상 응답


@pytest.mark.parametrize(
    "sentence",
    [
        "열린 이슈 7건, 닫힌 이슈 12건, 모두 19건입니다.",
        "진척률은 29.7%입니다.",
        "검증된 요구사항은 41건 중 0건입니다.",
        "총사업비는 18,000,000원입니다[1].",
        "사업비는 18,000,000원입니다.",
    ],
)
def test_집계값과_출처있는_문서값은_통과한다(sentence):
    assert _reasons(_checker(), sentence) == []


def test_대상어가_없는_짧은_답은_질문의_대상어로_본다():
    assert _reasons(_checker("진척률이 얼마나 돼?"), "29.7%입니다.") == []
    assert _reasons(_checker("이슈는 몇 건이야?"), "그중 7건이 열려 있습니다.") == []


def test_같은_지표를_다른_말로_불러도_통과한다():
    assert _reasons(_checker(), "진행률은 29.7%입니다.") == []


# ---------------------------------------------------------------- 차단


def test_근거에_없는_값은_막는다():
    assert _reasons(_checker(), "이슈는 모두 977건입니다.") == ["977건:근거에 없는 값"]


def test_반올림한_값도_지어낸_값이다():
    assert _reasons(_checker(), "진척률은 약 30%입니다.") == ["30%:근거에 없는 값"]


def test_숫자가_같아도_단위가_다르면_막는다():
    assert _reasons(_checker(), "진척률은 7%입니다.") == ["7%:단위 불일치"]


def test_숫자가_같아도_대상이_다르면_막는다():
    # 7건은 이슈의 값이다. 결함 7건이라고 말하면 안 된다
    assert _reasons(_checker("결함은 몇 건이야?"), "결함은 7건입니다.") == ["7건:대상 불일치"]
    assert _reasons(_checker(), "이슈 처리에 18,000,000원이 들었습니다.") == [
        "18000000원:대상 불일치"
    ]


def test_기준_시점이_다르면_막는다():
    assert _reasons(_checker(), "2026-09-01 기준 진척률은 29.7%입니다.") == [
        "29.7%:기준 시점 불일치"
    ]
    # 같은 날이면 통과한다
    assert _reasons(_checker(), "10월 2일 기준 진척률은 29.7%입니다.") == []


def _trend_checker() -> g.Checker:
    """기간 축 집계. 집계한 날은 10-07 이고 행마다 날짜가 따로 있다(GH-123 재현 값)."""
    facts = g.facts_from_lines(
        ["- 일 2026-09-18: 29.7%", "- 일 2026-10-06: 73.4%", "- 산출 근거: 일별 스냅샷의 진척률"],
        "집계",
        subject="진척률 추세",
        as_of=g.as_of_date("2026-10-07T03:00:00Z"),
    )
    facts += g.facts_from_lines(
        ["- 월 2026-09: 41.0%", "- 월 2026-10: 73.4%"], "그림 1", subject="월별 진척률",
        as_of=g.as_of_date("2026-10-07T03:00:00Z"),
    )
    return g.Checker(facts, subjects=g.DOMAIN_TERMS | g.keywords("진척률 추세 월별"))


def test_기간_축_값은_그_행의_날짜가_기준_시점이다():
    ck = _trend_checker()
    # GH-123: 날짜를 맞게 쓴 추세 문장이 집계한 날(10-07)과 다르다고 막혔다
    assert _reasons(ck, "9월 18일 진척률은 29.7%였고 10월 6일에는 73.4%로 올랐습니다.") == []
    assert _reasons(ck, "2026년 9월 진척률은 41.0%입니다.") == []
    # 다른 행의 날짜에 붙이면 여전히 막는다
    assert _reasons(ck, "10월 6일 진척률은 29.7%입니다.") == ["29.7%:기준 시점 불일치"]
    assert _reasons(ck, "2026년 10월 진척률은 41.0%입니다.") == ["41%:기준 시점 불일치"]
    # 근거에 없는 값은 그대로 막는다(GH-123 의 7건)
    assert _reasons(ck, "이 기간 7건이 늘었습니다.") == ["7건:근거에 없는 값"]


def test_머리말에_날짜가_없는_줄은_집계한_날을_쓴다():
    assert g._row_dates("- 대표 진척률: 29.7%") == frozenset()
    assert g._row_dates("- 산출 근거: 2026-09-18 부터 센다") == frozenset()
    assert g._row_dates("- 일 2026-09-18: 29.7%") == {(2026, 9, 18)}
    assert g._row_dates("- 월 2026-09: 41.0%") == {(2026, 9, None)}


def test_질문의_숫자는_근거가_아니다():
    ck = _checker("진척률이 30% 넘었어?")
    assert _reasons(ck, "네, 진척률은 30%를 넘었습니다.") == ["30%:근거에 없는 값"]


def test_앞_답의_숫자도_근거가_아니다():
    # 앞 답은 Fact 에 넣지 않는다. 같은 문장을 다시 써도 근거가 없으면 막힌다
    ck = _checker("아까 말한 결함 수 다시 알려줘")
    assert _reasons(ck, "결함은 23건입니다.") == ["23건:근거에 없는 값"]


# ---------------------------------------------------------------- 오탐 방지


@pytest.mark.parametrize(
    "sentence",
    [
        "M4 는 2026-10-23 까지다.",
        "10월 23일까지 마치고 10-23 에 보고한다.",
        "10.23까지 올린다.",
        "13:40 에 동기화했다.",
        "v0.4 초안과 버전 2 문서를 본다.",
        "SWFR.RAG.007 과 QUR.RAG.002, GH-23, ARC-010, V44 를 본다.",
        "qwen3:8b 와 bge-m3 를 쓴다.",
        "WBS 3.3 과 3.2절, 제3조, 5.2.1 항목을 본다.",
        "PR #108 을 병합했다.",
        "1) 시험을 만든다 → 2) 결과를 올린다. 3단계면 끝.",
        "근거는 [1] 과 [2] 이고 [그림 1] 에 있다.",
        "① 수집 ② 표준화 ③ 집계",
    ],
)
def test_날짜_버전_번호는_수치로_보지_않는다(sentence):
    assert g.quantities(sentence) == []
    assert _reasons(_checker(), sentence) == []


def test_목록_번호_뒤의_건수는_여전히_본다():
    assert g.quantities("1) 결과서 3건을 올린다") == [("3", "건")]
    assert g.quantities("이슈 1,200건, 진척 42.50%") == [("1200", "건"), ("42.5", "%")]


# ---------------------------------------------------------------- 스트리밍


def test_검사_전에는_숫자가_화면에_나가지_않는다():
    gate = g.SentenceGate(_checker("이슈 몇 건?"))
    shown = []
    pieces = [
        "현재 상황을 ",
        "말씀드리면 열린 이슈는 ",
        "9",
        "77건입니다. ",
        "닫힌 이슈는 12건입니다.",
    ]
    for piece in pieces:
        shown.append(gate.feed(piece))
    shown.append(gate.finish())
    # 숫자가 없는 앞부분은 바로 나간다
    assert shown[0] == "현재 상황을 " and shown[1] == "말씀드리면 열린 이슈는 "
    # '9' 가 들어온 순간에는 아무것도 안 나간다. 문장이 끝날 때까지 들고 있는다
    assert shown[2] == ""
    # 지어낸 977건 문장은 안내 한 줄로 바뀐다. 977 은 어떤 조각에도 없다
    assert shown[3].startswith(g.BLOCKED_NOTE)
    assert all("977" not in s and "9" not in s for s in shown)
    # 맞는 문장은 끝에 나간다
    assert "".join(shown).endswith("닫힌 이슈는 12건입니다.")
    assert gate.blocked == 1 and gate.violations[0].reason == "근거에 없는 값"


def test_숫자가_조각_경계에_걸려도_합쳐서_본다():
    gate = g.SentenceGate(_checker())
    out = gate.feed("진척률은 29.") + gate.feed("7%입니다.") + gate.finish()
    assert out == "진척률은 29.7%입니다."
    assert gate.blocked == 0


def test_통과한_문장은_원문_그대로_나간다():
    gate = g.SentenceGate(_checker())
    text = "열린 이슈 7건입니다.\n총사업비는 18,000,000원입니다[1]. 끝."
    out = "".join(gate.feed(ch) for ch in text) + gate.finish()
    assert out == text


SPLIT_SAFE = [
    "등록된 리스크입니다. \n[그림 1]",
    "근거대로 답합니다[1]. 끝.",
    "SWFR.RAG.007 은 v0.4 에서 WBS 3.3 으로 M4 에 잡혀 있다.",
    "열린 이슈는 7건입니다[1].",
]


@pytest.mark.parametrize("text", SPLIT_SAFE)
def test_표식과_식별자가_조각_경계에서_끊겨도_오탐하지_않는다(text):
    """10-02 실측: '[그림 ' 과 '1]' 로 끊겨 와서 '1' 이 수치로 막혔다. 어디서 끊겨도 같아야 한다."""
    # 한 글자씩(가장 잘게)
    gate = g.SentenceGate(_checker("이슈 몇 건?"))
    out = "".join(gate.feed(ch) for ch in text) + gate.finish()
    assert out == text and gate.blocked == 0
    # 두 조각으로 나눌 수 있는 모든 자리
    for cut in range(1, len(text)):
        gate = g.SentenceGate(_checker("이슈 몇 건?"))
        out = gate.feed(text[:cut]) + gate.feed(text[cut:]) + gate.finish()
        assert out == text and gate.blocked == 0, cut


def test_지어낸_숫자는_한_글자씩_와도_한_번도_나가지_않는다():
    gate = g.SentenceGate(_checker("이슈 몇 건?"))
    shown = [gate.feed(ch) for ch in "열린 이슈는 977건입니다. "] + [gate.finish()]
    assert all("9" not in s and "7" not in s for s in shown)
    assert gate.blocked == 1


# ------------------------------------------------ 폐쇄망 모델 실측(2026-11-13, DEF-V058~V060)


def test_문장이_행의_종료일을_말해도_기준_시점_불일치로_막지_않는다():
    """UC-060-S07: 지연 작업 줄의 종료 예정일은 그 행의 속성이다. 기준일(T0)의 실적 40% 를
    말하면서 종료 예정일을 같이 적어도 통과한다(DEF-V058)."""
    t0 = frozenset({(2026, 9, 15)})
    facts = g.facts_from_lines(
        [
            "- 기준일 2026-09-15: 말단 작업 10건 중 지연 작업 1건",
            "- 지연 작업 3.2 설계 (시민포털 고도화): 종료 예정 2026-07-31, 실적 40%",
        ],
        "집계",
        subject="지연 작업",
        as_of=t0,
    )
    checker = g.Checker(facts, question="이번 달 지연된 작업과 사유")
    assert _reasons(checker, "3.2 설계는 종료 예정일 2026-07-31 이 지났고 실적은 40% 입니다.") == []
    # 그 행에 없는 날짜를 기준으로 말하면 여전히 막는다
    assert _reasons(checker, "2026-10-31 기준 실적은 40% 입니다.") == ["40%:기준 시점 불일치"]


def test_한_문장의_두_대상은_숫자마다_자기_대상의_근거가_있어야_한다():
    """UC-060-S03 실측: 「산출물은 22종이고, 일반 이슈는 0건」. 0 은 산출물을 말한 WBS 원문에만
    있었다. 문장 전체의 대상으로 보면 통과했다(DEF-V059)."""
    facts = g.facts_from_chunk(1, "납품 산출물은 22종이다.")
    facts += g.facts_from_chunk(2, "시트: WBS | 5 | WBS ID 3.3 | 산출물 프로그램 목록 | 가중치 0")
    checker = g.Checker(facts, question="납품 산출물은 몇 종이고 일반 이슈는 몇 건이야")
    said = "납품 산출물은 22종이고, 일반 이슈는 0건입니다. [1]"
    assert _reasons(checker, said) == ["0건:대상 불일치"]
    assert _reasons(checker, "납품 산출물은 22종입니다. [1]") == []


def test_결함_포함_값을_일반_이슈라고_부르면_막는다():
    """UC-060-S09 실측: 판정이 전체 이슈(결함 포함)를 골랐는데 답이 「일반 이슈는 11건」.
    견줄 값이 하나뿐이라 라벨 짝짓기로 못 막았다(DEF-V060, DEC-02)."""
    facts = g.facts_from_lines(
        ["- 전체 이슈 건수(결함 포함), 사업 시민포털 고도화: 11건"],
        "집계",
        subject="전체 이슈 건수(결함 포함)",
    )
    checker = g.Checker(facts, question="일반 이슈는 몇 건이야")
    assert _reasons(checker, "일반 이슈는 11건이다.") == ["11건:지표 불일치"]
    assert _reasons(checker, "결함을 포함한 전체 이슈는 11건이다.") == []
    general = g.Checker(
        g.facts_from_lines(
            ["- 일반 이슈 건수(결함 제외) 전체: 9건"], "집계", subject="일반 이슈 건수(결함 제외)"
        ),
        question="일반 이슈는 몇 건이야",
    )
    assert _reasons(general, "일반 이슈는 9건이다.") == []
