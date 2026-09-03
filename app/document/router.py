"""/api — 문서 업로드·목록. 프런트 documents-page.tsx 가 부르는 경로 그대로다.

경로가 /projects/{id}/documents 와 /documents/{id} 두 갈래라 라우터를 하나로 둔다.
"""

from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.document import service
from app.document.models import (
    DocumentChunkResponse,
    DocumentTextResponse,
    DocumentUploadResponse,
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
async def upload_document(
    project_id: str, principal: Principal, file: Annotated[UploadFile, File()]
) -> DocumentUploadResponse:
    content = await file.read()
    with tx() as cur:
        return service.upload(cur, principal, project_id, file.filename or "", content)


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
