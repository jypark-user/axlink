"""원본 payload 에서 추적관계의 근거를 찾는다. 순수 함수만 둔다(DB·네트워크 없음).

근거는 명시적인 것만 인정한다(QUR.PIP.001). 사람이 적은 요구사항 코드, GH-/RM- 이슈 참조,
Redmine 의 REQ ID 커스텀 필드와 issue relations, 그리고 산출물 파일 경로 언급이다.
유사도로 짐작하지 않는다. 규칙 전체는 ARC-007 에 적어 두었다.

여기서는 "무엇이 무엇을 가리키는가" 만 뽑는다. 가리킨 대상이 실제로 표준 모델에 있는지는
trace_service 가 확인한다. 없으면 링크를 만들지 않는다.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.standard import design_refs
from app.standard.mapping_rules import MappingRules

# 요구사항 코드의 꼴. 우리 체계(SWFR.CON.004)뿐 아니라 점으로 이어진 대문자 묶음이면 후보로
# 본다. 후보가 실제 요구사항인지는 사업의 요구사항 목록과 대조해서 정한다.
_REQ_CODE = re.compile(r"\b([A-Z]{2,5}(?:\.[A-Z]{2,5})+\.\d{3})\b")
# 도구별 접두가 붙은 이슈 참조만 읽는다. 맨 #17 은 어느 도구인지 몰라 근거로 쓰지 않는다.
_ISSUE_REF = re.compile(r"\b(GH|RM)-(\d+)\b")
# 커밋 제목의 유형. test 유형이면 시험으로 이어진 것으로 본다.
_COMMIT_TYPE = re.compile(r"^\s*([a-z]+)(?:\([^)]*\))?!?:")
_TYPE_LABEL = re.compile(r"^유형:\s*(.+)$")

_MAX_TEXT = 300

# 표준 링크 종류. trace_link.link_kind CHECK 와 같다.
DESIGNS, IMPLEMENTS, TESTS, DELIVERS = "DESIGNS", "IMPLEMENTS", "TESTS", "DELIVERS"

# 이슈의 성격을 말해 주는 이름. Redmine 은 트래커, GitHub 은 「유형: …」 라벨이다.
_DESIGN_NAMES = {"설계"}
_TEST_NAMES = {"시험", "테스트"}
# 산출물 자리의 성격. 설계 문서는 설계로, 시험 문서는 시험으로 잇고 나머지는 납품으로 본다.
_DESIGN_PRODUCTS = {"SOFTWARE_DESIGN"}
_TEST_PRODUCTS = {"TEST_CASES_PROCEDURES", "TEST_REPORT", "VERIFICATION_RESULTS",
                  "VALIDATION_RESULTS"}

# 근거 유형. trace_link.evidence_kind CHECK 와 같다.
TEXT_REQ_CODE = "TEXT_REQ_CODE"
TEXT_ISSUE_REF = "TEXT_ISSUE_REF"
TEXT_FILE_PATH = "TEXT_FILE_PATH"
CUSTOM_FIELD = "CUSTOM_FIELD"
ISSUE_RELATION = "ISSUE_RELATION"


DOC_REQ_REF = "DOC_REQ_REF"


@dataclass(frozen=True)
class Evidence:
    """근거 하나. target 은 아직 표준 모델의 id 가 아니라 원문에 적힌 참조다."""

    kind: str
    text: str
    target: tuple[str, str]  # ("REQ", 코드) | ("GH", 번호) | ("RM", 번호) | ("FILE", 경로)
    link_kind: str
    # 근거 위치(설계 문서의 경로·커밋·줄 등). 대부분의 근거는 원문 URL 하나로 충분해 비어 있다
    meta: dict[str, Any] | None = None
    url: str | None = None  # 원본 URL 대신 쓸 주소(설계 문서의 그 줄)


@dataclass(frozen=True)
class Exclusion:
    """분류 규칙이 일부러 뺀 근거. 옛 링크를 '끊김'이 아니라 '제외'로 표시하려고 남긴다."""

    target: tuple[str, str]
    link_kind: str
    reason: str


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 1] + "…"


def _lines_with(text: str, pattern: re.Pattern[str]) -> list[tuple[re.Match[str], str]]:
    found: list[tuple[re.Match[str], str]] = []
    for line in (text or "").splitlines():
        for matched in pattern.finditer(line):
            found.append((matched, line.strip()))
    return found


def req_codes(text: str, known_codes: set[str]) -> list[tuple[str, str]]:
    """본문에 적힌 요구사항 코드와 그 줄. 사업에 없는 코드는 오타로 보고 버린다."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for matched, line in _lines_with(text, _REQ_CODE):
        code = matched.group(1)
        if code in known_codes and code not in seen:
            seen.add(code)
            out.append((code, line))
    return out


