"""/api — 문서 업로드·목록. 프런트 documents-page.tsx 가 부르는 경로 그대로다.

경로가 /projects/{id}/documents 와 /documents/{id} 두 갈래라 라우터를 하나로 둔다.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.document import draft_service, service
from app.document.models import (
    DocumentChunkResponse,
    DocumentDetailResponse,
    DocumentTextResponse,
    DocumentUpdateRequest,
    DocumentUploadResponse,
    StructuringConfirmRequest,
    StructuringConfirmResponse,
    StructuringDraftResponse,
)

router = APIRouter(prefix="/api", tags=["documents"])


@router.get(
    "/projects/{project_id}/documents", response_model=PageResponse[DocumentUploadResponse]
)
def list_documents(
    project_id: str,
    principal: Principal,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> PageResponse[DocumentUploadResponse]:
    with tx() as cur:
        return service.list_for_project(
            cur, principal, project_id, PageQuery(page=page, size=size)
        )


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
)
def upload_document(
    project_id: str,
    principal: Principal,
    file: Annotated[UploadFile, File()],
    wbsId: Annotated[str | None, Form()] = None,  # noqa: N803  WBS 항목에 바로 붙여 올릴 때
    # 발주기관 지정 산출물 항목의 제출본으로 올릴 때(UC-033)
    designatedId: Annotated[str | None, Form()] = None,  # noqa: N803
) -> DocumentUploadResponse:
    """접수만 한다. 추출·색인·초안은 작업자가 뒤에서 한다(GH-121). 동기 함수라 FastAPI 가
    스레드에서 돌린다. async 로 두고 안에서 막히는 일을 하면 API 전체가 멈춘다."""
    # 상한까지만 읽는다. 넘는 파일을 통째로 메모리에 올리지 않는다(넘으면 service 가 거절한다)
    content = file.file.read(service.MAX_BYTES + 1)
    with tx() as cur:
        return service.upload(
            cur, principal, project_id, file.filename or "", content, wbs_id=wbsId,
            designated_id=designatedId,
        )


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: str, principal: Principal) -> DocumentDetailResponse:
    """자료 상세. 정보·설정과 추출 결과 링크."""
    with tx() as cur:
        return service.get_detail(cur, principal, document_id)


@router.patch("/documents/{document_id}", response_model=DocumentDetailResponse)
def update_document(
    document_id: str, req: DocumentUpdateRequest, principal: Principal
) -> DocumentDetailResponse:
    """자료 설정: WBS 항목과 29110 유형 태그."""
    with tx() as cur:
        return service.update(cur, principal, document_id, req)


@router.get("/documents/{document_id}/text", response_model=DocumentTextResponse)
def get_document_text(document_id: str, principal: Principal) -> DocumentTextResponse:
    """추출 결과 원문. 파싱이 제대로 됐는지 눈으로 확인하는 용도다."""
    with tx() as cur:
        return service.get_text(cur, principal, document_id)


@router.get("/documents/{document_id}/chunks", response_model=PageResponse[DocumentChunkResponse])
def list_document_chunks(
    document_id: str,
    principal: Principal,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=50, ge=1, le=200),
) -> PageResponse[DocumentChunkResponse]:
    """색인된 본문 조각. 사업 정보 화면이 이어 붙여 원문으로 보여 준다."""
    with tx() as cur:
        return service.list_chunks(cur, principal, document_id, PageQuery(page=page, size=size))


@router.get("/documents/{document_id}/content")
def download_document(document_id: str, principal: Principal) -> FileResponse:
    """올린 원본 그대로. 추출 결과가 원본과 맞는지 대조할 때 쓴다."""
    with tx() as cur:
        stored = service.get_file(cur, principal, document_id)
    # 파일명이 한글이라 filename* (RFC 5987) 로 나가야 브라우저가 안 깨뜨린다.
    return FileResponse(
        stored.path, media_type=stored.content_type, filename=stored.filename
    )


@router.delete("/documents/{document_id}", status_code=204, response_class=Response)
def delete_document(document_id: str, principal: Principal) -> Response:
    with tx() as cur:
        service.delete(cur, principal, document_id)
    return Response(status_code=204)


@router.get("/documents/{document_id}/draft", response_model=StructuringDraftResponse)
def get_structuring_draft(document_id: str, principal: Principal) -> StructuringDraftResponse:
    """문서에서 뽑은 산출물 유형·요구사항 초안. structuring-draft-page.tsx 가 편집 대상으로 연다."""
    with tx() as cur:
        return draft_service.get(cur, principal, document_id)


@router.post(
    "/documents/{document_id}/draft/confirm", response_model=StructuringConfirmResponse
)
def confirm_structuring_draft(
    document_id: str, principal: Principal, req: StructuringConfirmRequest
) -> StructuringConfirmResponse:
    """사람이 고친 초안을 산출물 항목·요구사항으로 올린다."""
    with tx() as cur:
        return draft_service.confirm(cur, principal, document_id, req)


@router.post(
    "/documents/{document_id}/draft/reject", status_code=204, response_class=Response
)
def reject_structuring_draft(document_id: str, principal: Principal) -> Response:
    with tx() as cur:
        draft_service.reject(cur, principal, document_id)
    return Response(status_code=204)
