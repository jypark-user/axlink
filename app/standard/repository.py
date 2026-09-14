"""표준 모델 upsert. 원천 키는 (tool_connection_id, external_id) 다.

부분 유니크 인덱스라 on conflict 에 where 절을 그대로 붙여야 인덱스가 추론된다 —
ORM 을 쓰지 않는 이유 중 하나다(작업 규약 §1).
"""

from typing import Any

from app.common.paging import PageQuery
from app.db import fetch_all, fetch_one

_SOURCE_CONFLICT = """
    on conflict (tool_connection_id, external_id)
      where tool_connection_id is not null and external_id is not null
"""


def upsert_requirement(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into requirement
          (project_id, code, title, body, priority, status, assignee,
           source_created_at, source_updated_at,
           tool_connection_id, external_id, external_url, source_kind)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
        {_SOURCE_CONFLICT}
        do update set
           code = excluded.code, title = excluded.title, body = excluded.body,
           priority = excluded.priority, status = excluded.status,
           assignee = excluded.assignee,
           source_created_at = excluded.source_created_at,
           source_updated_at = excluded.source_updated_at,
           external_url = excluded.external_url, updated_at = now()
        returning id
        """,
        (
            project_id, rec["code"], rec["title"], rec["body"], rec["priority"], rec["status"],
            rec["assignee"], rec["source_created_at"], rec["source_updated_at"],
            connection_id, external_id, rec["external_url"],
        ),
    )
    return str(row["id"])


def upsert_issue(
    cur: Any, project_id: str, connection_id: str, external_id: str, rec: dict[str, Any]
) -> str:
    row = fetch_one(
        cur,
        f"""
        insert into issue
          (project_id, issue_key, title, body, status, severity, assignee,
           source_created_at, source_updated_at, resolved_at,
           tool_connection_id, external_id, external_url, source_kind)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'TOOL')
        {_SOURCE_CONFLICT}
        do update set
           issue_key = excluded.issue_key, title = excluded.title, body = excluded.body,
           status = excluded.status, severity = excluded.severity,
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
            connection_id, external_id, rec["external_url"],
        ),
    )
    return str(row["id"])


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
    """산출물 자리에 이번 버전을 올린다. 앞 버전은 지우지 않고 현행 표시만 내린다.

    산출물 목록은 미리 정의된 자리(ISO/IEC 29110 관리객체)이고 수집은 그 자리를 채운다.
    그런데 WBS 처럼 사업 내내 갱신되는 문서는 자리 하나에 여러 버전이 쌓인다.
    덮어쓰면 "계획을 언제 바꿨는가" 에 답할 수 없다 — 그 질문이 진척 감독의 본체다.

    자리 속성(적용 여부·기한·활동 구분·승인)은 버전이 아니라 자리에 속한다.
    새 버전이 앞 버전에서 물려받는다. 승인은 물려받지 않는다 — 새 버전은 다시 확인받아야 한다.
    """
    current = fetch_one(
        cur,
        """
        select id, version, applicable, due_date, pm_activity, si_activity
          from work_product
         where project_id = %s and type = %s and is_current
        """,
        (project_id, rec["type"]),
    )

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
            (current["pm_activity"] if current else None) or "PM_1",
            current["si_activity"] if current else None,
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
        select id, version, pm_activity, si_activity
          from work_product
         where project_id = %s and type = %s and is_current
        """,
        (project_id, rec["type"]),
    )
    same_version = fetch_one(
        cur,
        "select id from work_product where project_id = %s and type = %s and version = %s",
        (project_id, rec["type"], rec["version"]),
    )

    pm_activity = rec.get("pm_activity") or (current["pm_activity"] if current else None)
    si_activity = rec.get("si_activity") or (current["si_activity"] if current else None)
    if pm_activity is None and si_activity is None:
        pm_activity = "PM_1"
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


def upsert_document_requirement(
    cur: Any, project_id: str, document_id: str, work_product_id: str, rec: dict[str, Any]
) -> str:
    """문서에서 확정한 요구사항. 같은 코드가 이미 있으면 글만 갱신한다.

    도구(GitHub 이슈)에서 온 같은 코드의 요구사항이면 도구 연결은 그대로 둔다.
    문서는 정의를, 이슈는 이행 추적을 맡는 것이라 둘을 한 행으로 합쳐야 추적이 산다.
    코드가 없는 요구사항은 늘 새 행이다. 견줄 열쇠가 없다.
    """
    row = fetch_one(
        cur,
        """
        insert into requirement
          (project_id, code, title, body, priority, status,
           work_product_id, document_upload_id, source_kind)
        values (%s, %s, %s, %s, %s, 'DEFINED', %s, %s, 'DOCUMENT')
        on conflict (project_id, code) where code is not null
        do update set
           title = excluded.title, body = excluded.body, priority = excluded.priority,
           work_product_id = excluded.work_product_id,
           document_upload_id = excluded.document_upload_id,
           source_kind = case when requirement.tool_connection_id is null
                              then 'DOCUMENT' else requirement.source_kind end,
           updated_at = now()
        returning id
        """,
        (
            project_id, rec["code"], rec["title"], rec["body"], rec["priority"],
            work_product_id, document_id,
        ),
    )
    return str(row["id"])


def list_work_product_versions(
    cur: Any, project_id: str, product_type: str
) -> list[dict[str, Any]]:
    """한 자리의 버전 이력. 최신이 먼저다."""
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


def current_work_product(
    cur: Any, project_id: str, product_type: str
) -> dict[str, Any] | None:
    """현행 산출물 한 건. 진척 산정이 WBS 파일을 찾을 때 쓴다."""
    return fetch_one(
        cur,
        """
        select id, type, version, title, status, file_uri, source_revision, updated_at
          from work_product
         where project_id = %s and type = %s and is_current
        """,
        (project_id, product_type),
    )


# --- 조회 ---------------------------------------------------------------

_REQUIREMENT_COLUMNS = """
    r.id, r.project_id, r.code, r.title, r.priority, r.status, r.assignee,
    r.tool_connection_id, r.external_id, r.external_url, r.source_kind, r.updated_at,
    c.tool as tool_name,
    exists (
      select 1 from trace_link tl
       where tl.to_type = 'REQUIREMENT' and tl.to_id = r.id
         and tl.link_kind = 'TESTS' and tl.status = 'ACTIVE'
    ) as trace_complete
