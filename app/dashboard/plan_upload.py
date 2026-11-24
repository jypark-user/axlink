"""일정(WBS) 화면에서 WBS 파일을 바로 올린다 (11-24 사용자 결정).

저장소가 없는 사업(Redmine 만 쓰는 업체 등)은 WBS 를 넣을 곳이 없었다. 자료 화면의 초안 확정은
11-19 에 화면에서 뺐고(자료는 기타 자료만), 확정 API 만 남아 있었다. 그래서 일정 화면에 창구를
따로 둔다. 올린 파일은 곧바로 사업수행계획서(WBS)의 한 버전이 된다. 초안 확인을 거치지 않는
대신 올리기 전에 WBS 로 읽히는지 먼저 본다. 못 읽는 파일은 받지 않는다.

저장소에서 WBS 를 읽는 사업은 받지 않는다. 그 사업의 원천은 저장소 파일이다
(draft_service.guard_repository_plan 과 같은 규칙).
"""

from datetime import date
from pathlib import Path
from typing import Any

from app.auth import repository as auth_repo
from app.auth.deps import AuthPrincipal
from app.common import clock, errors
from app.dashboard import wbs
from app.dashboard.models import WbsPlanUploadResponse
from app.db import fetch_one
from app.document import draft_service
from app.document import service as document_service
from app.standard import repository as standard_repo

PLAN_TYPE = "PROJECT_PLAN"
# 확정이 곧 제출이다(DEC-14). 초안 확정과 같은 상태로 둔다
_STATUS = "SUBMITTED"


def upload_plan(
    cur: Any,
    principal: AuthPrincipal,
    project_id: str,
    filename: str,
    content: bytes,
    version: str | None,
    today: date | None = None,
) -> WbsPlanUploadResponse:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    if project_id not in allowed:
        raise errors.project_access_denied()
    if Path(filename or "").suffix.lower() != ".xlsx":
        raise errors.validation_failed("WBS 는 엑셀(.xlsx) 파일로 올립니다.")
    if not content:
        raise errors.validation_failed("빈 파일입니다.")
    # 크기·형식 검사는 document_service.upload 가 한다. 여기서는 내용이 WBS 로 읽히는지 먼저 본다.
    # 읽히지 않는 파일이 현행 계획서가 되면 일정 화면이 비어 버린다
    try:
        plan = wbs.parse(content)
    except wbs.WbsParseError as exc:
        raise errors.validation_failed(f"WBS 로 읽을 수 없습니다. {exc}") from exc
    reasons = wbs.unavailable_reasons(plan)
    if not plan.rows:
        raise errors.validation_failed("WBS 로 읽을 수 없습니다. 작업 행이 없습니다.")

    draft_service.guard_repository_plan(cur, project_id, PLAN_TYPE)
    label = (version or "").strip() or (today or clock.today()).isoformat()
    if len(label) > 50:
        raise errors.validation_failed("버전은 50자 이내로 적습니다.")

    doc = document_service.upload(cur, principal, project_id, filename, content)
    stored = fetch_one(
        cur, "select stored_path from document_upload where id = %s", (doc.id,)
    )
    assert stored is not None
    work_product_id = standard_repo.place_document_work_product(
        cur,
        project_id,
        doc.id,
        principal.user_id,
        {
            "type": PLAN_TYPE,
            "title": Path(filename).stem[:500] or "WBS",
            "version": label,
            "status": _STATUS,
            "authored_at": None,
            "file_uri": stored["stored_path"],
        },
    )
    from app.dashboard import service as dashboard_service  # 순환 import 회피

    # 산출물 지정·작업 연결을 새 판에 맞춘다(초안 확정과 같다)
    dashboard_service.sync_product_links(cur, project_id)
    return WbsPlanUploadResponse(
        workProductId=work_product_id,
        documentId=doc.id,
        version=label,
        leafCount=len(plan.rows),
        warnings=[*plan.warnings, *reasons],
    )
