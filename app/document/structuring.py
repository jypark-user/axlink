"""문서 정형화 규칙. DB 도 모델도 모른다. 추출한 본문을 받아 초안 재료를 낸다.

여기서 나오는 것은 전부 규칙(정규식·표 구조)의 결과다. 요구사항 코드·제목·본문·중요도는
문서에 적힌 글자를 그대로 옮긴 것이고, 산출물 유형은 키워드 점수로 고른 것이다.
LLM 은 규칙이 못 정한 유형과 제목만 고르며(draft_service), 여기에는 발을 들이지 않는다.
근거는 docs/20-design/ARC-009-문서-정형화-초안.md.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from app.standard.work_product_type import DISPLAY_NAMES

# 요구사항 코드. 작업 규약 2절의 SWFR.CON.004 꼴이 기본이고 REQ-001 · FR-01 같은
# 다른 사업의 표기도 받는다. 영역 구분이 없는 두 토막까지가 한계다.
CODE_PATTERN = r"[A-Z]{2,6}(?:[.\-][A-Z]{2,6})?[.\-]\d{2,4}"
_CODE_FULL = re.compile(rf"^{CODE_PATTERN}$")
_CODE_LINE = re.compile(rf"^\[?({CODE_PATTERN})\]?\s*[:：.\-)]?\s+(\S.*)$")

_TABLE_SEPARATOR = re.compile(r"^:?-{2,}:?$")
_MARKDOWN_NOISE = re.compile(r"\*\*|__|`|<br\s*/?>", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_COMMENT = re.compile(r"^<!--.*?-->$")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_VERSION_RE = re.compile(
    r"(?:\bv|\bver\.?|\bversion|버전|판)\s*[:：]?\s*(\d+(?:\.\d+){1,2})", re.IGNORECASE
)
_DATE_RE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?")

_CODE_HEADER = re.compile(r"ID|코드|번호|식별", re.IGNORECASE)
_TEXT_HEADER = re.compile(r"요구사항|명칭|명$|제목|이름|내용|설명|기능|상세")
_BODY_HEADER = re.compile(r"설명|내용|상세")
_PRIORITY_HEADER = re.compile(r"중요도|우선순위|필수|priority", re.IGNORECASE)

# 중요도 표기 → MoSCoW. 문서마다 말이 달라서 대표 표기만 받고 나머지는 SHOULD 다.
_PRIORITY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MUST", ("필수", "상", "높음", "high", "must", "m")),
    ("SHOULD", ("권장", "중", "보통", "중요", "medium", "should", "s")),
    ("COULD", ("선택", "하", "낮음", "low", "could", "c")),
    ("WONT", ("제외", "미채택", "보류", "wont", "won't", "w")),
)

MAX_TITLE_CHARS = 100
MAX_BODY_CHARS = 2000
MAX_DOC_TITLE_CHARS = 200
_HEAD_CHARS = 4000  # 유형·제목·버전은 문서 머리에서 찾는다. 표지와 개정 이력이 거기 있다.


@dataclass
class DraftRequirement:
    index: int
    code: str | None
    title: str
    body: str
    priority: str = "SHOULD"

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "code": self.code,
            "title": self.title,
            "body": self.body,
            "priority": self.priority,
        }


@dataclass
class TypeGuess:
    """키워드 점수 결과. decided 가 False 면 규칙만으로는 못 정한 것이다."""

    product_type: str | None
    confidence: float
    decided: bool
    scores: dict[str, int] = field(default_factory=dict)


# 유형별 단서. 문서 머리와 파일명에서 찾는다. 파일명은 사람이 붙인 이름이라 가중치가 높다.
_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "STATEMENT_OF_WORK": ("과업지시서", "과업 지시서", "제안요청서", "과업내용", "과업 내용"),
    "PROJECT_PLAN": ("사업수행계획서", "수행계획서", "사업수행계획", "WBS", "작업분류",
                     "추진일정", "추진 일정"),
    "PROGRESS_STATUS_RECORD": ("진척보고", "진척 보고", "주간보고", "월간보고", "진행현황",
                               "진행 현황", "진척률"),
    "MEETING_RECORD": ("회의록", "회의 일시", "참석자", "협의 내용", "회의 결과"),
    "CHANGE_REQUEST": ("변경요청서", "변경 요청서", "변경요청", "변경 요청", "변경 사유"),
    "CORRECTION_REGISTER": ("시정조치", "시정 조치", "조치 대장"),
    "ACCEPTANCE_RECORD": ("검수확인서", "검수 확인서", "검수확인", "검수 결과"),
    "PROJECT_REPOSITORY": ("사업 저장소", "프로젝트 저장소", "저장소 구성"),
    "REPOSITORY_BACKUP": ("저장소 백업", "백업본", "백업 이력"),
    "REQUIREMENTS_SPEC": ("요구사항정의서", "요구사항 정의서", "요구사항명세서",
                          "요구사항 명세서", "소프트웨어 요구사항"),
    "TRACEABILITY_RECORD": ("요구사항추적표", "요구사항 추적표", "추적표", "추적매트릭스",
                            "추적 매트릭스"),
    "SOFTWARE_DESIGN": ("설계서", "설계 문서", "아키텍처", "화면설계", "화면 설계", "DB 설계",
                        "인터페이스 설계"),
    "TEST_CASES_PROCEDURES": ("시험계획서", "시험 계획서", "테스트계획", "테스트 계획",
                              "테스트케이스", "시험 절차", "시험 케이스"),
    "SOFTWARE_COMPONENT": ("프로그램 구성요소", "소스코드 목록", "컴포넌트 목록",
                           "구성요소 목록"),
    "SOFTWARE": ("통합 소프트웨어", "릴리스 노트", "배포 패키지", "설치 파일"),
    "TEST_REPORT": ("시험결과서", "시험 결과서", "테스트 결과", "시험 결과"),
    "PRODUCT_OPERATION_GUIDE": ("운영지침서", "운영 지침서", "운영 가이드", "운영 매뉴얼"),
    "SOFTWARE_USER_DOC": ("사용자취급설명서", "사용자 취급설명서", "사용자 매뉴얼",
                          "사용자 설명서", "사용 설명서"),
    "SOFTWARE_CONFIGURATION": ("소프트웨어 형상", "형상 목록", "형상관리 대장", "형상 식별"),
    "MAINTENANCE_DOC": ("유지보수문서", "유지보수 문서", "유지보수 계획", "유지보수 지침"),
    "VERIFICATION_RESULTS": ("검토 결과", "검토결과", "검토 의견", "검증 결과"),
    "VALIDATION_RESULTS": ("확인 결과", "확인결과", "타당성 확인"),
}
assert set(_TYPE_KEYWORDS) == set(DISPLAY_NAMES)

_FILENAME_WEIGHT = 3
_TITLE_WEIGHT = 2
_BODY_CAP = 3
_REQUIREMENT_TABLE_BONUS = 4
_MIN_ROWS_FOR_BONUS = 3
_DECIDE_MIN = 3
_DECIDE_MARGIN = 2
_MAX_CONFIDENCE = 0.95


def clean(text: str) -> str:
    """마크다운 강조·코드 표시를 걷어낸다. 표 셀에 남은 서식은 요구사항 글자가 아니다."""
    return re.sub(r"\s+", " ", _MARKDOWN_NOISE.sub(" ", text)).strip()


def _cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return any(cells) and all(_TABLE_SEPARATOR.match(c) for c in cells if c)


def tables_and_lines(text: str) -> tuple[list[list[list[str]]], list[str]]:
    """표(행 목록)와 표 밖의 줄을 가른다. 표는 '|' 로 시작하는 연속 줄이다."""
    tables: list[list[list[str]]] = []
    lines: list[str] = []
    current: list[list[str]] = []
    for raw in text.splitlines():
        if raw.lstrip().startswith("|"):
            cells = _cells(raw)
            if not _is_separator(cells):
                current.append(cells)
            continue
        if current:
            tables.append(current)
            current = []
        lines.append(raw)
    if current:
        tables.append(current)
    return tables, lines


def priority_of(cell: str) -> str:
    word = clean(cell).lower()
    if not word:
        return "SHOULD"
    for priority, words in _PRIORITY_WORDS:
        if word in words or any(word.startswith(w) for w in words if len(w) > 1):
            return priority
    return "SHOULD"


def _title_of(text: str) -> str:
    if len(text) <= MAX_TITLE_CHARS:
        return text
    cut = text.rfind(" ", 0, MAX_TITLE_CHARS - 1)
    if cut < MAX_TITLE_CHARS // 2:
        cut = MAX_TITLE_CHARS - 1
    return text[:cut].rstrip(" ,·.") + "…"


@dataclass
class _Columns:
    code: int
    name: int
    body: int | None
    priority: int | None
    headerless: bool


def _columns(table: list[list[str]]) -> _Columns | None:
    """머리행을 읽어 코드·제목·본문·중요도 열을 정한다. 코드 열과 글 열이 없으면 표가 아니다.

    머리행에 ID·코드 같은 말이 없어도 첫 열의 값이 코드 꼴이면 코드 열로 본다.
    """
    header = [clean(c) for c in table[0]]
    if not header:
        return None
    if _CODE_FULL.match(header[0]):
        # 머리행이 없는 표. 첫 열이 코드고 둘째 열이 글이라고 본다.
        return _Columns(0, 1, None, None, True) if len(header) > 1 else None

    code = next((i for i, h in enumerate(header) if _CODE_HEADER.search(h)), None)
    if code is None:
        first = next((clean(r[0]) for r in table[1:] if r and r[0].strip()), "")
        if not _CODE_FULL.match(first):
            return None
        code = 0

    candidates = [i for i, h in enumerate(header) if i != code and _TEXT_HEADER.search(h)]
    if not candidates:
        return None
    body = next((i for i in candidates if _BODY_HEADER.search(header[i])), None)
    if body is not None and len(candidates) == 1:
        body = None
    name = next(i for i in candidates if i != body)
    priority = next((i for i, h in enumerate(header) if _PRIORITY_HEADER.search(h)), None)
    return _Columns(code, name, body, priority, False)


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return clean(row[index])


def requirements_from_tables(tables: list[list[list[str]]]) -> list[DraftRequirement]:
    """표 규칙. 코드 열의 값이 코드 꼴인 행만 요구사항이다. 같은 코드는 처음 것만 받는다."""
    found: list[DraftRequirement] = []
    seen: set[str] = set()
    for table in tables:
        cols = _columns(table)
        if cols is None:
            continue
        rows = table if cols.headerless else table[1:]
        for row in rows:
            code = _cell(row, cols.code)
            if not _CODE_FULL.match(code) or code in seen:
                continue
            name = _cell(row, cols.name)
            if not name:
                continue
            body = _cell(row, cols.body) or name
            seen.add(code)
            found.append(
                DraftRequirement(
                    index=len(found),
                    code=code,
                    title=_title_of(name),
                    body=body[:MAX_BODY_CHARS],
                    priority=priority_of(_cell(row, cols.priority)),
                )
            )
    return found


def requirements_from_lines(lines: list[str]) -> list[DraftRequirement]:
    """줄머리 코드 규칙. `[SWFR.CON.004] 제목` 이나 `SWFR.CON.004 제목` 꼴이며 다음 줄부터
    빈 줄이나 다음 코드 전까지가 본문이다."""
    found: list[DraftRequirement] = []
    seen: set[str] = set()
    current: DraftRequirement | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is not None:
            joined = clean(" ".join(body)) or current.title
            current.body = joined[:MAX_BODY_CHARS]
            found.append(current)
        current, body = None, []

    for raw in lines:
        line = raw.strip()
        match = _CODE_LINE.match(clean(_HEADING.sub(r"\1", line)))
        if match:
            flush()
            code, rest = match.group(1), clean(match.group(2))
            if code in seen or not rest:
                continue
            seen.add(code)
            current = DraftRequirement(index=len(found), code=code, title=_title_of(rest), body="")
            continue
        if current is None:
            continue
        if not line or _HEADING.match(line):
            flush()
            continue
        body.append(line)
    flush()
    return found


def extract_requirements(text: str) -> list[DraftRequirement]:
    """표가 있으면 표만 믿는다. 표가 있는 문서에서 줄 규칙까지 돌리면 표를 설명하는
    문장(상위 항목 제목, 본문 참조)이 요구사항으로 섞여 들어온다."""
    tables, lines = tables_and_lines(text)
    from_tables = requirements_from_tables(tables)
    if from_tables:
        return from_tables
    return requirements_from_lines(lines)


# 추적 규칙(trace_rules._REQ_CODE)이 읽는 꼴. 이 꼴이 아니면 커밋·이슈가 그 코드를 가리켜도
# 링크가 생기지 않는다. 명세서에는 받아 두되 경고한다
_TRACEABLE_CODE = re.compile(r"^[A-Z]{2,5}(?:\.[A-Z]{2,5})+\.\d{3}$")

# 명세서 항목의 문제. BLOCKING 은 제출 전에 고쳐야 한다
DUPLICATE_CODE = "DUPLICATE_CODE"
INVALID_CODE = "INVALID_CODE"
MISSING_TITLE = "MISSING_TITLE"
UNTRACEABLE_CODE = "UNTRACEABLE_CODE"
BLOCKING_PROBLEMS = (DUPLICATE_CODE, INVALID_CODE, MISSING_TITLE)


@dataclass
class SpecItem:
    """명세서 한 행. 정형화 초안(DraftRequirement)과 달리 버리는 행이 없다.

    같은 코드가 또 나와도, 코드 꼴이 아니어도 위치와 함께 남긴다. 무엇이 문제인지는
    problems_of 가 정하고, 사람이 고치거나 지운다.
    """

    code: str | None
    title: str
    body: str
    priority: str
    location: str

    def as_dict(self) -> dict:
        return {
            "code": self.code, "title": self.title, "body": self.body,
            "priority": self.priority, "location": self.location,
        }


def spec_items(text: str) -> list[SpecItem]:
    """명세서에서 항목을 위치와 함께 뽑는다. 표가 있으면 표만 본다(extract_requirements 와 같다).

    표에서는 유효한 코드가 한 행이라도 있는 표만 요구사항 표로 본다. 그 표 안에서 코드 칸이
    비지 않았는데 코드 꼴이 아닌 행은 버리지 않고 남긴다.
    """
    tables, _ = tables_and_lines(text)
    items: list[SpecItem] = []
    for t_no, table in enumerate(tables, start=1):
        cols = _columns(table)
        if cols is None:
            continue
        start = 0 if cols.headerless else 1
        rows = table[start:]
        if not any(_CODE_FULL.match(_cell(r, cols.code)) for r in rows):
            continue
        for r_no, row in enumerate(rows, start=start + 1):
            code = _cell(row, cols.code)
            name = _cell(row, cols.name)
            if not code and not name:
                continue
            if not code:
                continue  # 묶음 제목 같은 행. 코드 칸이 빈 행은 요구사항이 아니다
            body = _cell(row, cols.body) or name
            items.append(SpecItem(
                code=code, title=_title_of(name) if name else "", body=body[:MAX_BODY_CHARS],
                priority=priority_of(_cell(row, cols.priority)), location=f"표 {t_no} · {r_no}행",
            ))
    if items:
        return items
    return _spec_items_from_lines(text)


def _spec_items_from_lines(text: str) -> list[SpecItem]:
    items: list[SpecItem] = []
    current: SpecItem | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is not None:
            current.body = (clean(" ".join(body)) or current.title)[:MAX_BODY_CHARS]
            items.append(current)
        current, body = None, []

    for no, raw in enumerate(text.splitlines(), start=1):
        if raw.lstrip().startswith("|"):
            continue
        line = raw.strip()
        match = _CODE_LINE.match(clean(_HEADING.sub(r"\1", line)))
        if match:
            flush()
            rest = clean(match.group(2))
            current = SpecItem(code=match.group(1), title=_title_of(rest) if rest else "",
                               body="", priority="SHOULD", location=f"{no}번째 줄")
            continue
        if current is None:
            continue
        if not line or _HEADING.match(line):
            flush()
            continue
        body.append(line)
    flush()
    return items


def spec_parents(text: str, item_codes: set[str]) -> list[dict]:
    """명세서의 상위 요구사항. 표 밖의 줄(절 제목 등)이 요구사항 코드로 시작하는데 표의
    요구사항이 아닌 것이다. 예: "SFR.CON.001 확장 가능한 커넥터 구조".

    표가 없는 명세서는 그런 줄이 곧 요구사항이라(_spec_items_from_lines) 상위가 없다.
    커밋·이슈가 가리킬 수 있는 꼴(_TRACEABLE_CODE)만 받는다. 문서번호(IM-001) 같은 줄을
    상위로 읽지 않으려는 것이다.
    """
    tables, _ = tables_and_lines(text)
    if not tables or not item_codes:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for no, raw in enumerate(text.splitlines(), start=1):
        if raw.lstrip().startswith("|"):
            continue
        match = _CODE_LINE.match(clean(_HEADING.sub(r"\1", raw.strip())))
        if not match:
            continue
        code = match.group(1)
        if code in item_codes or code in seen or not _TRACEABLE_CODE.match(code):
            continue
        seen.add(code)
        out.append({"code": code, "title": _title_of(clean(match.group(2))),
                    "location": f"{no}번째 줄"})
    return out


def parent_of(item: dict, parent_codes: list[str]) -> str | None:
    """항목이 속한 상위 요구사항. 항목 설명·명칭이 상위 코드를 적었으면 그것이다(첫 번째).
    적지 않았으면 모른다. 위치로 짐작하지 않는다."""
    text = f"{item.get('title') or ''} {item.get('body') or ''}"
    for code in parent_codes:
        if re.search(rf"(?<![\w.]){re.escape(code)}(?![\w])", text):
            return code
    return None


def problems_of(items: list[dict]) -> list[list[str]]:
    """항목마다의 문제 목록. items 는 code·title 을 가진 사전이다(DB 행이나 SpecItem.as_dict)."""
    counts: dict[str, int] = {}
    for item in items:
        if item.get("code"):
            counts[item["code"]] = counts.get(item["code"], 0) + 1
    out: list[list[str]] = []
    for item in items:
        code, found = item.get("code"), []
        if not code or not _CODE_FULL.match(code):
            found.append(INVALID_CODE)
        elif not _TRACEABLE_CODE.match(code):
            found.append(UNTRACEABLE_CODE)
        if code and counts.get(code, 0) > 1:
            found.append(DUPLICATE_CODE)
        if not (item.get("title") or "").strip():
            found.append(MISSING_TITLE)
        out.append(found)
    return out


def is_code(value: str) -> bool:
    return bool(_CODE_FULL.match(value))


def _title_lines(text: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("|") or _COMMENT.match(line):
            continue
        out.append(clean(_HEADING.sub(r"\1", line)))
        if len(out) >= limit:
            break
    return out


def classify_type(filename: str, text: str, requirement_count: int = 0) -> TypeGuess:
    """22종 중 하나를 키워드 점수로 고른다. 점수가 낮거나 1·2위가 붙으면 결정하지 않는다."""
    head = text[:_HEAD_CHARS]
    title_text = " ".join(_title_lines(head))
    scores: dict[str, int] = {}
    for product_type, words in _TYPE_KEYWORDS.items():
        score = 0
        for word in words:
            if word in filename:
                score += _FILENAME_WEIGHT
            if word in title_text:
                score += _TITLE_WEIGHT
            score += min(head.count(word), _BODY_CAP)
        if score:
            scores[product_type] = score
    if requirement_count >= _MIN_ROWS_FOR_BONUS:
        scores["REQUIREMENTS_SPEC"] = scores.get("REQUIREMENTS_SPEC", 0) + _REQUIREMENT_TABLE_BONUS

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        return TypeGuess(None, 0.0, False, scores)
    top_type, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    decided = top >= _DECIDE_MIN and top - second >= _DECIDE_MARGIN
    if not decided:
        return TypeGuess(None, 0.0, False, scores)
    confidence = round(min(_MAX_CONFIDENCE, top / (top + second)), 2)
    return TypeGuess(top_type, confidence, True, scores)


def guess_title(text: str) -> str | None:
    """첫 표제, 없으면 짧은 첫 줄. 둘 다 없으면 None 이라 호출부가 LLM 에 묻는다."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("|") or _COMMENT.match(line):
            continue
        heading = _HEADING.match(line)
        if heading:
            return clean(heading.group(1))[:MAX_DOC_TITLE_CHARS] or None
        cleaned = clean(line)
        if 0 < len(cleaned) <= 120:
            return cleaned
        return None
    return None


