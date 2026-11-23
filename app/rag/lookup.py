"""질문에 적힌 ID 로 바로 찾는다.

착수보고 대표 질의에 「이슈 #123 의 내용과 처리 상태」, 「REQ-018 과 연결된 설계·시험 항목」이
있다. 유사도 검색은 `GH-139` 같은 번호를 잘 못 잡는다. 11-23 실측에서 이슈 본문이 색인돼
있는데도 최고 유사도가 0.51 이라 근거 게이트(0.55)에 막혔다. 적힌 ID 는 연결 규약의 핵심이라
(공통 원칙 「적힌 ID 로만 잇는다」) 유사도에 맡기지 않고 글자 그대로 찾는다.

찾은 항목은 표준 모델의 행으로 표를 만들고, 그 항목의 색인 조각을 출처로 붙인다. 표의 값은
전부 SQL 이 정한다(절대 규칙 1). 조각이 없어도 표가 근거가 된다(ARC-013).
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.db import fetch_all
from app.rag import intents, search, vocab
from app.rag.blocks import Block
from app.rag.search import RetrievedChunk
from app.semantic.models import WidgetRow
from app.standard import repository

ISSUE_KEY = re.compile(r"(?<![A-Za-z0-9])((?:GH|RM)-\d+)(?!\d)", re.IGNORECASE)
REQUIREMENT_CODE = re.compile(r"(?<![A-Za-z0-9.])((?:SFR|SWFR|QUR|SER)\.[A-Z]{3}\.\d{3})(?!\d)")
# 한 질문에서 찾는 ID 수. 여러 개를 나열한 질문은 목록 질문에 가깝다
MAX_REFS = 3
MAX_LINK_ROWS = 30

# 추적 칸 이름은 요구사항 추적 화면과 같다
_KIND_WORD = {
    "DESIGNS": "설계",
    "IMPLEMENTS": "구현",
    "TESTS": "시험",
    "DELIVERS": "산출물",
}
_KIND_ORDER = {"DESIGNS": 0, "IMPLEMENTS": 1, "TESTS": 2, "DELIVERS": 3}
_TYPE_WORD = {
    "ISSUE": "이슈",
    "CODE_CHANGE": "커밋·PR",
    "REPO_DOCUMENT": "설계 문서",
    "WORK_PRODUCT": "산출물",
    "RISK": "리스크",
}


@dataclass
class Found:
    blocks: list[Block] = field(default_factory=list)
    chunks: list[RetrievedChunk] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.blocks)


def refs(question: str) -> tuple[list[str], list[str]]:
    """질문에 적힌 이슈 번호와 요구사항 코드. 적힌 순서대로, 중복 없이."""
    keys = list(dict.fromkeys(m.upper() for m in ISSUE_KEY.findall(question)))
    codes = list(dict.fromkeys(REQUIREMENT_CODE.findall(question)))
    return keys[:MAX_REFS], codes[:MAX_REFS]


def find(cur: Any, question: str, project_ids: list[str], first_slot: int) -> Found:
    """적힌 ID 가 범위 안에 있으면 표와 출처를 만든다. 없으면 빈 Found."""
    keys, codes = refs(question)
    found = Found()
    if not project_ids or not (keys or codes):
        return found
    slot = first_slot
    for issue in _issues(cur, keys, project_ids):
        found.blocks.append(_issue_block(cur, slot, issue, project_ids))
        found.chunks += search.chunks_of(cur, "ISSUE", [str(issue["id"])], project_ids)
        slot += 1
    for req in _requirements(cur, codes, project_ids):
        found.blocks.append(_trace_block(cur, slot, req, project_ids))
        found.chunks += search.chunks_of(cur, "REQUIREMENT", [str(req["id"])], project_ids)
        slot += 1
    found.chunks = search.attach_status(cur, found.chunks)
    return found


def _issues(cur: Any, keys: list[str], project_ids: list[str]) -> list[dict[str, Any]]:
    if not keys:
        return []
    rows = fetch_all(
        cur,
        """
        select i.id, i.issue_key, i.title, i.status, i.severity, i.assignee, i.issue_kind,
               to_char(i.source_created_at at time zone 'Asia/Seoul', 'YYYY-MM-DD') as created,
               to_char(coalesce(i.source_updated_at, i.updated_at) at time zone 'Asia/Seoul',
                       'YYYY-MM-DD') as updated,
               to_char(i.resolved_at at time zone 'Asia/Seoul', 'YYYY-MM-DD') as resolved,
               p.name as project_name
          from issue i
          join project p on p.id = i.project_id
         where i.project_id = any(%s::uuid[]) and upper(i.issue_key) = any(%s)
         order by array_position(%s::text[], upper(i.issue_key)), p.name
        """,
        (project_ids, keys, keys),
    )
    return rows[:MAX_REFS]


def _requirements(cur: Any, codes: list[str], project_ids: list[str]) -> list[dict[str, Any]]:
    if not codes:
        return []
    rows = fetch_all(
        cur,
        """
        select r.id, r.code, r.title, r.status, p.name as project_name
          from requirement r
          join project p on p.id = r.project_id
         where r.project_id = any(%s::uuid[]) and r.code = any(%s)
         order by array_position(%s::text[], r.code::text), p.name
        """,
        (project_ids, codes, codes),
    )
    return rows[:MAX_REFS]


def _issue_block(
    cur: Any, slot: int, issue: dict[str, Any], project_ids: list[str]
) -> Block:
    codes = fetch_all(
        cur,
        """
        select distinct r.code from trace_link t
          join requirement r on r.id = t.to_id
         where t.from_type = 'ISSUE' and t.from_id = %s and t.to_type = 'REQUIREMENT'
           and t.status = 'ACTIVE' and r.code is not null
         order by r.code
        """,
        (issue["id"],),
    )
    values = {
        "key": issue["issue_key"],
        "title": issue["title"],
        "kind": "결함" if issue["issue_kind"] == "DEFECT" else "일반 이슈",
        "status": str(vocab.word(issue["status"])),
        "severity": str(vocab.word(issue["severity"])) if issue["severity"] else "미지정",
        "assignee": issue["assignee"] or "-",
        "created": issue["created"] or "-",
        "updated": issue["updated"] or "-",
        "resolved": issue["resolved"] or "-",
        "requirements": ", ".join(r["code"] for r in codes) or "-",
    }
    columns = [
        ("key", "번호"),
        ("title", "제목"),
        ("kind", "종류"),
        ("status", "상태"),
        ("severity", "심각도"),
        ("assignee", "담당"),
        ("created", "등록일"),
        ("updated", "갱신일"),
        ("resolved", "해결일"),
        ("requirements", "연결 요구사항"),
    ]
    data = intents._table(  # noqa: SLF001 — 표 모양은 일정 질문과 같다
        "entity_issue", "이슈", None, columns, [WidgetRow(values=values)], project_ids
    )
    title = f"이슈 {issue['issue_key']}"
    return Block(
        slot=slot,
        template="DATA_TABLE",
        title=title,
        data=data,
        lines=["- " + " · ".join(f"{label} {values[key]}" for key, label in columns)],
        note=f"{issue['project_name']} 의 {title}. 상태는 수집한 도구의 지금 상태다",
    )


def _trace_block(
    cur: Any, slot: int, req: dict[str, Any], project_ids: list[str]
) -> Block:
    links = [
        lk
        for lk in repository.links_to_requirements(cur, [str(req["id"])])
        if lk["status"] != "SUPERSEDED"
    ]
    labels = repository.entity_labels(cur, {(lk["from_type"], str(lk["from_id"])) for lk in links})
    issue_ids = [str(lk["from_id"]) for lk in links if lk["from_type"] == "ISSUE"]
    issue_status = _issue_status(cur, issue_ids)
    links.sort(key=lambda lk: (_KIND_ORDER.get(lk["link_kind"], 9), lk["from_type"]))

    counts: dict[str, int] = {}
    rows: list[WidgetRow] = []
    for lk in links:
        kind = _KIND_WORD.get(lk["link_kind"], lk["link_kind"])
        counts[kind] = counts.get(kind, 0) + 1
        if len(rows) >= MAX_LINK_ROWS:
            continue
        meta = lk.get("evidence_meta") or {}
        label = labels.get((lk["from_type"], str(lk["from_id"])), ("?", None))[0]
        if lk["from_type"] == "REPO_DOCUMENT":
            label = meta.get("docId") or label
        if lk["status"] == "BROKEN":
            state = "연결 끊김"
        else:
            state = issue_status.get(str(lk["from_id"]), "-")
        rows.append(
            WidgetRow(
                values={
                    "kind": kind,
                    "type": _TYPE_WORD.get(lk["from_type"], lk["from_type"]),
                    "item": label,
                    "state": state,
                }
            )
        )
    columns = [("kind", "구분"), ("type", "종류"), ("item", "항목"), ("state", "상태")]
    data = intents._table(  # noqa: SLF001
        "entity_trace", "추적 연결", None, columns, rows, project_ids,
        truncated=len(links) > len(rows),
    )
    total = len(links)
    status = vocab.word(req["status"])
    title = f"{req['code']} 추적 연결"
    note = (
        f"{req['project_name']} 의 {req['code']} {req['title']} (상태 {status}). "
        "설계는 저장소 설계 문서, 구현은 이슈·커밋, 시험은 시험 커밋이 이 코드를 적은 것이다"
    )
    if total > len(rows):
        note += f". 표에는 연결 {total}건 중 앞 {len(rows)}건"
    # 칸별 건수는 한 줄에 하나씩 둔다. 한 줄에 몰면 수치 검문이 값과 칸 이름을 잘못 짝짓는다.
    # 0건인 칸도 적는다. "설계 연결은 없다" 도 근거가 있는 말이어야 한다
    lines = [f"- 연결 전체 {total}건"] + [
        f"- {word} 연결 {counts.get(word, 0)}건" for word in ("설계", "구현", "시험")
    ]
    if counts.get("산출물"):
        lines.append(f"- 산출물 연결 {counts['산출물']}건")
    lines += [
        "- " + " · ".join(f"{label} {r.values[key]}" for key, label in columns) for r in rows
    ]
    return Block(
        slot=slot, template="DATA_TABLE", title=title, data=data, lines=lines, note=note
    )


def _issue_status(cur: Any, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = fetch_all(
        cur, "select id::text as id, status from issue where id = any(%s::uuid[])", (ids,)
    )
    return {r["id"]: str(vocab.word(r["status"])) for r in rows if r["status"]}
