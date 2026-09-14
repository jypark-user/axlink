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
    """산출물 항목에 이번 버전을 올린다. 앞 버전은 지우지 않고 현행 표시만 내린다.

    산출물 목록은 미리 정의된 항목(ISO/IEC 29110 관리객체)이고 수집은 그 항목을 채운다.
    그런데 WBS 처럼 사업 내내 갱신되는 문서는 항목 하나에 여러 버전이 쌓인다.
    덮어쓰면 "계획을 언제 바꿨는가" 에 답할 수 없다. 그 질문이 진척 감독의 본체다.

    항목 속성(적용 여부·기한·활동 구분·승인)은 버전이 아니라 항목에 속한다.
    새 버전이 앞 버전에서 물려받는다. 승인은 물려받지 않는다. 새 버전은 다시 확인받아야 한다.
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


_ISSUE_COLUMNS = """
    i.id, i.project_id, i.issue_key, i.title, i.status, i.severity, i.assignee,
    i.resolved_at, i.source_updated_at, i.updated_at,
    i.tool_connection_id, i.external_id, i.external_url, i.source_kind,
    c.tool as tool_name
"""
_ISSUE_FROM = """
    from issue i
    left join tool_connection c on c.id = i.tool_connection_id
"""


def _issue_filter(q: str | None, status: str | None) -> tuple[str, list[Any]]:
    where, params = "", []
    if q and q.strip():
        like = f"%{q.strip()}%"
        where += " and (i.issue_key ilike %s or i.title ilike %s)"
        params += [like, like]
    if status:
        where += " and i.status = %s"
        params.append(status)
    return where, params


def count_issues(cur: Any, project_id: str, q: str | None, status: str | None) -> int:
    where, params = _issue_filter(q, status)
    row = fetch_one(
        cur,
        f"select count(*) as n from issue i where i.project_id = %s {where}",
        (project_id, *params),
    )
    return int(row["n"]) if row else 0


def search_issues(
    cur: Any, project_id: str, q: str | None, status: str | None, page: PageQuery
) -> list[dict[str, Any]]:
    """열린 것이 위로, 그 안에서는 원천에서 최근 움직인 순서다. 감독이 볼 순서가 그렇다."""
    where, params = _issue_filter(q, status)
    return fetch_all(
        cur,
        f"""
        select {_ISSUE_COLUMNS} {_ISSUE_FROM}
         where i.project_id = %s {where}
         order by (i.status in ('RESOLVED', 'CLOSED')), i.source_updated_at desc nulls last,
                  i.updated_at desc
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
        select ra.external_id, ra.object_kind, ra.payload_jsonb,
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
) -> str | None:
    """같은 변이 있으면 근거만 갱신하고 살린다. 사람이 만든 링크는 건드리지 않는다."""
    row = fetch_one(
        cur,
        """
        insert into trace_link
          (project_id, from_type, from_id, to_type, to_id, link_kind,
           origin, status, evidence_kind, evidence_text, evidence_url)
        values (%s, %s, %s, %s, %s, %s, 'AUTO', 'ACTIVE', %s, %s, %s)
        on conflict on constraint uq_trace_link__edge do update set
           status = 'ACTIVE',
           evidence_kind = excluded.evidence_kind,
           evidence_text = excluded.evidence_text,
           evidence_url = excluded.evidence_url,
           updated_at = now()
         where trace_link.origin = 'AUTO'
        returning id
        """,
        (
            project_id, from_type, from_id, to_type, to_id, link_kind,
            evidence_kind, evidence_text, evidence_url,
        ),
    )
    return str(row["id"]) if row else None


def break_stale_auto_links(cur: Any, project_id: str, keep_ids: list[str]) -> int:
    """이번 생성에서 근거가 다시 확인되지 않은 자동 링크는 끊긴 것으로 표시한다.

    지우지 않는다. 언제 근거가 사라졌는지가 남아야 감독 기록이 된다.
    """
    cur.execute(
        """
        update trace_link
           set status = 'BROKEN', updated_at = now()
         where project_id = %s and origin = 'AUTO' and status = 'ACTIVE'
           and not (id = any(%s::uuid[]))
        """,
        (project_id, keep_ids),
    )
    return cur.rowcount


_LINK_COLUMNS = """
    tl.id, tl.project_id, tl.from_type, tl.from_id, tl.to_type, tl.to_id, tl.link_kind,
    tl.origin, tl.status, tl.evidence_kind, tl.evidence_text, tl.evidence_url, tl.created_at
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
        "ISSUE": "coalesce(issue_key, title)",
        "RISK": "title",
        "CODE_CHANGE": (
            "case when kind = 'COMMIT' then left(ref_name, 7) || ' ' || title else title end"
        ),
        "WORK_PRODUCT": "coalesce(title, type)",
    }
    for entity_type, ids in by_type.items():
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


def get_requirement(cur: Any, project_id: str, requirement_id: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        f"""
        select {_REQUIREMENT_COLUMNS}, r.body {_REQUIREMENT_FROM}
         where r.project_id = %s and r.id = %s
        """,
        (project_id, requirement_id),
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
