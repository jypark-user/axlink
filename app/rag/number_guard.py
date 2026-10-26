"""답변 수치 검문 (QUR.RAG.002, ARC-017).

모델이 쓴 숫자는 문장이 끝날 때까지 들고 있다가, 그 숫자가 집계 값이나 근거 원문의 값과
같고 단위·대상·기준 시점이 맞는지 본 뒤에만 내보낸다. 맞지 않는 문장은 화면에 나가지 않는다.
질문과 앞 답의 숫자는 근거가 아니다. 질문의 낱말은 "무엇에 대한 숫자인가" 를 판정할 때만 쓴다.

집계·그림·일정의 값은 그 값을 부르는 말(라벨)과 짝을 짓는다(점검 NUM-01). "계획 진척률 75%",
"보고 진척률 40%" 를 받고 "계획 진척률은 40%" 라고 쓰면, 숫자는 근거에 있어도 다른 값의 라벨이
문장과 더 잘 맞으므로 막는다. 라벨은 근거 줄에서 그 숫자 바로 앞 구절과 줄 머리말이다.
문장 쪽은 숫자 바로 앞(값이 앞에 오는 문장이면 바로 뒤) 구절을 본다. 같은 묶음 안에서 값을
서로 구분하는 낱말만 센다. 구분하는 말을 하지 않은 문장은 값·단위·대상·시점만 본다.
낱말 대조라 문장 구조를 이해하는 것은 아니다. 근거 원문(청크)의 숫자와 산출 근거 같은 설명
줄에는 짝을 적용하지 않는다.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from app.rag import blocks as blocks_mod

BLOCKED_NOTE = "(근거를 확인할 수 없는 수치가 있어 이 부분은 표시하지 않았습니다.)"

_SEOUL = ZoneInfo("Asia/Seoul")

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


def _spans(text: str) -> list[tuple[int, int, str, str]]:
    """수치마다 (시작, 끝, 값, 단위). 끝은 단위 뒤다."""
    out = []
    for m in _NUMBER.finditer(_mask(text)):
        unit = m.group(2) or ""
        out.append((m.start(1), m.end(), _normalize(m.group(1)), _UNIT_ALIAS.get(unit, unit)))
    return out


def quantities(text: str, start_at: int = 0) -> list[tuple[str, str]]:
    """수치로 보는 숫자와 그 단위. 날짜·버전·번호는 뺀다.

    start_at 앞은 이미 내보낸 같은 문장의 앞부분이다. 제외 규칙(식별자·표식·버전)은 앞부분까지
    붙여서 보고, 수치는 start_at 뒤에서만 센다. 조각이 'SWFR.RAG.' 와 '007' 로 끊겨 와도 같다.
    """
    return [(value, unit) for start, _, value, unit in _spans(text) if start >= start_at]


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
    label: frozenset[str] | None = None  # 값을 부르는 말. 근거 원문·설명 줄의 값은 None


def facts_from_lines(
    lines: Iterable[str], source: str, subject: str = "", as_of: frozenset[DateKey] = frozenset()
) -> list[Fact]:
    """집계·그림의 줄. 대상어는 그 묶음 전체(제목·지표명·라벨·산출 근거)의 낱말이다."""
    lines = list(lines)
    words = keywords(" ".join([subject, *lines]))
    return [
        Fact(value, unit, words, source, as_of, label=label)
        for line in lines
        for value, unit, label in _labelled(line)
    ]


# 값의 뜻을 풀어 쓴 줄. 설명 문장의 낱말을 라벨로 쓰면 다른 값이 막힌다
_EXPLAIN_HEADS = ("산출 근거",)


def _labelled(line: str) -> list[tuple[str, str, frozenset[str] | None]]:
    """줄의 수치마다 (값, 단위, 라벨). 라벨은 줄 머리말 + 앞 숫자 뒤부터 이 숫자 앞까지 +
    이 숫자 뒤 쉼표까지("말단 작업 10건 중 3건이 늦음" 의 3 은 "늦음" 까지)."""
    spans = _spans(line)
    colon = line.find(":")
    head = line[:colon] if spans and 0 <= colon < spans[0][0] else ""
    if head.strip(" -") in _EXPLAIN_HEADS:
        return [(value, unit, None) for _, _, value, unit in spans]
    out = []
    for i, (start, end, value, unit) in enumerate(spans):
        prev = spans[i - 1][1] if i else 0
        nxt = spans[i + 1][0] if i + 1 < len(spans) else len(line)
        tail = line[end:nxt].split(",")[0]
        words = keywords(f"{head} {line[prev:start]} {tail}")
        out.append((value, unit, frozenset(_canon(words))))
    return out


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
    reason: str  # 근거에 없는 값 | 단위 불일치 | 대상 불일치 | 지표 불일치 | 기준 시점 불일치


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
    # 묶음(source)마다 라벨이 있는 값들과, 그 값들을 서로 구분하는 낱말
    _labelled: dict[str, list[Fact]] = field(init=False, repr=False)
    _distinct: dict[str, frozenset[str]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._labelled = {}
        for f in self.facts:
            if f.label is not None:
                self._labelled.setdefault(f.source, []).append(f)
        self._distinct = {
            source: frozenset().union(*(f.label for f in group))
            - frozenset.intersection(*(f.label for f in group))
            for source, group in self._labelled.items()
        }

    def check(self, sentence: str, context: str = "") -> list[Violation]:
        """문장의 수치 중 근거로 설명되지 않는 것. context 는 이미 내보낸 같은 문장의 앞부분이다."""
        whole = context + sentence
        spans = _spans(whole)
        if not any(start >= len(context) for start, *_ in spans):
            return []
        subject = self._subjects_in(whole) or self._subjects_in(self.question)
        cited = {int(n) for n in _FOOTNOTE.findall(whole)}
        when = dates_in(whole)
        clauses = self._clauses(whole, spans)
        bad = []
        for (start, _, value, unit), clause in zip(spans, clauses, strict=True):
            if start < len(context):
                continue
            reason = self._why_not(value, unit, subject, cited, when, clause)
            if reason:
                bad.append(Violation(value, unit, reason))
        return bad

    def _clauses(self, text: str, spans: list[tuple[int, int, str, str]]) -> list[set[str]]:
        """숫자마다 그 숫자를 가리키는 구절의 낱말.

        보통은 앞 숫자 뒤부터 이 숫자 앞까지("계획 진척률은 75%"). 첫 숫자 앞에 구분하는 말이
        없고 마지막 숫자 뒤에 있으면 값이 앞에 오는 문장으로 보고 뒤 구절을 쓴다("75%는 계획").
        """
        vocab = frozenset().union(*self._distinct.values())
        edges = [0, *[end for _, end, *_ in spans]]
        before = [_canon(keywords(text[edges[i]: spans[i][0]])) for i in range(len(spans))]
        nexts = [start for start, *_ in spans[1:]] + [len(text)]
        after = [_canon(keywords(text[spans[i][1]: nexts[i]])) for i in range(len(spans))]

        def names(words: set[str]) -> bool:
            return any(_overlap([w], vocab) for w in words)

        if spans and not names(before[0]) and names(after[-1]):
            return after
        return before

    def _outranked(self, fact: Fact, clause: set[str]) -> bool:
        """구절이 말한 구분 낱말이 같은 묶음의 다른 값(같은 단위) 라벨과 더 많이 맞는가."""
        if fact.label is None:
            return False
        distinct = self._distinct.get(fact.source, frozenset())
        named = [w for w in clause if _overlap([w], distinct)]
        if not named:
            return False

        def score(label: frozenset[str]) -> int:
            return sum(1 for w in named if _overlap([w], label))

        mine = score(fact.label)
        return any(
            score(other.label) > mine
            for other in self._labelled[fact.source]
            if other.value != fact.value
            and (not other.unit or not fact.unit or other.unit == fact.unit)
        )

    def _subjects_in(self, text: str) -> set[str]:
        vocab = _canon(self.subjects)
        return {w for w in _canon(keywords(text)) if _overlap([w], vocab)}

    def _why_not(self, value, unit, subject, cited, when, clause=frozenset()) -> str | None:
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
        same = [f for f in same if not self._outranked(f, clause)]
        if not same:
            return "지표 불일치"
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