def issue_refs(text: str) -> list[tuple[str, str, str]]:
    """본문의 GH-n / RM-n 참조와 그 줄."""
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for matched, line in _lines_with(text, _ISSUE_REF):
        key = (matched.group(1), matched.group(2))
        if key not in seen:
            seen.add(key)
            out.append((key[0], key[1], line))
    return out


def file_paths(text: str, known_paths: set[str]) -> list[tuple[str, str]]:
    """본문에 적힌 산출물 파일 경로와 그 줄. 수집된 산출물의 경로만 인정한다."""
    out: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        for path in sorted(known_paths):
            if path and path in line:
                out.append((path, line.strip()))
    return out


def commit_link_kind(message: str) -> str:
    """변경 파일을 모를 때의 분류. 커밋 제목의 유형이 test 면 시험, 아니면 구현이다."""
    first = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    matched = _COMMIT_TYPE.match(first)
    return TESTS if matched and matched.group(1) == "test" else IMPLEMENTS


# 변경 파일 분류(ARC-024 2-3). 경로 관례만 쓴다. 관례를 벗어나면 "코드"로 읽힌다.
_TEST_FILE = re.compile(
    r"(^|/)(tests?)/|(^|/)test_[^/]+\.py$|_test\.py$|\.(test|spec)\.[cm]?[jt]sx?$"
)
_DOC_EXT = (".md", ".txt", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".pdf", ".hwp", ".hwpx",
            ".csv")


def file_category(path: str, design_globs: list[str]) -> str:
    """'design' | 'test' | 'doc' | 'code'."""
    if design_globs and design_refs.match_any(path, design_globs):
        return "design"
    if _TEST_FILE.search(path):
        return "test"
    if path.startswith("docs/") or path.lower().endswith(_DOC_EXT):
        return "doc"
    return "code"


def change_link_kinds(
    title: str, files: list[str] | None, design_globs: list[str]
) -> tuple[list[str], str | None]:
    """변경 하나가 요구사항에 어떤 관계로 이어지는가. (관계 목록, 아무것도 없을 때 사유).

    변경 파일을 모르면 지금 규칙(제목 유형)을 그대로 쓴다. 알면 파일이 말한다. 섞여 있으면
    관계가 여럿이다. 제목 유형(docs·test)만으로는 정하지 않는다.
    """
    if files is None:
        return [commit_link_kind(title)], None
    cats = {file_category(f, design_globs) for f in files}
    order = (("code", IMPLEMENTS), ("test", TESTS), ("design", DESIGNS))
    kinds = [kind for cat, kind in order if cat in cats]
    if kinds:
        return kinds, None
    if cats == {"doc"}:
        return [], "관리·매뉴얼 문서만 바꾼 변경이라 구현으로 세지 않음"
    return [], "변경 파일이 없음"


def _files_of(payload: dict[str, Any]) -> list[str] | None:
    files = payload.get("files")
    if not isinstance(files, list):
        return None
    return [str(f.get("filename") or f) if isinstance(f, dict) else str(f) for f in files]


def merged_pr_number(payload: dict[str, Any]) -> str | None:
    """`Merge pull request #n` 병합 커밋이면 n. 아니면 None."""
    message = (payload.get("commit") or {}).get("message") or ""
    if len(payload.get("parents") or []) < 2:
        return None
    m = re.match(r"^Merge pull request #(\d+)\b", message.strip())
    return m.group(1) if m else None


