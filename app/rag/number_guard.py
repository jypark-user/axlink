"""답변 수치 검문 (QUR.RAG.002, ARC-017).

모델이 쓴 숫자는 문장이 끝날 때까지 들고 있다가, 그 숫자가 집계 값이나 근거 원문의 값과
같고 단위·대상·기준 시점이 맞는지 본 뒤에만 내보낸다. 맞지 않는 문장은 화면에 나가지 않는다.
질문과 앞 답의 숫자는 근거가 아니다. 질문의 낱말은 "무엇에 대한 숫자인가" 를 판정할 때만 쓴다.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from app.common import clock
from app.rag import blocks as blocks_mod

BLOCKED_NOTE = "(근거를 확인할 수 없는 수치가 있어 이 부분은 표시하지 않았습니다.)"

_SEOUL = clock.PROJECT_TZ

# ---------------------------------------------------------------- 수치가 아닌 숫자

_FOOTNOTE = re.compile(r"\[(\d{1,2})\]")
_DATE_FULL = re.compile(r"(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})")
_DATE_KO = re.compile(r"(?:(\d{4})\s*년)?\s*(?:(\d{1,2})\s*월)?\s*(?:(\d{1,2})\s*일)?")
_DATE_MD = re.compile(r"(?<![\d.\-/])(\d{1,2})[-/](\d{1,2})(?![\d./\-])")
_DATE_MD_DOT = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?=\s*(?:까지|부터|일|~|에\s|에$))")

_NON_QUANTITY = [
    blocks_mod.MARKER,
    _FOOTNOTE,
    _DATE_FULL,
    re.compile(r"\d{4}\s*년(?:\s*\d{1,2}\s*월)?(?:\s*\d{1,2}\s*일)?"),
    re.compile(r"\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?"),
    re.compile(r"\d{1,2}\s*일"),  # 날짜와 일수. 일수는 검문하지 않는다(관대)
    _DATE_MD,
    _DATE_MD_DOT,
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),  # 시각
    re.compile(r"[vV]\.?\s?\d+(?:\.\d+)*"),  # v0.4
    re.compile(r"(?:버전|ver\.?)\s*\d+(?:\.\d+)*", re.IGNORECASE),
    re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.\-_:][A-Za-z0-9]+)+"),  # SWFR.RAG.007, GH-23, bge-m3
    re.compile(r"[A-Za-z]+\d[A-Za-z0-9]*"),  # V44, M4, S1
    re.compile(r"#\d+"),
    re.compile(r"WBS\s*\d+(?:\.\d+)*"),
    re.compile(r"\d+(?:\.\d+){2,}"),  # 3.2.1
    re.compile(r"제\s*\d+"),  # 제3조
    re.compile(r"\d+(?:\.\d+)*\s*(?:절|조|항|장|번째)"),
    re.compile(r"(?m)^\s*\(?\d{1,2}[).](?!\d)"),  # 줄머리 목록 번호 1) 2. (3)
    re.compile(r"(?:(?<=\s)|(?<=→))\d{1,2}(?:\)|\.(?=\s)|단계)"),  # 문장 속 단계 번호
    re.compile(r"[①-⑳]"),  # ①~⑳
]

_NUMBER = re.compile(
    r"(?<![\d.])(\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(%p|%|퍼센트포인트|퍼센트|포인트|개월|개|건|명|회|만원|억원|원|배|점|시간|분|초|주|쪽|"
    r"페이지|줄|행|청크|자|TB|GB|MB|KB)?"
)
_UNIT_ALIAS = {"퍼센트": "%", "퍼센트포인트": "%p", "포인트": "%p", "페이지": "쪽"}

# ---------------------------------------------------------------- 낱말

_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}")
_JOSA = (
    "으로써", "으로는", "에서는", "에서", "에게", "까지", "부터", "이라는", "이라", "라는", "이며",
    "이고", "에는", "에도", "으로", "와는", "과는", "은", "는", "이", "가", "을", "를", "의", "에",
    "도", "와", "과", "로", "만", "께",
)
_STOP = {
    "있다", "있습", "있습니다", "없다", "없습니다", "입니다", "합니다", "됩니다", "이다", "하는",
    "되는", "대한", "관련", "그리고", "하지만", "경우", "현재", "기준", "정도", "모두", "각각",
    "이번", "지금", "전체", "나머지", "답변", "근거", "그림", "값이", "값은", "값을", "산출",
}


def _stem(word: str) -> str:
    w = word.lower()
    for josa in _JOSA:
        if w.endswith(josa) and len(w) - len(josa) >= 2:
            return w[: -len(josa)]
    return w


def keywords(text: str) -> frozenset[str]:
    """대상어 후보. 두 글자 이상 낱말에서 조사를 떼고 흔한 말을 뺀다."""
    out = set()
    for m in _WORD.finditer(text):
        w = _stem(m.group(0))
        if w not in _STOP and len(w) >= 2:
            out.add(w)
    return frozenset(out)


# ---------------------------------------------------------------- 날짜

DateKey = tuple[int | None, int | None, int | None]  # (연, 월, 일). 모르는 칸은 None


def dates_in(text: str) -> set[DateKey]:
    found: set[DateKey] = set()
    for m in _DATE_FULL.finditer(text):
        found.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    rest = _DATE_FULL.sub(" ", text)
    for m in _DATE_KO.finditer(rest):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if not (y or mo or d):
            continue
        if mo is None and d is None:
            found.add((int(y), None, None))
            continue
        found.add((int(y) if y else None, int(mo) if mo else None, int(d) if d else None))
    for m in _DATE_MD.finditer(rest):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            found.add((None, mo, d))
    return found


def _compatible(a: DateKey, b: DateKey) -> bool:
    return all(x is None or y is None or x == y for x, y in zip(a, b, strict=True))


def as_of_date(generated_at: str | None) -> frozenset[DateKey]:
    """집계 데이터를 뽑은 시각(UTC ISO)을 서울 날짜로."""
    if not generated_at:
        return frozenset()
    try:
        at = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).astimezone(_SEOUL)
    except ValueError:
        return frozenset()
    return frozenset({(at.year, at.month, at.day)})


# ---------------------------------------------------------------- 숫자 꺼내기


def _mask(text: str) -> str:
    for pattern in _NON_QUANTITY:
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


def _normalize(token: str) -> str:
    plain = token.replace(",", "")
    try:
        value = float(plain)
    except ValueError:
        return plain
    return str(int(value)) if value.is_integer() else f"{value:g}"


def quantities(text: str, start_at: int = 0) -> list[tuple[str, str]]:
    """수치로 보는 숫자와 그 단위. 날짜·버전·번호는 뺀다.

    start_at 앞은 이미 내보낸 같은 문장의 앞부분이다. 제외 규칙(식별자·표식·버전)은 앞부분까지
    붙여서 보고, 수치는 start_at 뒤에서만 센다. 조각이 'SWFR.RAG.' 와 '007' 로 끊겨 와도 같다.
    """
    out = []
    for m in _NUMBER.finditer(_mask(text)):
        if m.start(1) < start_at:
            continue
        unit = m.group(2) or ""
        out.append((_normalize(m.group(1)), _UNIT_ALIAS.get(unit, unit)))
    return out


def has_quantity(text: str) -> bool:
    return bool(quantities(text))


# ---------------------------------------------------------------- 근거 값


@dataclass(frozen=True)
class Fact:
    value: str
    unit: str
    keywords: frozenset[str]
    source: str  # "집계" | "그림 1" | "근거 2" | "목록 범위"
    as_of: frozenset[DateKey] = frozenset()
    chunk_no: int | None = None


def facts_from_lines(
    lines: Iterable[str], source: str, subject: str = "", as_of: frozenset[DateKey] = frozenset()
) -> list[Fact]:
    """집계·그림의 줄. 대상어는 그 묶음 전체(제목·지표명·라벨·산출 근거)의 낱말이다."""
    lines = list(lines)
    words = keywords(" ".join([subject, *lines]))
    return [
        Fact(value, unit, words, source, as_of)
        for line in lines
        for value, unit in quantities(line)
    ]


def facts_from_chunk(no: int, content: str) -> list[Fact]:
    """근거 원문. 대상어와 기준 시점은 그 숫자가 든 문장에서만 가져온다."""
    facts = []
    for sentence in re.split(r"(?<=[.?!。])\s+|\n+", content):
        found = quantities(sentence)
        if not found:
            continue
        words = keywords(sentence)
        when = frozenset(dates_in(sentence))
        facts.extend(Fact(v, u, words, f"근거 {no}", when, no) for v, u in found)
    return facts


# ---------------------------------------------------------------- 검사


@dataclass(frozen=True)
class Violation:
    value: str
    unit: str
    reason: str  # 근거에 없는 값 | 단위 불일치 | 대상 불일치 | 기준 시점 불일치


# 수치가 "무엇의" 값인지 말하는 낱말. 문장의 대상어는 이 사전과 집계·그림 제목에서만 뽑는다.
# 동사·형용사("열려", "늘었다")까지 대상어로 보면 멀쩡한 문장이 막힌다.
DOMAIN_TERMS = frozenset({
    "이슈", "결함", "버그", "리스크", "위험", "요구사항", "산출물", "문서", "진척률", "진척",
    "이행률", "처리율", "해결률", "승인율", "제출률", "일정", "마일스톤", "작업", "커밋", "시험",
    "테스트", "사업", "사업비", "예산", "계약", "인원", "담당자", "지연", "승인", "제출", "미제출",
    "스냅샷", "청크", "연결", "동기화", "확인요청", "조치", "용역사", "발주기관", "회의",
})
# 같은 지표를 다른 말로 부르는 경우
_SYNONYMS = {
    "진행률": "진척률",
    "공정률": "진척률",
    "공정": "진척",
    "버그": "결함",
    "위험": "리스크",
}


def _canon(words: Iterable[str]) -> set[str]:
    return {_SYNONYMS.get(w, w) for w in words}


def _overlap(a: Iterable[str], b: Iterable[str]) -> bool:
    """낱말이 같거나 한쪽이 다른 쪽을 품으면 겹친 것으로 본다(사업비 · 총사업비)."""
    b = list(b)
    return any(x == y or x in y or y in x for x in a for y in b)


@dataclass
class Checker:
    facts: list[Fact]
    question: str = ""
    subjects: frozenset[str] = DOMAIN_TERMS  # 집계·그림 제목의 낱말을 더해 넘긴다

    def check(self, sentence: str, context: str = "") -> list[Violation]:
        """문장의 수치 중 근거로 설명되지 않는 것. context 는 이미 내보낸 같은 문장의 앞부분이다."""
        whole = context + sentence
        claims = quantities(whole, start_at=len(context))
        if not claims:
            return []
        subject = self._subjects_in(whole) or self._subjects_in(self.question)
        cited = {int(n) for n in _FOOTNOTE.findall(whole)}
        when = dates_in(whole)
        bad = []
        for value, unit in claims:
            reason = self._why_not(value, unit, subject, cited, when)
            if reason:
                bad.append(Violation(value, unit, reason))
        return bad

    def _subjects_in(self, text: str) -> set[str]:
        vocab = _canon(self.subjects)
        return {w for w in _canon(keywords(text)) if _overlap([w], vocab)}

    def _why_not(self, value, unit, subject, cited, when) -> str | None:
        same = [f for f in self.facts if f.value == value]
        if not same:
            return "근거에 없는 값"
        same = [f for f in same if not unit or not f.unit or f.unit == unit]
        if not same:
            return "단위 불일치"
        if subject:  # 문장(또는 질문)이 대상을 말했으면 그 대상의 값이어야 한다
            same = [
                f for f in same
                if _overlap(subject, _canon(f.keywords))
                or (f.chunk_no is not None and f.chunk_no in cited)
            ]
            if not same:
                return "대상 불일치"
        if when:
            same = [
                f for f in same
                if not f.as_of or any(_compatible(a, b) for a in when for b in f.as_of)
            ]
            if not same:
                return "기준 시점 불일치"
        return None


# ---------------------------------------------------------------- 스트림 관문

def _open_bracket(text: str) -> bool:
    return text.rfind("[") > text.rfind("]")


# 문장 끝: 마침표·물음표·느낌표 뒤 공백, 또는 줄바꿈. "29.7%" 의 점은 끝이 아니다
_BOUNDARY = re.compile(r"[.?!。](?=\s)|\n")


@dataclass
class SentenceGate:
    """조각을 받아 검사를 통과한 글만 돌려준다.

    숫자가 없는 글은 받는 대로 내보낸다. 숫자가 보이면 그 문장이 끝날 때까지 들고 있다가
    검사한 뒤 내보내거나 안내 한 줄로 바꾼다. 검사 전 숫자가 화면에 나가는 일은 없다.
    """

    checker: Checker
    violations: list[Violation] = field(default_factory=list)
    blocked: int = 0
    _held: str = ""
    _sent_prefix: str = ""  # 이미 내보낸 같은 문장의 앞부분(숫자 없음). 대상어 판정에 쓴다

    def feed(self, piece: str) -> str:
        self._held += piece
        out = []
        while True:
            m = _BOUNDARY.search(self._held)
            if not m:
                break
            sentence, self._held = self._held[: m.end()], self._held[m.end() :]
            out.append(self._release(sentence))
            self._sent_prefix = ""
        # 아직 끝나지 않은 문장에 숫자가 없으면 지금 내보내도 된다. 다만 닫히지 않은 '[' 가
        # 있으면 각주·그림 표식이 끊겨 오는 중일 수 있어 들고 있는다
        if self._held and not re.search(r"\d", self._held) and not _open_bracket(self._held):
            out.append(self._held)
            self._sent_prefix += self._held
            self._held = ""
        return "".join(out)

    def finish(self) -> str:
        rest, self._held = self._held, ""
        out = self._release(rest) if rest else ""
        self._sent_prefix = ""
        return out

    def _release(self, sentence: str) -> str:
        bad = self.checker.check(sentence, self._sent_prefix)
        if not bad:
            return sentence
        self.violations.extend(bad)
        self.blocked += 1
        lead = sentence[: len(sentence) - len(sentence.lstrip())]
        tail = sentence[len(sentence.rstrip()) :]
        return lead + BLOCKED_NOTE + (tail or " ")