"""
_REQUIREMENT_FROM = """
    from requirement r
    left join tool_connection c on c.id = r.tool_connection_id
"""


def _search(q: str | None) -> tuple[str, list[Any]]:
    """코드·제목 어느 쪽으로 찾아도 걸리게 한다.

    조건을 SQL 안에서 "%s is null" 로 처리하면 파라미터 타입을 못 정해 실패한다.
    없을 때는 조건 자체를 빼는 편이 낫다.
    """
    if not q or not q.strip():
        return "", []
    like = f"%{q.strip()}%"
    return " and (r.code ilike %s or r.title ilike %s)", [like, like]


def count_requirements(cur: Any, project_id: str, q: str | None) -> int:
    where, params = _search(q)
    row = fetch_one(
        cur,
        f"select count(*) as n from requirement r where r.project_id = %s {where}",
        (project_id, *params),
    )
    return int(row["n"]) if row else 0



def search_requirements(
    cur: Any, project_id: str, q: str | None, page: PageQuery
) -> list[dict[str, Any]]:
    where, params = _search(q)
    return fetch_all(
        cur,
        f"""
        select {_REQUIREMENT_COLUMNS} {_REQUIREMENT_FROM}
         where r.project_id = %s {where}
         order by r.code nulls last, r.created_at
         limit %s offset %s
        """,
        (project_id, *params, page.size, page.offset),
    )


def list_work_products(cur: Any, project_id: str) -> list[dict[str, Any]]:
    """현행 산출물 22종. 아직 안 낸 것도 자리로 나와야 제출 현황이 성립한다."""
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