def _kind_by_name(name: str | None) -> str:
    name = (name or "").strip()
    if name in _DESIGN_NAMES:
        return DESIGNS
    if name in _TEST_NAMES:
        return TESTS
    return IMPLEMENTS


def product_link_kind(product_type: str) -> str:
    """산출물이 요구사항에 어떻게 이어지는가. 자리(유형)가 말해 준다."""
    if product_type in _DESIGN_PRODUCTS:
        return DESIGNS
    if product_type in _TEST_PRODUCTS:
        return TESTS
    return DELIVERS


def github_issue_link_kind(payload: dict[str, Any]) -> str:
    for item in payload.get("labels") or []:
        matched = _TYPE_LABEL.match(str(item.get("name", "")).strip())
        if matched:
            return _kind_by_name(matched.group(1))
    return IMPLEMENTS


def redmine_issue_link_kind(payload: dict[str, Any]) -> str:
    return _kind_by_name((payload.get("tracker") or {}).get("name"))


def _from_text(
    text: str, link_kind: str, known_codes: set[str], known_paths: set[str],
    with_refs: bool,
) -> list[Evidence]:
    found: list[Evidence] = []
    for code, line in req_codes(text, known_codes):
        found.append(Evidence(TEXT_REQ_CODE, _clip(line), ("REQ", code), link_kind))
    if with_refs:
        for prefix, number, line in issue_refs(text):
            found.append(Evidence(TEXT_ISSUE_REF, _clip(line), (prefix, number), link_kind))
    for path, line in file_paths(text, known_paths):
        found.append(Evidence(TEXT_FILE_PATH, _clip(line), ("FILE", path), DELIVERS))
    return found


def _change_evidence(
    text: str, title: str, files: list[str] | None, design_globs: list[str],
    known_codes: set[str], known_paths: set[str],
) -> tuple[list[Evidence], list[Exclusion]]:
    kinds, reason = change_link_kinds(title, files, design_globs)
    found: list[Evidence] = []
    excluded: list[Exclusion] = []
    refs = _from_text(text, IMPLEMENTS, known_codes, known_paths, True)
    for e in refs:
        if e.link_kind == DELIVERS:
            found.append(e)  # 산출물 경로 근거는 분류와 무관하게 납품으로 잇는다
            continue
        if not kinds:
            excluded.append(Exclusion(e.target, IMPLEMENTS, reason or "분류 제외"))
            continue
        for kind in kinds:
            found.append(Evidence(e.kind, e.text, e.target, kind))
    return found, excluded


def commit_evidence(
    payload: dict[str, Any], known_codes: set[str], known_paths: set[str],
    design_globs: list[str] | None = None,
) -> list[Evidence]:
    """GitHub 커밋. 제목·본문 전체를 본다. 본문은 code_change 에 없고 원본에만 있다."""
    return commit_evidence_with_exclusions(payload, known_codes, known_paths, design_globs)[0]


def commit_evidence_with_exclusions(
    payload: dict[str, Any], known_codes: set[str], known_paths: set[str],
    design_globs: list[str] | None = None,
) -> tuple[list[Evidence], list[Exclusion]]:
    message = ((payload.get("commit") or {}).get("message") or "")
    title = message.strip().splitlines()[0] if message.strip() else ""
    return _change_evidence(message, title, _files_of(payload), design_globs or [],
                            known_codes, known_paths)


def pull_request_evidence(
    payload: dict[str, Any], known_codes: set[str], known_paths: set[str],
    design_globs: list[str] | None = None,
) -> list[Evidence]:
    return pull_request_evidence_with_exclusions(
        payload, known_codes, known_paths, design_globs)[0]


