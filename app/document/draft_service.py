"""문서 정형화 초안. 추출한 본문에서 산출물 유형과 요구사항 목록을 뽑아 사람에게 묻는다.

순서가 방어선이다. 규칙(structuring)이 먼저 뽑고, 규칙이 못 정한 유형과 제목만
LLM 에 묻는다. LLM 은 22종 중 하나를 고르거나 제목 한 줄을 쓸 뿐이다. 요구사항
코드·본문·중요도·건수는 전부 문서에 적힌 글자에서 온다(절대 규칙 1).

확정은 사람이 한다. 확정 전까지 표준 모델(work_product·requirement)에는 아무것도
쓰지 않는다. 근거는 docs/20-design/ARC-009-문서-정형화-초안.md.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

from app.ai.llm import llm_port
from app.ai.port import LlmPort
from app.auth.models import AuthPrincipal
from app.common import errors
from app.config import settings
from app.document import draft_repository, repository, structuring
from app.document.access import require_project
from app.document.models import (
    DraftRequirement,
    StructuringConfirmRequest,
    StructuringConfirmResponse,
    StructuringDraftResponse,
)
from app.standard import repository as standard_repo
from app.standard.work_product_type import DISPLAY_NAMES

LLM_CONFIDENCE = 0.5  # 모델이 고른 유형은 규칙이 정한 것보다 낮게 본다. 사람이 다시 본다
_PRIORITIES = ("MUST", "SHOULD", "COULD", "WONT")
# 확정은 문서를 산출물 한 버전으로 등록하는 일이다. 승인은 발주기관이 그 버전을 받아들이는
# 다른 행위라 여기서 하지 않는다(work-products/{id}/approve).
_CONFIRMABLE_STATUSES = ("DRAFT", "SUBMITTED")
_MAX_REJECTED_RAW = 200

_TYPE_SYSTEM = (
    "당신은 소프트웨어 사업 산출물 분류기다. 문서가 아래 22종 중 어느 것인지 코드 하나만 답하라.\n"
    "확실하지 않으면 UNKNOWN 이라고만 답하라. 설명·수치·다른 문장을 쓰지 마라.\n\n"
    + "\n".join(f"{code}: {name}" for code, name in DISPLAY_NAMES.items())
)
_TITLE_SYSTEM = (
    "문서의 제목을 한 줄로만 답하라. 문서에 적힌 제목을 그대로 옮기고, "
    "없으면 UNKNOWN 이라고만 답하라."
)


def propose(
    cur: Any,
    document_id: str,
    filename: str,
    text: str,
    llm_factory: Callable[[], LlmPort],
) -> str:
    """추출이 끝난 문서의 초안을 만들고 문서 상태를 STRUCTURED 로 올린다.

    모델은 필요할 때만 만든다. 규칙이 다 정한 문서는 모델을 부르지 않는다.
    """
    requirements = structuring.extract_requirements(text)
    guess = structuring.classify_type(filename, text, len(requirements))
    title = structuring.guess_title(text)

    draft: dict[str, Any] = {
        "title": title,
        "titleSource": "RULE" if title else None,
        "typeSource": "RULE" if guess.decided else None,
        "version": structuring.guess_version(text),
        "authoredDate": structuring.guess_authored_date(text),
        "confidence": guess.confidence,
        "rejectedTypeRaw": None,
        "scores": guess.scores,
        "requirements": [r.as_dict() for r in requirements],
        "llmError": None,
    }
    product_type = guess.product_type
    model = "rules"
    type_rejected = False

    if not guess.decided or title is None:
        model = settings.llm_model
        try:
            llm = llm_factory()
            if not guess.decided:
                answer = llm.complete(_TYPE_SYSTEM, _llm_user(filename, text))
                product_type = structuring.parse_type_answer(answer.text)
                if product_type is None:
                    type_rejected = True
                    draft["rejectedTypeRaw"] = structuring.strip_think(answer.text)[
                        :_MAX_REJECTED_RAW
                    ]
                else:
                    draft["typeSource"] = "LLM"
                    draft["confidence"] = LLM_CONFIDENCE
                model = answer.model
            if title is None:
                answer = llm.complete(_TITLE_SYSTEM, _llm_user(filename, text))
                draft["title"] = structuring.parse_title_answer(answer.text)
                draft["titleSource"] = "LLM" if draft["title"] else None
                model = answer.model
        except errors.ApiError as exc:
            if not exc.code.startswith("AI_"):
                raise
            # 모델이 죽었다고 초안을 안 만들 이유는 없다. 규칙이 뽑은 것만으로 사람이 고른다.
            draft["llmError"] = exc.message
            repository.note_error(cur, document_id, f"유형 판별을 건너뛰었습니다. {exc.message}")

    draft_id = draft_repository.upsert(cur, document_id, model, draft, product_type, type_rejected)
    draft_repository.set_document_status(cur, document_id, "STRUCTURED")
    return draft_id


def _llm_user(filename: str, text: str) -> str:
    return f"파일명: {filename}\n\n본문 앞부분:\n{structuring.head_for_llm(text)}"


def _load(cur: Any, principal: AuthPrincipal, document_id: str) -> dict[str, Any]:
    row = draft_repository.find_by_document(cur, document_id)
    if row is None:
        raise errors.not_found("정형화 초안", document_id)
    require_project(cur, principal, str(row["project_id"]))
    return row


def _to_response(row: dict[str, Any]) -> StructuringDraftResponse:
    draft = row["draft_json"]
    return StructuringDraftResponse(
        documentId=str(row["document_upload_id"]),
        status=row["status"],
        suggestedType=row["proposed_type"],
        rejectedTypeRaw=draft.get("rejectedTypeRaw"),
        confidence=float(draft.get("confidence") or 0.0),
        title=draft.get("title"),
        version=draft.get("version"),
        authoredDate=draft.get("authoredDate"),
        requirements=[DraftRequirement(**r) for r in draft.get("requirements", [])],
        createdAt=row["created_at"].isoformat(),
    )


def get(cur: Any, principal: AuthPrincipal, document_id: str) -> StructuringDraftResponse:
    return _to_response(_load(cur, principal, document_id))


def _require_proposed(row: dict[str, Any]) -> None:
    if row["status"] != "PROPOSED":
        raise errors.ApiError(
            409, "DRAFT_ALREADY_DECIDED", f"이미 처리된 초안입니다: {row['status']}"
        )


def reject(cur: Any, principal: AuthPrincipal, document_id: str) -> None:
    row = _load(cur, principal, document_id)
    _require_proposed(row)
    draft_repository.mark_rejected(cur, str(row["id"]), principal.user_id)
    draft_repository.set_document_status(cur, document_id, "REJECTED")


def _validate(req: StructuringConfirmRequest) -> dict[str, Any]:
    """확정 값 검사. 스키마 CHECK 에 걸리기 전에 사람이 읽을 말로 돌려준다."""
    if req.type not in DISPLAY_NAMES:
        raise errors.validation_failed(f"산출물 유형이 아닙니다: {req.type}")
    title = req.title.strip()
    version = req.version.strip()
    if not title or len(title) > 500:
        raise errors.validation_failed("제목은 1~500자여야 합니다.")
    if not version or len(version) > 40:
        raise errors.validation_failed("버전은 1~40자여야 합니다.")
    if req.workProductStatus == "APPROVED":
        raise errors.validation_failed(
            "확정은 산출물 등록입니다. 승인은 발주기관이 산출물 화면에서 따로 합니다."
        )
    if req.workProductStatus not in _CONFIRMABLE_STATUSES:
        raise errors.validation_failed(
            "확정 상태는 " + " · ".join(_CONFIRMABLE_STATUSES) + " 중 하나여야 합니다."
        )
    authored_at = None
    if req.authoredDate:
        try:
            authored_at = date.fromisoformat(req.authoredDate)
        except ValueError as exc:
            raise errors.validation_failed(f"작성일 형식이 아닙니다: {req.authoredDate}") from exc

    seen: set[str] = set()
    requirements: list[dict[str, Any]] = []
    for i, r in enumerate(req.requirements, 1):
        code = (r.code or "").strip() or None
        name = r.title.strip()
        if not name or len(name) > 500:
            raise errors.validation_failed(f"요구사항 {i} 의 제목은 1~500자여야 합니다.")
        if code and len(code) > 64:
            raise errors.validation_failed(f"요구사항 {i} 의 코드가 너무 깁니다.")
        if code in seen:
            raise errors.validation_failed(f"요구사항 코드가 겹칩니다: {code}")
        if r.priority not in _PRIORITIES:
            raise errors.validation_failed(f"요구사항 {i} 의 중요도가 아닙니다: {r.priority}")
        if code:
            seen.add(code)
        requirements.append(
            {"code": code, "title": name, "body": r.body.strip() or name, "priority": r.priority}
        )

    return {
        "type": req.type,
        "title": title,
        "version": version,
        "status": req.workProductStatus,
        "authored_at": authored_at,
        "requirements": requirements,
    }


def confirm(
    cur: Any, principal: AuthPrincipal, document_id: str, req: StructuringConfirmRequest
) -> StructuringConfirmResponse:
    """사람이 고친 초안을 산출물 한 버전으로 올린다.

    요구사항은 여기서 만들지 않는다(GH-139). 용역사가 확정한 초안이 곧바로 사업의 요구사항이
    되면 발주기관 확정 전 목록이 확정 요구사항처럼 보이고, 기준선을 확정한 뒤에는 새 파일이
    기준선을 덮는다. 요구사항은 요구사항 기준선(명세서 등록 → 제출 → 발주기관 확정)으로만 들어간다.
    """
    row = _load(cur, principal, document_id)
    _require_proposed(row)
    rec = _validate(req)
    project_id = str(row["project_id"])
    rec["file_uri"] = row["stored_path"]

    work_product_id = standard_repo.place_document_work_product(
        cur, project_id, document_id, principal.user_id, rec
    )

    # 제안한 유형과 다르게 확정했으면 그 사실을 남긴다. 규칙·모델의 오답 기록이다.
    status = "CONFIRMED" if rec["type"] == row["proposed_type"] else "MANUAL_OVERRIDE"
    draft_repository.mark_confirmed(cur, str(row["id"]), principal.user_id, work_product_id, status)
    draft_repository.set_document_status(cur, document_id, "CONFIRMED")

    return StructuringConfirmResponse(
        workProductId=work_product_id,
        createdRequirementIds=[],
        indexedChunkCount=0,
    )


def propose_for_upload(cur: Any, document_id: str, filename: str, text: str) -> None:
    """업로드 흐름에서 부른다. 구현체 선택은 llm_port 한 곳이다."""
    propose(cur, document_id, filename, text, llm_port)
