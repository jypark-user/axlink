"""표준 모델 upsert. 원천 키는 (tool_connection_id, external_id) 다.

부분 유니크 인덱스라 on conflict 에 where 절을 그대로 붙여야 인덱스가 추론된다 —
ORM 을 쓰지 않는 이유 중 하나다(작업 규약 §1).
"""

from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from app.common import errors
from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one
from app.standard import work_product_type

_SOURCE_CONFLICT = """
    on conflict (tool_connection_id, external_id)
      where tool_connection_id is not null and external_id is not null
"""


def find_requirement_by_source(
    cur: Any, connection_id: str, external_id: str
) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        "select id, code, tool_connection_id from requirement "
        "where tool_connection_id = %s and external_id = %s",
        (connection_id, external_id),
    )


def update_requirement_evidence(
    cur: Any, requirement_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> None:
    """예전에 이슈로 만든 요구사항(ARC-030 전)을 그 이슈의 열림·닫힘에 맞춘다.
    근거 상태만 바꾸고 정의(코드·제목·본문·중요도)는 건드리지 않는다. 발주기관이 지정한
    상태가 있으면 지금 상태는 지정대로 둔다(ARC-025)."""
    cur.execute(
        """
        update requirement
           set tool_connection_id = %s, external_id = %s, external_url = %s,
               evidence_status = %s, status = coalesce(decided_status, %s),
               source_created_at = coalesce(source_created_at, %s),
               source_updated_at = %s, updated_at = now()
         where id = %s
        """,
        (
            connection_id, external_id, rec["external_url"], rec["status"], rec["status"],
            rec["source_created_at"], rec["source_updated_at"], requirement_id,
        ),
    )


def upsert_issue(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into issue
          (project_id, issue_key, title, body, status, severity, assignee,
           source_created_at, source_updated_at, resolved_at,
           tool_connection_id, external_id, external_url, source_kind, source_priority)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL', %s)
        {_SOURCE_CONFLICT}
        do update set
           issue_key = excluded.issue_key, title = excluded.title, body = excluded.body,
           status = excluded.status, severity = excluded.severity,
           source_priority = excluded.source_priority,
           assignee = excluded.assignee,
           source_created_at = excluded.source_created_at,
           source_updated_at = excluded.source_updated_at,
           resolved_at = excluded.resolved_at,
           external_url = excluded.external_url, updated_at = now()
        returning id
        """,
        (
            project_id, rec["issue_key"], rec["title"], rec["body"], rec["status"],
            rec["severity"], rec["assignee"], rec["source_created_at"],
            rec["source_updated_at"], rec["resolved_at"],
            connection_id, external_id, rec["external_url"], rec.get("source_priority"),
        ),
    )
    return str(row["id"])


def upsert_milestone(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    """원천 마일스톤 하나(ARC-023). 매 수집마다 목록 전체가 오므로 기한·상태는 늘 원천 값이다."""
    row = fetch_one(
        cur,
        """
        insert into milestone
          (project_id, tool_connection_id, external_id, number, title, due_on, state,
           closed_at, source_url, source_updated_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (tool_connection_id, external_id)
        do update set
           number = excluded.number, title = excluded.title, due_on = excluded.due_on,
           state = excluded.state, closed_at = excluded.closed_at,
           source_url = excluded.source_url, source_updated_at = excluded.source_updated_at,
           updated_at = now()
        returning id
        """,
        (
            project_id, connection_id, external_id, rec["number"], rec["title"], rec["due_on"],
            rec["state"], rec["closed_at"], rec["source_url"], rec["source_updated_at"],
        ),
    )
    return str(row["id"])


def link_issue_milestones(
    cur: Any, connection_id: str, links: list[tuple[str, int | None]]
) -> None:
    """이슈마다 원천이 지정한 마일스톤 번호로 같은 연결의 마일스톤을 잇는다.
    번호가 없으면 비운다."""
    for issue_id, number in links:
        cur.execute(
            """
            update issue
               set milestone_id = (select m.id from milestone m
                                    where m.tool_connection_id = %s and m.number = %s)
             where id = %s
               and milestone_id is distinct from (select m.id from milestone m
                                                   where m.tool_connection_id = %s
                                                     and m.number = %s)
            """,
            (connection_id, number, issue_id, connection_id, number),
        )


def upsert_risk(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into risk
          (project_id, title, body, probability, impact, severity, mitigation, owner,
           status, identified_at, closed_at,
           tool_connection_id, external_id, external_url, source_kind)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
        {_SOURCE_CONFLICT}
        do update set
           title = excluded.title, body = excluded.body, severity = excluded.severity,
           owner = excluded.owner, status = excluded.status,
           closed_at = excluded.closed_at, external_url = excluded.external_url,
           updated_at = now()
        returning id
        """,
        (
            project_id, rec["title"], rec["body"], rec["probability"], rec["impact"],
            rec["severity"], rec["mitigation"], rec["owner"], rec["status"],
            rec["identified_at"], rec["closed_at"],
            connection_id, external_id, rec["external_url"],
        ),
    )
    return str(row["id"])


def upsert_code_change(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into code_change
          (project_id, kind, title, ref_name, state, author, occurred_at,
           tool_connection_id, external_id, external_url, source_kind)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
        {_SOURCE_CONFLICT}
        do update set
           title = excluded.title, ref_name = excluded.ref_name, state = excluded.state,
           author = excluded.author, occurred_at = excluded.occurred_at,
           external_url = excluded.external_url, updated_at = now()
        returning id
        """,
        (
            project_id, rec["kind"], rec["title"], rec["ref_name"], rec["state"],
            rec["author"], rec["occurred_at"],
            connection_id, external_id, rec["external_url"],
        ),
    )
    return str(row["id"])


def upsert_work_product(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str | None:
    """산출물 항목에 이번 버전을 올린다. 앞 버전은 지우지 않고 현행 표시만 내린다.

    산출물 목록은 미리 정의된 항목(ISO/IEC 29110 관리객체)이고 수집은 그 항목을 채운다.
    그런데 WBS 처럼 사업 내내 갱신되는 문서는 항목 하나에 여러 버전이 쌓인다.
    덮어쓰면 "계획을 언제 바꿨는가" 에 답할 수 없다. 그 질문이 진척 감독의 본체다.

    항목 속성(적용 여부·기한·승인)은 버전이 아니라 항목에 속한다.
    새 버전이 앞 버전에서 물려받는다. 승인은 물려받지 않는다. 새 버전은 다시 확인받아야 한다.
    활동 구분은 물려받지 않고 유형에서 정한다(work_product_type.ACTIVITIES).
    """
    current = fetch_one(
        cur,
        """
        select id, version, applicable, due_date
          from work_product
         where project_id = %s and type = %s and is_current
        """,
        (project_id, rec["type"]),
    )
    pm_activity, si_activity = work_product_type.activity_of(rec["type"])

    # 같은 버전이 다시 왔다. 내용이 안 바뀐 것이므로 새 행을 만들지 않는다.
    if current is not None and current["version"] == rec["version"]:
        fetch_one(
            cur,
            """
            update work_product
               set title = %s, file_uri = %s, external_url = %s,
                   source_revision = %s, updated_at = now()
             where id = %s
            returning id
            """,
            (
                rec["title"], rec["file_uri"], rec["external_url"],
                rec.get("source_revision"), current["id"],
            ),
        )
        return str(current["id"])

    if current is not None:
        # 부분 유니크 uq_work_product__current 때문에 먼저 내려야 새 현행이 들어간다.
        cur.execute(
            "update work_product set is_current = false, updated_at = now() where id = %s",
            (current["id"],),
        )

    # 파일을 예전 내용으로 되돌리면 같은 버전(같은 blob)이 다시 온다. 그 판의 행이 이미 있으므로
    # 새로 넣지 않고 되살린다(uq_work_product__version, DEF-V033). 그 판의 제출·승인 이력은 그대로
    # 두고, 항목 속성(적용 여부·기한)은 지금 현행에서 물려받는다.
    revived = fetch_one(
        cur,
        """
        update work_product
           set is_current = true, title = %s, file_uri = %s, external_url = %s,
               source_revision = %s, applicable = %s, due_date = %s, updated_at = now()
         where project_id = %s and type = %s and version = %s and not is_current
        returning id
        """,
        (
            rec["title"], rec["file_uri"], rec["external_url"], rec.get("source_revision"),
            current["applicable"] if current else True,
            current["due_date"] if current else None,
            project_id, rec["type"], rec["version"],
        ),
    )
    if revived is not None:
        return str(revived["id"])

    created = fetch_one(
        cur,
        """
        insert into work_product
          (project_id, type, version, title, status, applicable, due_date,
           pm_activity, si_activity, file_uri, external_url,
           tool_connection_id, external_id, source_revision, source_kind,
           is_current, submitted_at)
        values (%s, %s, %s, %s, 'SUBMITTED', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'TOOL', true, now())
        returning id
        """,
        (
            project_id, rec["type"], rec["version"], rec["title"],
            current["applicable"] if current else True,
            current["due_date"] if current else None,
            pm_activity, si_activity,
            rec["file_uri"], rec["external_url"], connection_id, external_id,
            rec.get("source_revision"),
        ),
    )
    return str(created["id"])


def place_document_work_product(
    cur: Any, project_id: str, document_id: str, user_id: str, rec: dict[str, Any]
) -> str:
    """올린 문서를 산출물 자리의 한 버전으로 올린다. 규칙은 upsert_work_product 와 같다.

    다른 점은 원천이다. 도구 수집은 (연결, 외부 ID) 로 원본을 잇지만 문서는
    document_upload_id 로 잇고 source_kind 는 DOCUMENT 다. 같은 버전 표기가 이미
    있으면 그 행을 고쳐 쓴다. 버전 유일 제약(uq_work_product__version) 때문이기도
    하고, 같은 버전을 다시 올린 것은 내용을 바로잡은 것이지 새 버전이 아니다.
    """
    current = fetch_one(
        cur,
        """
        select id, version
          from work_product
         where project_id = %s and type = %s and is_current
        """,
        (project_id, rec["type"]),
    )
    same_version = fetch_one(
        cur,
        """
        select id, status from work_product
         where project_id = %s and type = %s and version = %s
        """,
        (project_id, rec["type"], rec["version"]),
    )
    if same_version is not None and same_version["status"] == "APPROVED":
        # 승인된 버전을 같은 버전 표기로 고쳐 쓰면 승인이 바뀐 파일에 붙은 것처럼 보인다
        raise errors.ApiError(
            409, "APPROVED_VERSION_LOCKED",
            f"버전 {rec['version']} 은 승인된 버전이라 고쳐 쓸 수 없습니다. 새 버전으로 올리세요.",
        )

    pm_activity, si_activity = work_product_type.activity_of(rec["type"])
    approved = rec["status"] == "APPROVED"

    if current is not None and (same_version is None or same_version["id"] != current["id"]):
        # 부분 유니크 uq_work_product__current 때문에 먼저 내려야 새 현행이 들어간다.
        cur.execute(
            "update work_product set is_current = false, updated_at = now() where id = %s",
            (current["id"],),
        )

    if same_version is not None:
        row = fetch_one(
            cur,
            """
            update work_product
               set title = %s, status = %s, pm_activity = %s, si_activity = %s,
                   document_upload_id = %s, file_uri = %s, authored_at = %s,
                   tool_connection_id = null, external_id = null, external_url = null,
                   source_revision = null, source_kind = 'DOCUMENT', is_current = true,
                   submitted_at = now(),
                   approved_by_user_id = %s, approved_at = case when %s then now() end,
                   reject_reason = null, updated_at = now()
             where id = %s
            returning id
            """,
            (
                rec["title"], rec["status"], pm_activity, si_activity,
                document_id, rec["file_uri"], rec["authored_at"],
                user_id if approved else None, approved, same_version["id"],
            ),
        )
        return str(row["id"])

    row = fetch_one(
        cur,
        """
        insert into work_product
          (project_id, type, version, title, status, pm_activity, si_activity,
           document_upload_id, file_uri, authored_at, source_kind, is_current,
           submitted_at, approved_by_user_id, approved_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'DOCUMENT', true, now(),
                %s, case when %s then now() end)
        returning id
        """,
        (
            project_id, rec["type"], rec["version"], rec["title"], rec["status"],
            pm_activity, si_activity, document_id, rec["file_uri"], rec["authored_at"],
            user_id if approved else None, approved,
        ),
    )
    return str(row["id"])


def work_product_for_review(cur: Any, work_product_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        """
        select id, project_id, type, version, title, status, is_current
          from work_product where id = %s
        """,
        (work_product_id,),
    )


def approve_work_product(cur: Any, work_product_id: str, user_id: str) -> None:
    cur.execute(
        """
        update work_product
           set status = 'APPROVED', approved_by_user_id = %s, approved_at = now(),
               reject_reason = null, updated_at = now()
         where id = %s
        """,
        (user_id, work_product_id),
    )


def reject_work_product(cur: Any, work_product_id: str, reason: str) -> None:
    cur.execute(
        """
        update work_product
           set status = 'REJECTED', approved_by_user_id = null, approved_at = null,
               reject_reason = %s, updated_at = now()
         where id = %s
        """,
        (reason, work_product_id),
    )


def list_work_product_versions(
    cur: Any, project_id: str, product_type: str
) -> list[dict[str, Any]]:
    """한 항목의 버전 이력. 최신이 먼저다."""
    return fetch_all(
        cur,
        """
        select id, version, title, status, is_current, file_uri, external_url,
               source_revision, submitted_at, updated_at
          from work_product
         where project_id = %s and type = %s
         order by is_current desc, submitted_at desc nulls last, updated_at desc
        """,
        (project_id, product_type),
    )


def list_past_work_products(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """현행이 아닌 지난 버전 전부와 마지막 판정(승인·반려) 기록(AC-031-5).

    반려하면 승인자 열이 비워지므로 판정자·일자는 활동 기록에서 읽는다. 최신이 먼저다.
    """
    return fetch_all(
        cur,
        """
        select w.type, w.id, w.version, w.title, w.status, w.submitted_at, w.reject_reason,
               w.approved_at, u.name as approved_by,
               d.actor_label as decided_by, d.occurred_at as decided_at, d.kind as decided_kind
          from work_product w
          left join app_user u on u.id = w.approved_by_user_id
          left join lateral (
                select e.actor_label, e.occurred_at, e.kind
                  from activity_event e
                 where e.project_id = w.project_id
                   and e.target_type = 'WORK_PRODUCT' and e.target_key = w.id::text
                   and e.kind in ('WORK_PRODUCT_APPROVED', 'WORK_PRODUCT_REJECTED')
                 order by e.occurred_at desc
                 limit 1
          ) d on true
         where w.project_id = %s and not w.is_current
         order by w.type, w.submitted_at desc nulls last, w.created_at desc
        """,
        (project_id,),
    )


def current_work_product(
    cur: Any, project_id: str, product_type: str
) -> dict[str, Any] | None:
    """현행 산출물 한 건. 진척 산정이 WBS 파일을 찾을 때 쓴다."""
    return fetch_one(
        cur,
        """
        select id, type, version, title, status, file_uri, source_revision, external_url,
               updated_at, document_upload_id, source_kind
          from work_product
         where project_id = %s and type = %s and is_current
        """,
        (project_id, product_type),
    )


def work_product_row(cur: Any, work_product_id: str) -> dict[str, Any] | None:
    """산출물 한 건(현행 여부 무관). 이전 기준선을 보일 때 그 판을 찾는다."""
    return fetch_one(
        cur,
        """
        select id, type, version, title, status, file_uri, source_revision, external_url,
               updated_at
          from work_product
         where id = %s
        """,
        (work_product_id,),
    )


def document_stored_path(cur: Any, document_id: str) -> str | None:
    """업로드 문서가 보관된 경로(문서 루트 기준 상대 경로)."""
    row = fetch_one(
        cur, "select stored_path from document_upload where id = %s", (document_id,)
    )
    return row["stored_path"] if row else None


# --- 조회 ---------------------------------------------------------------

_REQUIREMENT_COLUMNS = """
    r.id, r.project_id, r.code, r.title, r.priority, r.status, r.assignee,
    r.tool_connection_id, r.external_id, r.external_url, r.source_kind, r.updated_at,
    coalesce(r.evidence_status, r.status) as evidence_status,
    r.decided_status, r.decided_reason, r.decided_at, du.name as decided_by_name,
    r.baseline_id,
    c.tool as tool_name, c.name as connection_name, c.target_resource,
    {source_state} as source_state,
    exists (
      select 1 from trace_link tl
       where tl.to_type = 'REQUIREMENT' and tl.to_id = r.id
         and tl.link_kind = 'TESTS' and tl.status = 'ACTIVE'
    ) as trace_complete
"""
# 출처 이슈 상태는 수집한 원본 기록에서 읽는다. 내부 상태(IMPLEMENTED 등)에서 역산하지 않는다.
# 지금 요구사항을 만드는 원천은 GitHub 뿐이라 GitHub 의 state 만 읽는다. 다른 도구는 UNKNOWN
_SOURCE_STATE = """
    case
      when r.tool_connection_id is null then 'NONE'
      when c.tool = 'GITHUB' and ra.payload_jsonb ->> 'state' = 'open' then 'OPEN'
      when c.tool = 'GITHUB' and ra.payload_jsonb ->> 'state' = 'closed' then 'CLOSED'
      else 'UNKNOWN'
    end
"""
_REQUIREMENT_COLUMNS = _REQUIREMENT_COLUMNS.replace("{source_state}", _SOURCE_STATE.strip())
_REQUIREMENT_FROM = """
    from requirement r
    left join tool_connection c on c.id = r.tool_connection_id
    left join raw_artifact ra
      on ra.tool_connection_id = r.tool_connection_id and ra.external_id = r.external_id
    left join app_user du on du.id = r.decided_by_user_id
"""

VERIFIED_STATUSES = ("VERIFIED", "ACCEPTED")
REQUIREMENT_STATUSES = ("DEFINED", "DESIGNED", "IMPLEMENTED", "VERIFIED", "ACCEPTED", "REJECTED")


@dataclass(frozen=True)
class RequirementFilter:
    """요구사항 목록 조건. 요약 카드를 누르면 이 중 하나가 걸린다. 비어 있으면 사업 전체다."""

    q: str | None = None
    status: str | None = None
    verified: bool | None = None
    source_state: str | None = None  # OPEN | CLOSED | UNKNOWN | NONE
    connection_id: str | None = None


def _search(q: str | None) -> tuple[str, list[Any]]:
    """코드·제목 어느 쪽으로 찾아도 걸리게 한다.

    조건을 SQL 안에서 "%s is null" 로 처리하면 파라미터 타입을 못 정해 실패한다.
    없을 때는 조건 자체를 빼는 편이 낫다.
    """
    if not q or not q.strip():
        return "", []
    like = f"%{q.strip()}%"
    return " and (r.code ilike %s or r.title ilike %s)", [like, like]


def _requirement_where(f: RequirementFilter) -> tuple[str, list[Any]]:
    where, params = _search(f.q)
    if f.status:
        where += " and r.status = %s"
        params.append(f.status)
    if f.verified is not None:
        where += f" and r.status {'' if f.verified else 'not '}in ('VERIFIED', 'ACCEPTED')"
    if f.source_state:
        where += f" and ({_SOURCE_STATE}) = %s"
        params.append(f.source_state)
    if f.connection_id:
        where += " and r.tool_connection_id = %s"
        params.append(f.connection_id)
    return where, params


def count_requirements(cur: Any, project_id: str, f: RequirementFilter) -> int:
    where, params = _requirement_where(f)
    row = fetch_one(
        cur,
        f"select count(*) as n {_REQUIREMENT_FROM} where r.project_id = %s {where}",
        (project_id, *params),
    )
    return int(row["n"]) if row else 0


def requirement_summary(cur: Any, project_id: str) -> dict[str, Any]:
    """요구사항 화면 요약. 목록과 같은 FROM·같은 사업 조건이고 쪽과 상관없다."""
    totals = fetch_one(
        cur,
        f"""
        select count(*) as total,
               count(*) filter (where r.status in ('VERIFIED', 'ACCEPTED')) as verified,
               count(*) filter (where r.decided_status is not null) as decided,
               -- mapping.requirement_status_basis 와 같은 규칙. GitHub 닫힘이 만든 IMPLEMENTED
               count(*) filter (where r.status = 'IMPLEMENTED' and c.tool = 'GITHUB')
                 as implemented_from_source_closed
          {_REQUIREMENT_FROM}
         where r.project_id = %s
        """,
        (project_id,),
    )
    by_status = fetch_all(
        cur,
        "select status, count(*) as n from requirement where project_id = %s group by status",
        (project_id,),
    )
    sources = fetch_all(
        cur,
        f"""
        select r.tool_connection_id as connection_id, c.tool, c.name, c.target_resource,
               count(*) as total,
               count(*) filter (where ({_SOURCE_STATE}) = 'OPEN') as open,
               count(*) filter (where ({_SOURCE_STATE}) = 'CLOSED') as closed,
               count(*) filter (where ({_SOURCE_STATE}) = 'UNKNOWN') as unknown
          {_REQUIREMENT_FROM}
         where r.project_id = %s
         group by r.tool_connection_id, c.tool, c.name, c.target_resource
         order by r.tool_connection_id is null, c.tool, c.name
        """,
        (project_id,),
    )
    return {
        "total": int(totals["total"]),
        "verified": int(totals["verified"]),
        "decided": int(totals["decided"]),
        "implemented_from_source_closed": int(totals["implemented_from_source_closed"]),
        "by_status": {r["status"]: int(r["n"]) for r in by_status},
        "sources": sources,
    }


def search_requirements(
    cur: Any, project_id: str, f: RequirementFilter, page: PageQuery
) -> list[dict[str, Any]]:
    where, params = _requirement_where(f)
    return fetch_all(
        cur,
        f"""
        select {_REQUIREMENT_COLUMNS} {_REQUIREMENT_FROM}
         where r.project_id = %s {where}
         order by r.code nulls last, r.created_at, r.id
         limit %s offset %s
        """,
        (project_id, *params, page.size, page.offset),
    )


def create_checklist(cur: Any, project_id: str) -> int:
    """사업의 산출물 목록 22개 항목을 만든다. 이미 있는 유형은 건드리지 않는다.

    사업 생성 때 부른다. 수집이 먼저 닿아 항목을 즉석에서 만들면 활동 구분이 기본값으로
    들어가므로, 목록이 수집보다 먼저 있어야 한다(ARC-005).
    """
    created = 0
    for product_type, (pm, si) in work_product_type.ACTIVITIES.items():
        cur.execute(
            """
            insert into work_product (project_id, type, pm_activity, si_activity)
            select %s, %s, %s, %s
             where not exists (
               select 1 from work_product where project_id = %s and type = %s
             )
            """,
            (project_id, product_type, pm, si, project_id, product_type),
        )
        created += cur.rowcount
    return created


_ISSUE_COLUMNS = """
    i.id, i.project_id, i.issue_key, i.title, i.status, i.severity, i.assignee,
    i.resolved_at, i.source_updated_at, i.updated_at, i.source_priority,
    i.tool_connection_id, i.external_id, i.external_url, i.source_kind,
    c.tool as tool_name, c.name as connection_name, c.target_resource,
    m.title as milestone_title, m.due_on as milestone_due_on, m.state as milestone_state,
    m.source_url as milestone_url,
    r.payload_jsonb as raw_payload
"""
_ISSUE_FROM = """
    from issue i
    left join tool_connection c on c.id = i.tool_connection_id
    left join milestone m on m.id = i.milestone_id
    left join raw_artifact r
           on r.tool_connection_id = i.tool_connection_id and r.external_id = i.external_id
"""


def _issue_filter(
    q: str | None, status: str | None, connection_id: str | None = None
) -> tuple[str, list[Any]]:
    where, params = "", []
    if q and q.strip():
        like = f"%{q.strip()}%"
        where += " and (i.issue_key ilike %s or i.title ilike %s)"
        params += [like, like]
    if status:
        where += " and i.status = %s"
        params.append(status)
    if connection_id:
        # 사업 조건(i.project_id)과 같이 건다. 다른 사업의 연결 id 를 넣어도 0건이다
        where += " and i.tool_connection_id = %s"
        params.append(connection_id)
    return where, params


def count_issues(
    cur: Any, project_id: str, q: str | None, status: str | None,
    connection_id: str | None = None,
) -> int:
    where, params = _issue_filter(q, status, connection_id)
    row = fetch_one(
        cur,
        f"select count(*) as n from issue i where i.project_id = %s {where}",
        (project_id, *params),
    )
    return int(row["n"]) if row else 0


# 이슈 화면 "심각·높음" 카드. ck_issue__severity 의 위 세 단계다
HEAVY_SEVERITIES = ("BLOCKER", "CRITICAL", "MAJOR")


def issue_summary(
    cur: Any, project_id: str, connection_id: str | None = None
) -> dict[str, int]:
    """이슈 화면 카드 숫자. 목록과 같은 테이블·같은 사업 조건이고 페이지와 무관하다."""
    row = fetch_one(
        cur,
        """
        select count(*) as total,
               count(*) filter (where status in ('OPEN', 'IN_PROGRESS')) as open,
               count(*) filter (where status in ('RESOLVED', 'CLOSED')) as closed,
               count(*) filter (where status in ('OPEN', 'IN_PROGRESS')
                                  and severity = any(%s)) as heavy_open,
               count(*) filter (where status in ('OPEN', 'IN_PROGRESS')
                                  and nullif(btrim(assignee), '') is null) as unassigned_open,
               count(*) filter (where status in ('OPEN', 'IN_PROGRESS')
                                  and severity is null) as unspecified_open
          from issue
         where project_id = %s
           and (%s::uuid is null or tool_connection_id = %s::uuid)
        """,
        (list(HEAVY_SEVERITIES), project_id, connection_id, connection_id),
    )
    keys = ("total", "open", "closed", "heavy_open", "unassigned_open", "unspecified_open")
    return {k: int(row[k]) for k in keys}


def issue_sources(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """이슈 화면의 연결 고르기. 사업에 붙은 연결과 연결별 이슈 수다.

    이슈가 없는 연결도 낸다. 고를 수 있어야 "이 연결에서는 0건" 을 확인한다.
    도구에서 오지 않은 이슈(업로드·수기)는 connection_id 가 비어 한 줄로 묶는다.
    """
    return fetch_all(
        cur,
        """
        select c.id as connection_id, c.tool, c.name, c.target_resource,
               count(i.id) as n
          from tool_connection c
          left join issue i on i.tool_connection_id = c.id and i.project_id = c.project_id
         where c.project_id = %s
         group by c.id
        union all
        select null, null, null, null, count(*)
          from issue
         where project_id = %s and tool_connection_id is null
        having count(*) > 0
         order by 2 nulls last, 3
        """,
        (project_id, project_id),
    )


def search_issues(
    cur: Any, project_id: str, q: str | None, status: str | None, page: PageQuery,
    connection_id: str | None = None,
) -> list[dict[str, Any]]:
    """열린 것이 위로, 그 안에서는 원천에서 최근 움직인 순서다. 감독이 볼 순서가 그렇다.

    끝의 id 는 동점 정리다. 한 번에 승격된 행은 시각이 같아서, 이게 없으면 쪽을 넘길 때
    같은 행이 두 번 나오고 어떤 행은 한 번도 안 나온다.
    """
    where, params = _issue_filter(q, status, connection_id)
    return fetch_all(
        cur,
        f"""
        select {_ISSUE_COLUMNS} {_ISSUE_FROM}
         where i.project_id = %s {where}
         order by (i.status in ('RESOLVED', 'CLOSED')), i.source_updated_at desc nulls last,
                  i.updated_at desc, i.id
         limit %s offset %s
        """,
        (project_id, *params, page.size, page.offset),
    )


def list_work_products(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """현행 산출물 22종. 아직 안 낸 것도 항목으로 나와야 제출 현황이 성립한다."""
    return fetch_all(
        cur,
        """
        select w.id, w.project_id, w.type, w.version, w.title, w.status,
               w.pm_activity, w.si_activity, w.applicable, w.due_date,
               w.file_uri, w.external_url, w.approved_at, w.updated_at,
               u.name as approved_by
          from work_product w
          left join app_user u on u.id = w.approved_by_user_id
         where w.project_id = %s and w.is_current
         order by w.pm_activity nulls last, w.si_activity nulls last, w.type
        """,
        (project_id,),
    )


# --- 추적관계 -------------------------------------------------------------

_ENTITY_TABLE = {
    "REQUIREMENT": "requirement",
    "ISSUE": "issue",
    "RISK": "risk",
    "CODE_CHANGE": "code_change",
    "WORK_PRODUCT": "work_product",
}


def requirement_codes(cur: Any, project_id: str) -> dict[str, str]:
    """{코드: id}. 코드 없는 요구사항은 본문에서 가리킬 방법이 없으니 뺀다."""
    rows = fetch_all(
        cur,
        "select id, code from requirement where project_id = %s and code is not null",
        (project_id,),
    )
    return {r["code"]: str(r["id"]) for r in rows}


def tool_entity_index(cur: Any, project_id: str) -> dict[tuple[str, str], tuple[str, str]]:
    """{(연결 id, 외부 id): (엔터티 유형, id)}. GH-n / RM-n 참조를 표준 모델로 푸는 표다."""
    rows = fetch_all(
        cur,
        """
        select 'REQUIREMENT' as entity_type, id, tool_connection_id, external_id
          from requirement where project_id = %s and tool_connection_id is not null
        union all
        select 'ISSUE', id, tool_connection_id, external_id
          from issue where project_id = %s and tool_connection_id is not null
        union all
        select 'RISK', id, tool_connection_id, external_id
          from risk where project_id = %s and tool_connection_id is not null
        """,
        (project_id, project_id, project_id),
    )
    return {
        (str(r["tool_connection_id"]), r["external_id"]): (r["entity_type"], str(r["id"]))
        for r in rows
    }


def current_work_product_paths(cur: Any, project_id: str) -> dict[str, tuple[str, str]]:
    """{파일 경로: (id, 유형)}. 현행 버전만 잇는다."""
    rows = fetch_all(
        cur,
        """
        select id, type, file_uri from work_product
         where project_id = %s and is_current and file_uri is not null
        """,
        (project_id,),
    )
    return {r["file_uri"]: (str(r["id"]), r["type"]) for r in rows}


def project_connections(cur: Any, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        "select id, tool, base_url, mapping_rules_json from tool_connection "
        "where project_id = %s order by created_at",
        (project_id,),
    )


def raw_artifacts_with_entities(cur: Any, connection_id: str) -> list[dict[str, Any]]:
    """원본과 그 원본이 승격된 표준 엔터티를 나란히 놓는다.

    커밋 본문·이슈 본문·Redmine 커스텀 필드는 표준 모델에 없고 원본에만 있다.
    근거는 원본에서 읽고, 링크의 양 끝은 표준 모델의 id 로 적는다.
    """
    return fetch_all(
        cur,
        """
        select ra.id as raw_id, ra.external_id, ra.object_kind, ra.payload_jsonb,
               r.id as requirement_id, i.id as issue_id, k.id as risk_id,
               c.id as code_change_id,
               coalesce(r.external_url, i.external_url, k.external_url, c.external_url)
                 as external_url
          from raw_artifact ra
          left join requirement r
            on r.tool_connection_id = ra.tool_connection_id and r.external_id = ra.external_id
          left join issue i
            on i.tool_connection_id = ra.tool_connection_id and i.external_id = ra.external_id
          left join risk k
            on k.tool_connection_id = ra.tool_connection_id and k.external_id = ra.external_id
          left join code_change c
            on c.tool_connection_id = ra.tool_connection_id and c.external_id = ra.external_id
         where ra.tool_connection_id = %s
         order by ra.object_kind, ra.external_id
        """,
        (connection_id,),
    )


def upsert_auto_trace_link(
    cur: Any, project_id: str, from_type: str, from_id: str, to_type: str, to_id: str,
    link_kind: str, evidence_kind: str, evidence_text: str, evidence_url: str | None,
    evidence_meta: dict[str, Any] | None = None,
) -> str | None:
    """같은 변이 있으면 근거만 갱신하고 살린다. 사람이 만든 링크는 건드리지 않는다."""
    row = fetch_one(
        cur,
        """
        insert into trace_link
          (project_id, from_type, from_id, to_type, to_id, link_kind,
           origin, status, evidence_kind, evidence_text, evidence_url, evidence_meta)
        values (%s, %s, %s, %s, %s, %s, 'AUTO', 'ACTIVE', %s, %s, %s, %s)
        on conflict on constraint uq_trace_link__edge do update set
           status = 'ACTIVE',
           status_reason = case when trace_link.status = 'ACTIVE'
                                then trace_link.status_reason end,
           status_changed_at = case when trace_link.status = 'ACTIVE'
                                    then trace_link.status_changed_at else now() end,
           superseded_by = null,
           evidence_kind = excluded.evidence_kind,
           evidence_text = excluded.evidence_text,
           evidence_url = excluded.evidence_url,
           evidence_meta = excluded.evidence_meta,
           updated_at = now()
         where trace_link.origin = 'AUTO'
        returning id
        """,
        (
            project_id, from_type, from_id, to_type, to_id, link_kind,
            evidence_kind, evidence_text, evidence_url,
            Jsonb(evidence_meta) if evidence_meta is not None else None,
        ),
    )
    return str(row["id"]) if row else None


def replace_unresolved_refs(
    cur: Any, project_id: str,
    refs: dict[tuple[str, str, str], tuple[str, str | None]],
) -> None:
    """사업에 없는 요구사항 코드를 가리킨 근거. 링크 생성 때마다 사업 단위로 다시 쓴다."""
    cur.execute("delete from requirement_unresolved_ref where project_id = %s", (project_id,))
    for (code, source_type, source_id), (text, url) in refs.items():
        cur.execute(
            """
            insert into requirement_unresolved_ref
              (project_id, code, source_type, source_id, evidence_text, evidence_url)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (project_id, code, source_type, source_id, text, url),
        )


def list_unresolved_refs(cur: Any, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select code, source_type, source_id, evidence_text, evidence_url
          from requirement_unresolved_ref
         where project_id = %s
         order by code, source_type, created_at
        """,
        (project_id,),
    )


def close_stale_auto_links(
    cur: Any, project_id: str, keep_ids: list[str],
    replaced: dict[tuple[str, str, str, str], list[tuple[str, str]]],
    excluded: dict[tuple[str, str, str, str], str],
    deleted_docs: set[str],
    rerouted: dict[tuple[str, str, str, str], str | None] | None = None,
) -> tuple[int, int]:
    """이번에 다시 확인되지 않은 자동 링크를 닫는다. (끊김 수, 대체·제외 수).

    같은 출발·도착에 다른 관계가 새로 생겼으면 대체, 분류 규칙이 뺐으면 제외(둘 다 SUPERSEDED),
    같은 GH-n·RM-n 참조가 이번에 다른 연결의 대상으로 풀렸거나 대상을 정하지 못했으면 연결 해석
    정정(SUPERSEDED, ARC-027), 그 밖은 원천 근거가 사라진 끊김(BROKEN)이다. 지우지 않는다.
    옛 링크의 관계·근거·만든 시각은 그대로 남는다(ARC-024 2-5). 수동 링크는 대상이 아니다.
    """
    rows = fetch_all(
        cur,
        """
        select tl.id, tl.from_type, tl.from_id, tl.to_type, tl.to_id, tl.link_kind,
               coalesce(ti.tool, tr.tool, tk.tool) as to_tool,
               coalesce(i.external_id, r.external_id, k.external_id) as to_external_id
          from trace_link tl
          left join issue i on tl.to_type = 'ISSUE' and i.id = tl.to_id
          left join tool_connection ti on ti.id = i.tool_connection_id
          left join requirement r on tl.to_type = 'REQUIREMENT' and r.id = tl.to_id
          left join tool_connection tr on tr.id = r.tool_connection_id
          left join risk k on tl.to_type = 'RISK' and k.id = tl.to_id
          left join tool_connection tk on tk.id = k.tool_connection_id
         where tl.project_id = %s and tl.origin = 'AUTO' and tl.status = 'ACTIVE'
           and not (tl.id = any(%s::uuid[]))
        """,
        (project_id, keep_ids),
    )
    broken = superseded = 0
    for r in rows:
        key = (r["from_type"], str(r["from_id"]), r["to_type"], str(r["to_id"]))
        ref = _tool_ref(r["to_tool"], r["to_external_id"])
        ref_key = (r["from_type"], str(r["from_id"]), *ref) if ref else None
        if key in replaced:
            new_kinds = ", ".join(sorted({k for _, k in replaced[key]}))
            status, by = "SUPERSEDED", replaced[key][0][0]
            reason = f"분류 정정으로 대체: {r['link_kind']} → {new_kinds}"
        elif key in excluded:
            status, by, reason = "SUPERSEDED", None, f"분류 정정으로 제외: {excluded[key]}"
        elif ref_key is not None and rerouted and ref_key in rerouted:
            status, by = "SUPERSEDED", rerouted[ref_key]
            label = f"{ref[0]}-{ref[1]}"
            reason = (
                f"연결 해석 정정으로 대체: {label} 을 다른 연결의 같은 번호에 이었음"
                if by
                else f"연결 해석 정정으로 제외: {label} 의 도구 연결이 여럿이라 대상을 정할 수 없음"
            )
        elif r["from_type"] == "REPO_DOCUMENT" and str(r["from_id"]) in deleted_docs:
            status, by, reason = "BROKEN", None, "원천 문서가 저장소에서 삭제됨"
        else:
            status, by, reason = "BROKEN", None, "원천 근거가 다시 확인되지 않음"
        cur.execute(
            """
            update trace_link
               set status = %s, status_reason = %s, superseded_by = %s,
                   status_changed_at = now(), updated_at = now()
             where id = %s
            """,
            (status, reason, by, r["id"]),
        )
        if status == "BROKEN":
            broken += 1
        else:
            superseded += 1
    return broken, superseded


_REF_PREFIX = {"GITHUB": "GH", "REDMINE": "RM"}


def _tool_ref(tool: str | None, external_id: str | None) -> tuple[str, str] | None:
    """링크 도착점을 GH-n·RM-n 참조로 되돌린다. 이슈 번호가 아니면 None."""
    prefix = _REF_PREFIX.get(tool or "")
    if prefix is None or not external_id:
        return None
    if prefix == "GH":
        kind, _, number = external_id.partition(":")
        return (prefix, number) if kind == "issue" else None
    return (prefix, external_id) if external_id.isdigit() else None


def break_stale_auto_links(cur: Any, project_id: str, keep_ids: list[str]) -> int:
    """이전 이름. 대체·제외 판단 없이 모두 끊김으로 닫는다."""
    return close_stale_auto_links(cur, project_id, keep_ids, {}, {}, set())[0]


_LINK_COLUMNS = """
    tl.id, tl.project_id, tl.from_type, tl.from_id, tl.to_type, tl.to_id, tl.link_kind,
    tl.origin, tl.status, tl.evidence_kind, tl.evidence_text, tl.evidence_url, tl.created_at,
    tl.evidence_meta, tl.status_reason, tl.status_changed_at, tl.superseded_by
"""


def links_to_requirements(cur: Any, requirement_ids: list[str]) -> list[dict[str, Any]]:
    if not requirement_ids:
        return []
    return fetch_all(
        cur,
        f"""
        select {_LINK_COLUMNS} from trace_link tl
         where tl.to_type = 'REQUIREMENT' and tl.to_id = any(%s::uuid[])
         order by tl.link_kind, tl.created_at
        """,
        (requirement_ids,),
    )


def links_touching(cur: Any, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    """한 엔터티가 출발점이든 도착점이든 걸려 있는 링크 전부."""
    return fetch_all(
        cur,
        f"""
        select {_LINK_COLUMNS} from trace_link tl
         where (tl.from_type = %s and tl.from_id = %s) or (tl.to_type = %s and tl.to_id = %s)
         order by tl.link_kind, tl.created_at
        """,
        (entity_type, entity_id, entity_type, entity_id),
    )


def entity_labels(
    cur: Any, refs: set[tuple[str, str]]
) -> dict[tuple[str, str], tuple[str, str | None]]:
    """{(유형, id): (표시 이름, 원문 링크)}. 화면 셀과 상세 목록이 같이 쓴다."""
    out: dict[tuple[str, str], tuple[str, str | None]] = {}
    by_type: dict[str, list[str]] = {}
    for entity_type, entity_id in refs:
        by_type.setdefault(entity_type, []).append(entity_id)

    label_sql = {
        "REQUIREMENT": "coalesce(code, title)",
        "RISK": "title",
        "CODE_CHANGE": (
            "case when kind = 'COMMIT' then left(ref_name, 7) || ' ' || title else title end"
        ),
        "WORK_PRODUCT": "coalesce(title, type)",
    }
    for entity_type, ids in by_type.items():
        if entity_type == "REPO_DOCUMENT":
            # 저장소 설계 문서는 원본이 곧 출발점이다. 표시 이름은 경로, 링크는 그 커밋의 파일
            rows = fetch_all(
                cur,
                "select id, payload_jsonb->>'path' as label, payload_jsonb->>'html_url' as url "
                "from raw_artifact where id = any(%s::uuid[])",
                (ids,),
            )
            for r in rows:
                out[(entity_type, str(r["id"]))] = (r["label"] or "?", r["url"])
            continue
        if entity_type == "ISSUE":
            # 같은 도구의 연결이 사업에 둘 이상이면 GH-5 가 둘일 수 있다. 그때만 연결 이름을 붙인다
            rows = fetch_all(
                cur,
                """
                select i.id, i.external_url,
                       coalesce(i.issue_key, i.title)
                       || case when exists (
                            select 1 from tool_connection o
                             where o.project_id = c.project_id and o.tool = c.tool
                               and o.id <> c.id
                          ) then ' · ' || c.name else '' end as label
                  from issue i
                  left join tool_connection c on c.id = i.tool_connection_id
                 where i.id = any(%s::uuid[])
                """,
                (ids,),
            )
            for r in rows:
                out[(entity_type, str(r["id"]))] = (r["label"], r["external_url"])
            continue
        table = _ENTITY_TABLE.get(entity_type)
        if table is None:
            continue
        rows = fetch_all(
            cur,
            f"select id, {label_sql[entity_type]} as label, external_url from {table} "
            f"where id = any(%s::uuid[])",
            (ids,),
        )
        for r in rows:
            out[(entity_type, str(r["id"]))] = (r["label"], r["external_url"])
    return out


def set_requirement_decision(
    cur: Any, requirement_id: str, status: str, reason: str, user_id: str
) -> None:
    """발주기관 지정. 지금 상태도 지정 상태로 맞춘다(ck_requirement__decided_effective)."""
    cur.execute(
        """
        update requirement
           set decided_status = %s, decided_reason = %s, decided_by_user_id = %s,
               decided_at = now(), status = %s, updated_at = now()
         where id = %s
        """,
        (status, reason, user_id, status, requirement_id),
    )


def clear_requirement_decision(cur: Any, requirement_id: str) -> None:
    """지정을 거두고 근거 상태로 돌아간다."""
    cur.execute(
        """
        update requirement
           set decided_status = null, decided_reason = null, decided_by_user_id = null,
               decided_at = null, status = coalesce(evidence_status, status), updated_at = now()
         where id = %s
        """,
        (requirement_id,),
    )


def insert_entity_history(
    cur: Any, *, entity_type: str, entity_id: str, project_id: str, field: str,
    from_value: str | None, to_value: str | None, actor: str,
) -> None:
    cur.execute(
        """
        insert into entity_history
            (entity_type, entity_id, project_id, field, from_value, to_value, actor)
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        (entity_type, entity_id, project_id, field, from_value, to_value, actor[:120]),
    )


def get_requirement(cur: Any, project_id: str, requirement_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        f"""
        select {_REQUIREMENT_COLUMNS}, r.body {_REQUIREMENT_FROM}
         where r.project_id = %s and r.id = %s
        """,
        (project_id, requirement_id),
    )


def requirement_baseline_source(cur: Any, requirement_id: str) -> dict[str, Any] | None:
    """요구사항이 든 확정 명세서와 그 항목의 원문 위치. 확정되지 않은 판본은 내보내지 않는다."""
    return fetch_one(
        cur,
        """
        select b.id as baseline_id, b.version, b.status, b.confirmed_at,
               fu.name as confirmed_by_name, b.document_upload_id, b.source_filename,
               b.source_doc_version, i.source_location, i.match_result
          from requirement r
          join requirement_baseline_item i on i.id = r.baseline_item_id
          join requirement_baseline b on b.id = i.baseline_id
          left join app_user fu on fu.id = b.confirmed_by_user_id
         where r.id = %s and b.status = 'CONFIRMED'
        """,
        (requirement_id,),
    )


def entity_history(cur: Any, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        select id, entity_type, entity_id, field, from_value, to_value, actor, changed_at
          from entity_history
         where entity_type = %s and entity_id = %s
         order by changed_at desc
        """,
        (entity_type, entity_id),
    )