def guess_version(text: str) -> str | None:
    match = _VERSION_RE.search(text[:_HEAD_CHARS])
    return match.group(1) if match else None


def guess_authored_date(text: str) -> str | None:
    for match in _DATE_RE.finditer(text[:_HEAD_CHARS]):
        year, month, day = (int(g) for g in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    return None


def head_for_llm(text: str, limit: int = 3000) -> str:
    """LLM 에 보여 줄 문서 머리. 표 줄은 빼고 글만 남긴다. 표는 길기만 하고 유형 단서가 적다."""
    kept: list[str] = []
    size = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("|") or _COMMENT.match(line):
            continue
        kept.append(line)
        size += len(line) + 1
        if size >= limit:
            break
    return "\n".join(kept)[:limit]


def strip_think(answer: str) -> str:
    """추론형 모델은 답 앞에 <think> 블록을 붙인다. 답은 그 뒤다."""
    return _THINK.sub("", answer).strip()


def parse_type_answer(answer: str) -> str | None:
    """LLM 답에서 22종 코드 하나를 찾는다. 둘 이상이거나 없으면 None 이다."""
    tokens = set(re.findall(r"[A-Z][A-Z_]{3,}", strip_think(answer).upper()))
    hits = [t for t in DISPLAY_NAMES if t in tokens]
    if len(hits) != 1:
        return None
    return hits[0]


def parse_title_answer(answer: str) -> str | None:
    """LLM 답의 첫 줄을 제목으로 본다. 모른다고 하면 None."""
    for raw in strip_think(answer).splitlines():
        line = clean(raw).strip("\"'“”「」 ")
        if not line:
            continue
        if line.upper() == "UNKNOWN":
            return None
        return line[:MAX_DOC_TITLE_CHARS]
    return None
