"""수치와 지표의 짝 (QUR.RAG.002, 점검 NUM-01). 모델 없이 도는 단위 시험이다.

근거에 있는 숫자라도 다른 줄(다른 지표·다른 항목)의 값이면 막는다. 같은 묶음의 줄들을 서로
구분하는 낱말(계획·보고, 열림·닫힘, 담당자 이름 등)을 문장이 숫자 가까이에서 말했을 때만 본다.
"""

import pytest

from app.rag import number_guard as g


def _checker() -> g.Checker:
    facts = g.facts_from_lines(
        ["- 계획 진척률: 75%", "- 보고 진척률: 40%", "- 목표: 80%"],
        "집계",
        subject="계획 대비 진척률",
    )
    facts += g.facts_from_lines(
        ["- 담당자 김민수: 3건", "- 담당자 이서연: 5건", "- 전체(항목 합): 8건"],
        "그림 1",
        subject="담당자별 열린 이슈",
    )
    subjects = g.DOMAIN_TERMS | g.keywords("계획 대비 진척률 담당자별 열린 이슈")
    return g.Checker(facts, subjects=subjects)


def _blocked(sentence: str) -> bool:
    gate = g.SentenceGate(_checker())
    out = gate.feed(sentence) + gate.finish()
    return gate.blocked > 0 and g.BLOCKED_NOTE in out


@pytest.mark.parametrize("sentence", [
    "계획 진척률은 40%이고 보고 진척률은 75%입니다.",   # 점검 재현 문장
    "보고 진척률은 75%입니다.",
    "75%는 보고 진척률입니다.",                          # 값이 앞, 지표가 뒤
    "목표는 75%입니다.",
    "김민수 담당은 5건입니다.",
    "이서연 담당자에게 3건이 열려 있습니다.",
])
def test_다른_줄의_값을_붙이면_막는다(sentence):
    assert _blocked(sentence)


@pytest.mark.parametrize("sentence", [
    "계획 진척률은 75%이고 보고 진척률은 40%입니다.",
    "보고 진척률은 40%로 계획 75%보다 낮습니다.",
    "40%가 보고 진척률이고 75%가 계획 진척률입니다.",
    "진척률은 계획 75%, 보고 40%입니다.",
    "목표 80%에 못 미칩니다.",
    "진척률은 40%입니다.",                                # 어느 줄인지 말하지 않으면 값만 본다
    "김민수 3건, 이서연 5건으로 모두 8건입니다.",
    "열린 이슈는 전체 8건입니다.",
])
def test_같은_줄의_값이면_통과한다(sentence):
    assert not _blocked(sentence)


def test_없는_값은_여전히_막는다():
    assert _blocked("보고 진척률은 99%입니다.")


# ------------------------------------------------- 한 줄에 지표가 여럿인 일정 근거


def _schedule() -> g.Checker:
    line = ("- AX Link (기준일 2026-10-20): 계획 진척률(추정) 75%, 보고 진척률(WBS 실적) 40%, "
            "차이 -35%p (뒤처짐), 말단 작업 10건 중 3건이 계획선보다 늦음")
    return g.Checker(g.facts_from_lines([line], "일정", subject="계획 대비 진척률"))


def test_일정_근거에서_자리를_바꾼_값을_막는다():
    assert _schedule().check("계획 진척률은 40%이고 보고 진척률은 75%입니다.")


def test_활용형이_다른_말은_같은_말로_보지_못한다():
    # 한계: "늦은" 과 근거의 "늦음" 을 같은 말로 보지 않아 10건(말단 작업 전체)을 늦은 작업
    # 수로 써도 통과한다. 형태소 분석 없이 낱말만 대조하는 방식의 한계다
    assert _schedule().check("늦은 작업은 10건입니다.") == []


@pytest.mark.parametrize("sentence", [
    "계획 진척률은 75%, 보고 진척률은 40%로 35%p 뒤처져 있습니다.",
    "말단 작업 10건 중 3건이 계획선보다 늦습니다.",
    "계획선보다 늦은 작업은 3건입니다.",
])
def test_일정_근거의_제자리_값은_통과한다(sentence):
    assert _schedule().check(sentence) == []
