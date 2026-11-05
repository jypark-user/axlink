"""저장소 설계 문서에서 명시적인 요구사항 참조만 뽑는다 (ARC-024). 순수 함수만 둔다.

인정하는 꼴은 셋이다. 머리 표의 `관련` 행(또는 목록형 `- 관련 요구사항:` 줄), "요구사항 대응표" 절의
표 행(첫 칸이 코드), 절 제목 괄호 안의 코드. 본문에 지나가듯 나온 코드와 범위 표기
(`SWFR.CON.001~007`)는 근거가 아니다. 문서 상태도 문서가 스스로 선언한 값만 읽는다.

앱(trace_service)과 추적표 생성기(scripts/build_traceability.py)가 같은 함수를 쓴다.
"""

import re
from dataclasses import dataclass, field

# 요구사항 코드 꼴. trace_rules 와 같다. 범위 표기의 앞쪽(…001~007)은 따로 거른다.
_CODE = re.compile(r"\b([A-Z]{2,5}(?:\.[A-Z]{2,5})+\.\d{3})\b(~\d{3})?(`?\s*\(([^)]*)\))?")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_ARC_ID = re.compile(r"\b(ARC-\d{3})\b")
_IM_ID = re.compile(r"\((IM-\d{3})\)|\b(IM-\d{3})\b")
_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_QUALIFIERS = ("미결", "검토 필요")

RELATED_ROW, MAPPING_TABLE, SECTION_TITLE = "관련 행", "대응표", "절 제목"
CONFIRMED, DRAFT, UNKNOWN = "CONFIRMED", "DRAFT", "UNKNOWN"


@dataclass(frozen=True)
class Ref:
    code: str
    line_no: int  # 1부터
    line: str  # 그 줄 원문(앞뒤 공백 정리)
    section: str  # 가장 가까운 절 제목. 없으면 ""
    form: str  # RELATED_ROW | MAPPING_TABLE | SECTION_TITLE
    qualifier: str | None = None  # "미결" · "검토 필요" 처럼 참조에 붙은 한정어


@dataclass
class DocInfo:
    doc_id: str | None
    status: str
    status_text: str | None
    refs: list[Ref] = field(default_factory=list)


def _cells(line: str) -> list[str] | None:
    m = _TABLE_ROW.match(line)
    if not m:
        return None
    return [c.strip() for c in m.group(1).split("|")]


def _plain(text: str) -> str:
    return re.sub(r"[*`]", "", text).strip()


def _codes(text: str, known: set[str]) -> list[tuple[str, str | None]]:
    """줄 조각의 코드와 한정어. 범위 표기는 뺀다. 사업에 없는 코드는 오타로 보고 버린다."""
    out: list[tuple[str, str | None]] = []
    for m in _CODE.finditer(text):
        code, ranged, paren = m.group(1), m.group(2), m.group(4)
        if ranged or code not in known:
            continue
        # 괄호 한정어(`CODE`(미결)) 또는 코드 바로 뒤의 한정어(CODE 미결)
        tail = text[m.end() : m.end() + 8]
        qualifier = next(
            (q for q in _QUALIFIERS if (paren and q in paren) or tail.lstrip().startswith(q)), None
        )
        if (code, qualifier) not in out:
            out.append((code, qualifier))
    return out


def _status(lines: list[str]) -> tuple[str, str | None]:
    """문서가 선언한 상태. 앞쪽 40줄만 본다(머리 표·머리말)."""
    for raw in lines[:40]:
        cells = _cells(raw)
        if cells and len(cells) >= 2 and _plain(cells[0]) == "상태":
            text = _plain(cells[1])
            return _status_of(text), text
        m = re.match(r"^\s*-\s*상태\s*[:：]\s*(.+)$", raw)
        if m:
            text = _plain(m.group(1))
            return _status_of(text), text
    for raw in lines[:40]:
        m = re.search(r"\bv\d+(?:\.\d+)*\s*(초안|확정)", raw)
        if m:
            text = _plain(m.group(0))
            return _status_of(text), text
    return UNKNOWN, None


def _status_of(text: str) -> str:
    if "초안" in text:
        return DRAFT
    if "확정" in text:
        return CONFIRMED
    return UNKNOWN


def _doc_id(lines: list[str]) -> str | None:
    for raw in lines[:10]:
        h = _HEADING.match(raw)
        if not h:
            continue
        title = h.group(2)
        m = _ARC_ID.search(title)
        if m:
            return m.group(1)
        m = _IM_ID.search(title)
        if m:
            return m.group(1) or m.group(2)
        return None
    return None


def parse(text: str, known_codes: set[str]) -> DocInfo:
    lines = (text or "").splitlines()
    status, status_text = _status(lines)
    info = DocInfo(doc_id=_doc_id(lines), status=status, status_text=status_text)

    section = ""
    in_mapping_table = False
    seen: set[tuple[str, str]] = set()

    def add(code: str, qualifier: str | None, n: int, raw: str, form: str) -> None:
        key = (code, form)
        if key in seen:
            return
        seen.add(key)
        info.refs.append(Ref(code, n, raw.strip(), section, form, qualifier))

    for n, raw in enumerate(lines, start=1):
        h = _HEADING.match(raw)
        if h:
            title = h.group(2)
            section = _plain(title)
            in_mapping_table = "요구사항 대응표" in title
            # 절 제목 괄호 안의 코드만. 제목 본문에 그냥 적힌 코드는 지나가는 언급으로 본다
            for paren in re.findall(r"\(([^)]*)\)", title):
                for code, qualifier in _codes(paren, known_codes):
                    add(code, qualifier, n, raw, SECTION_TITLE)
            continue

        cells = _cells(raw)
        if cells:
            if len(cells) >= 2 and _plain(cells[0]) == "관련":
                for code, qualifier in _codes(" ".join(cells[1:]), known_codes):
                    add(code, qualifier, n, raw, RELATED_ROW)
            elif in_mapping_table:
                for code, qualifier in _codes(cells[0], known_codes):
                    add(code, qualifier, n, raw, MAPPING_TABLE)
            continue

        m = re.match(r"^\s*-\s*관련\s*요구사항\s*[:：]\s*(.+)$", raw)
        if m:
            for code, qualifier in _codes(m.group(1), known_codes):
                add(code, qualifier, n, raw, RELATED_ROW)
    return info


def match_any(path: str, patterns: list[str]) -> bool:
    """경로가 설정 패턴 중 하나에 맞는가. `*` 는 한 단계, `**` 는 여러 단계."""
    for pattern in patterns:
        regex = re.escape(pattern.strip()).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*")
        regex = regex.replace(r"\*", "[^/]*")
        if pattern.strip() and re.fullmatch(regex, path):
            return True
    return False