def pull_request_evidence_with_exclusions(
    payload: dict[str, Any], known_codes: set[str], known_paths: set[str],
    design_globs: list[str] | None = None,
) -> tuple[list[Evidence], list[Exclusion]]:
    title = payload.get("title") or ""
    text = f"{title}\n{payload.get('body') or ''}"
    return _change_evidence(text, title, _files_of(payload), design_globs or [],
                            known_codes, known_paths)


def design_doc_evidence(payload: dict[str, Any], known_codes: set[str]) -> list[Evidence]:
    """저장소 설계 문서의 명시적 참조(ARC-024 2-1). 삭제된 문서는 근거가 없다."""
    if payload.get("deleted") or not payload.get("text"):
        return []
    info = design_refs.parse(payload["text"], known_codes)
    base = payload.get("html_url") or ""
    out: list[Evidence] = []
    for ref in info.refs:
        meta = {
            "repo": payload.get("repo"), "path": payload.get("path"),
            "commitSha": payload.get("commit_sha"), "blobSha": payload.get("blob_sha"),
            "line": ref.line_no, "section": ref.section, "form": ref.form,
            "qualifier": ref.qualifier, "docId": info.doc_id,
            "docStatus": info.status, "docStatusText": info.status_text,
        }
        out.append(Evidence(
            DOC_REQ_REF, _clip(ref.line), ("REQ", ref.code), DESIGNS, meta,
            f"{base}#L{ref.line_no}" if base else None,
        ))
    return out


def github_issue_evidence(
    payload: dict[str, Any], known_codes: set[str], known_paths: set[str]
) -> list[Evidence]:
    """GitHub 이슈(요구사항이 아닌 것). 제목·본문의 요구사항 코드와 파일 경로를 본다.

    이슈끼리의 GH-n 참조는 읽지 않는다. 이슈가 이슈를 언급한 것은 추적표의 축이 아니다.
    """
    text = f"{payload.get('title') or ''}\n{payload.get('body') or ''}"
    return _from_text(text, github_issue_link_kind(payload), known_codes, known_paths, False)


def requirement_issue_evidence(
    payload: dict[str, Any], known_paths: set[str]
) -> list[Evidence]:
    """요구사항 이슈 자신. 본문에 적힌 산출물 경로만 본다(요구사항끼리는 잇지 않는다)."""
    text = f"{payload.get('title') or ''}\n{payload.get('body') or ''}"
    return [
        Evidence(TEXT_FILE_PATH, _clip(line), ("FILE", path), DELIVERS)
        for path, line in file_paths(text, known_paths)
    ]


def redmine_issue_evidence(
    payload: dict[str, Any], rules: MappingRules, known_codes: set[str], known_paths: set[str]
) -> list[Evidence]:
    """Redmine 이슈. 커스텀 필드 REQ ID 가 1차 근거고, 본문 코드와 relations 가 그 다음이다."""
    link_kind = redmine_issue_link_kind(payload)
    found: list[Evidence] = []

    for field in payload.get("custom_fields") or []:
        if field.get("name") != rules.req_id_field or not field.get("value"):
            continue
        values = field["value"] if isinstance(field["value"], list) else [field["value"]]
        for value in values:
            for code, _ in req_codes(str(value), known_codes):
                found.append(Evidence(
                    CUSTOM_FIELD, _clip(f"{rules.req_id_field}: {value}"),
                    ("REQ", code), link_kind,
                ))

    text = f"{payload.get('subject') or ''}\n{payload.get('description') or ''}"
    found += _from_text(text, link_kind, known_codes, known_paths, False)

    own = str(payload.get("id") or "")
    for rel in payload.get("relations") or []:
        # 관계는 양쪽 이슈에 같은 방향으로 실려 온다. 출발점인 쪽에서만 만들어 중복을 막는다.
        if str(rel.get("issue_id") or "") != own or not rel.get("issue_to_id"):
            continue
        rel_type = rel.get("relation_type") or "relates"
        found.append(Evidence(
            ISSUE_RELATION, _clip(f"{rel_type} RM-{rel['issue_to_id']}"),
            ("RM", str(rel["issue_to_id"])), link_kind,
        ))
    return found
