"""GitHub 원본 → 표준 모델 매핑. 순수 함수만 둔다(DB·네트워크 없음).

우리 저장소는 요구사항 41건을 GitHub 이슈로 관리한다(작업 규약 §2). 그래서 이슈가
두 갈래로 갈린다 — 「유형: 요구사항」 라벨이 붙은 것은 requirement, 나머지는 issue.
GitHub 만 쓰는 용역업체 케이스가 그대로 여기서 성립한다.
"""

import re
from typing import Any

from app.standard.mapping_rules import MappingRules

_DEFAULT_RULES = MappingRules()

# "[SWFR.CON.001] 커넥터는 ..." 에서 코드와 제목을 가른다.
_CODE_IN_TITLE = re.compile(r"^\[([A-Z]{2,5}(?:\.[A-Z]{2,5})+\.\d{3})\]\s*(.*)$")
_TYPE_LABEL = re.compile(r"^유형:\s*(.+)$")
_PRIORITY_ROW = re.compile(r"\|\s*중요도\s*\|\s*([^|]+?)\s*\|")

_PRIORITY = {"필수": "MUST", "권장": "SHOULD", "선택": "COULD", "제외": "WONT"}


def labels(payload: dict[str, Any]) -> list[str]:
    return [str(item.get("name", "")) for item in payload.get("labels") or []]


def issue_type(payload: dict[str, Any]) -> str | None:
    """「유형: 요구사항」 같은 라벨에서 유형만 뽑는다."""
    for label in labels(payload):
        matched = _TYPE_LABEL.match(label.strip())
        if matched:
            return matched.group(1).strip()
    return None


def classify_issue(payload: dict[str, Any], rules: MappingRules = _DEFAULT_RULES) -> str:
    """이슈 하나가 표준 모델의 어느 테이블로 갈지 정한다.

    라벨이 1차 근거고, 어떤 라벨이 요구사항인지는 연결별 설정이다(SWFR.CON.002).
    라벨이 없어도 제목이 [SWFR.xxx.001] 꼴이면 요구사항으로 본다 —
    라벨 정리가 안 된 저장소에서도 추적 ID 는 제목에 남아 있기 때문이다.
    """
    if rules.requirement_label in labels(payload):
        return "REQUIREMENT"
    if _CODE_IN_TITLE.match(payload.get("title") or ""):
        return "REQUIREMENT"
    return "ISSUE"


def to_requirement(payload: dict[str, Any]) -> dict[str, Any]:
    raw_title = (payload.get("title") or "").strip()
    matched = _CODE_IN_TITLE.match(raw_title)
    code, title = (matched.group(1), matched.group(2)) if matched else (None, raw_title)
    body = payload.get("body") or ""

    return {
        "code": code,
        "title": title[:500] or raw_title[:500],
        "body": body,
        "priority": _priority(body),
        # 이슈를 닫았다는 건 구현했다는 뜻이지 시험으로 검증했다는 뜻은 아니다.
        # VERIFIED 로 올리는 건 시험 결과(TST)와 이어질 때다 — SWFR.PIP.008 이행률의 분자.
        "status": "IMPLEMENTED" if payload.get("state") == "closed" else "DEFINED",
        "assignee": _login(payload.get("assignee")),
        "source_created_at": payload.get("created_at"),
        "source_updated_at": payload.get("updated_at"),
        "external_url": payload.get("html_url"),
    }


SOURCE_ISSUE_CLOSED = "SOURCE_ISSUE_CLOSED"


def requirement_status_basis(status: str, tool: str | None) -> str | None:
    """요구사항 상태의 출처. to_requirement 가 GitHub 닫힘으로 만든 IMPLEMENTED 만 짚는다.

    다른 도구나 문서·수기로 들어온 상태는 이 규칙으로 생긴 게 아니라 None 이다.
    """
    if tool == "GITHUB" and status == "IMPLEMENTED":
        return SOURCE_ISSUE_CLOSED
    return None


def to_issue(payload: dict[str, Any]) -> dict[str, Any]:
    closed = payload.get("state") == "closed"
    return {
        "issue_key": f"GH-{payload.get('number')}",
        "title": (payload.get("title") or "").strip()[:500],
        "body": payload.get("body") or "",
        "status": "CLOSED" if closed else "OPEN",
        # GitHub 이슈에는 심각도가 없다. 근거 없이 채우지 않는다(GH-116). 화면은 '미지정'
        "severity": None,
        "source_priority": None,
        "assignee": _login(payload.get("assignee")),
        "source_created_at": payload.get("created_at"),
        "source_updated_at": payload.get("updated_at"),
        "resolved_at": payload.get("closed_at") if closed else None,
        "external_url": payload.get("html_url"),
    }


def to_code_change(kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if kind == "commit":
        return _commit(payload)
    if kind == "pull_request":
        return _pull_request(payload)
    return None


def _commit(payload: dict[str, Any]) -> dict[str, Any] | None:
    commit = payload.get("commit") or {}
    author = commit.get("author") or {}
    occurred = author.get("date") or (commit.get("committer") or {}).get("date")
    if not occurred:
        return None  # 시각이 없으면 추이 지표에 못 쓴다 — 넣지 않는다.
    message = (commit.get("message") or "").strip()
    return {
        "kind": "COMMIT",
        "title": (message.splitlines()[0] if message else payload.get("sha", ""))[:500],
        "ref_name": payload.get("sha"),
        "state": "CREATED",
        "author": author.get("name") or _login(payload.get("author")),
        "occurred_at": occurred,
        "external_url": payload.get("html_url"),
    }


def _pull_request(payload: dict[str, Any]) -> dict[str, Any] | None:
    occurred = payload.get("created_at")
    if not occurred:
        return None
    if payload.get("merged_at"):
        state = "MERGED"
    elif payload.get("state") == "closed":
        state = "CLOSED"
    else:
        state = "OPENED"
    return {
        "kind": "MERGE_REQUEST",
        "title": (payload.get("title") or "").strip()[:500],
        "ref_name": ((payload.get("head") or {}).get("ref") or "")[:300] or None,
        "state": state,
        "author": _login(payload.get("user")),
        "occurred_at": occurred,
        "external_url": payload.get("html_url"),
    }


def _priority(body: str) -> str:
    matched = _PRIORITY_ROW.search(body)
    return _PRIORITY.get(matched.group(1).strip(), "SHOULD") if matched else "SHOULD"


def _login(user: Any) -> str | None:
    if isinstance(user, dict):
        return user.get("login") or user.get("name")
    return None


def to_work_product(payload: dict[str, Any], product_type: str) -> dict[str, Any] | None:
    """저장소에서 가져온 파일을 산출물로 옮긴다.

    산출물 목록에는 항목이 미리 있고(ISO/IEC 29110 관리객체), 수집이 그 항목을 채운다.
    파일이 실제로 올라와 있다는 것이 곧 제출의 근거다 — SWFR.PIP.009.
    """
    path = payload.get("path")
    if not path:
        return None
    sha = payload.get("sha") or "0"
    return {
        "type": product_type,
        "title": path.rsplit("/", 1)[-1],
        "file_uri": path,
        "external_url": payload.get("htmlUrl"),
        # 내용이 바뀌면 sha 가 바뀐다. 버전 표기를 사람이 손대지 않아도 된다.
        "version": sha[:12],
        # 보관된 원본은 전체 sha 로 이름 지어져 있다. 짧은 표기로는 도달하지 못한다.
        "source_revision": sha,
    }
