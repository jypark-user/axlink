"""문서 업로드 → 파싱 → 저장.

업로드 시점에 바로 읽는다. PoC 규모라 요청 안에서 동기로 돌린다 — 실측으로 70,650자
HWP 가 1초 안쪽이다. 큐로 뺄 이유가 아직 없다.

파일은 해시 이름으로 저장한다. 사용자가 준 파일명을 경로에 쓰지 않는다 —
경로 조작을 원천에서 막고, 같은 내용을 두 번 저장하지 않는다.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.activity import service as activity
from app.ai.embedding import embedding_port
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.config import settings
from app.dashboard import service as dashboard_service
from app.document import draft_service, extractor, repository
from app.document.access import require_project as _require_project
from app.document.models import (
    DocumentChunkResponse,
    DocumentDetailResponse,
    DocumentTextResponse,
    DocumentUpdateRequest,
    DocumentUploadResponse,
)
from app.rag import indexing
from app.rag import repository as rag_repo
from app.standard import wbs_repository
from app.standard.work_product_type import DISPLAY_NAMES

MAX_BYTES = 50 * 1024 * 1024  # 프런트 features/documents/upload.ts 와 같은 한도


def _to_response(row: dict[str, Any]) -> DocumentUploadResponse:
    return DocumentUploadResponse(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        fileName=row["original_filename"],
        fileSize=row["size_bytes"],
        mimeType=row["content_type"],
        status=row["status"],
        uploadedBy=row["uploaded_by"],
        uploadedAt=row["created_at"].isoformat(),
        extractedCharCount=row["extracted_chars"],
        # 초안이 사람의 판단을 기다리는 동안만 "초안 확인" 이 뜬다.
        draftAvailable=row["draft_status"] == "PROPOSED",
        workProductId=(
            str(row["draft_work_product_id"]) if row["draft_work_product_id"] else None
        ),
        error=row["error"],
    )


def _store(project_id: str, file_hash: str, ext: str, content: bytes) -> str:
    """해시 경로에 저장하고 저장소 기준 상대경로를 돌려준다."""
    relative = Path(project_id) / file_hash[:2] / f"{file_hash}.{ext.lower()}"
    target = Path(settings.document_root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return relative.as_posix()


def upload(
    cur: Any, principal: AuthPrincipal, project_id: str, filename: str, content: bytes,
    wbs_id: str | None = None,
) -> DocumentUploadResponse:
    """문서를 올린다. wbs_id 를 주면 그 WBS 항목의 산출물로 바로 붙는다(ARC-016).

    항목이 없으면 올리기 전에 거절한다. 조용히 안 붙이면 용역사는 올렸다고 믿고 판정은 그대로다.
    """
    _require_project(cur, principal, project_id)
    wbs_item_id: str | None = None
    if wbs_id:
        dashboard_service.ensure_wbs_loaded(cur, project_id)
        item = wbs_repository.find_item(cur, project_id, wbs_id.strip())
        if item is None:
            raise errors.validation_failed(f"WBS 항목 {wbs_id} 이(가) 이 사업에 없습니다.")
        wbs_item_id = str(item["id"])

    if not filename or not filename.strip():
        raise errors.validation_failed("파일명이 없습니다.")
    ext = extractor.ext_of(filename)
    if ext not in extractor.SUPPORTED_EXTS:
        supported = " · ".join(extractor.SUPPORTED_EXTS)
        got = ext or "없음"
        raise errors.validation_failed(f"{supported} 만 올릴 수 있습니다. (받은 형식: {got})")
    if not content:
        raise errors.validation_failed("빈 파일입니다.")
    if len(content) > MAX_BYTES:
        raise errors.validation_failed("50MB 이하 파일만 올릴 수 있습니다.")

    file_hash = hashlib.sha256(content).hexdigest()
    existing = repository.find_by_hash(cur, project_id, file_hash)
    if existing:
        # 내용이 같으면 같은 파일이다. 막지 않는다. 읽기에 실패했던 것이면 다시 읽고, WBS
        # 항목을 지정했으면 잇는다. 사용자는 "다시 올리기" 로 재시도한다고 여긴다.
        document_id = str(existing["id"])
        if wbs_item_id:
            repository.link_wbs_item(cur, document_id, wbs_item_id)
        if existing["status"] == "FAILED":
            _process(cur, project_id, document_id, filename.strip(), ext, existing["stored_path"])
        return _to_response(repository.find_by_id(cur, document_id))

    stored_path = _store(project_id, file_hash, ext, content)
    document_id = repository.insert(
        cur, project_id, principal.user_id, filename.strip(), stored_path,
        extractor.MIME_BY_EXT.get(ext, "application/octet-stream"),
        ext, len(content), file_hash,
    )
    if wbs_item_id:
        repository.link_wbs_item(cur, document_id, wbs_item_id)
    _process(cur, project_id, document_id, filename.strip(), ext, stored_path)
    where = f" ({wbs_id.strip()} 항목)" if wbs_id else ""
    activity.record(
        cur, project_id=project_id, kind=activity.DOCUMENT_UPLOADED,
        audience=activity.other_side(principal.role),
        summary=f"문서 올림: {filename.strip()}{where}", actor=principal,
        target_type="DOCUMENT", target_key=document_id,
    )
    return _to_response(repository.find_by_id(cur, document_id))


def _process(
    cur: Any, project_id: str, document_id: str, filename: str, ext: str, stored_path: str
) -> None:
    """읽고 색인하고 초안까지. 처음 올릴 때와 실패 뒤 다시 올릴 때가 같은 길을 간다."""
    try:
        result = extractor.extract(Path(settings.document_root) / stored_path, ext)
    except Exception as exc:  # noqa: BLE001 — 파서가 죽어도 업로드 자체는 남긴다
        repository.mark_failed(cur, document_id, f"{type(exc).__name__}: {exc}")
        return
    if not result.text.strip():
        repository.mark_failed(cur, document_id, result.warning or "본문을 읽지 못했습니다.")
        return
    repository.mark_extracted(cur, document_id, result.text, result.page_count, result.warning)
    _index(cur, project_id, document_id, filename, result.text, stored_path)
    # 읽은 김에 초안까지 만든다. 사람이 확인할 것이 생겨야 업로드가 끝난 것이다.
    draft_service.propose_for_upload(cur, document_id, project_id, filename, result.text)


def list_for_project(
    cur: Any, principal: AuthPrincipal, project_id: str, page: PageQuery
) -> PageResponse[DocumentUploadResponse]:
    _require_project(cur, principal, project_id)
    total = repository.count_by_project(cur, project_id)
    rows = repository.list_by_project(cur, project_id, page)
    return PageResponse.of([_to_response(r) for r in rows], page, total)


def get_detail(cur: Any, principal: AuthPrincipal, document_id: str) -> DocumentDetailResponse:
    row = repository.find_by_id(cur, document_id)
    if row is None:
        raise errors.not_found("문서", document_id)
    _require_project(cur, principal, str(row["project_id"]))
    return DocumentDetailResponse(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        fileName=row["original_filename"],
        fileSize=row["size_bytes"],
        mimeType=row["content_type"],
        status=row["status"],
        error=row["error"],
        uploadedBy=row["uploaded_by"],
        uploadedAt=row["created_at"].isoformat(),
        pageCount=row["page_count"],
        extractedCharCount=row["extracted_chars"],
        wbsId=row["wbs_id"],
        wbsName=row["wbs_name"],
        productType=row["product_type"],
        proposedType=row["proposed_type"],
        draftStatus=row["draft_status"],
        workProductId=str(row["draft_work_product_id"]) if row["draft_work_product_id"] else None,
        downloadUrl=f"/api/documents/{row['id']}/content",
        originalUrl=None,  # 올린 문서는 여기가 원본이다. 도구에서 온 산출물은 external_url 을 쓴다
    )


def update(
    cur: Any, principal: AuthPrincipal, document_id: str, req: DocumentUpdateRequest
) -> DocumentDetailResponse:
    """자료 설정. WBS 항목과 29110 유형 태그를 사람이 정한다. 빈 문자열은 지운다."""
    row = repository.find_by_id(cur, document_id)
    if row is None:
        raise errors.not_found("문서", document_id)
    project_id = str(row["project_id"])
    _require_project(cur, principal, project_id)

    if req.wbsId is not None:
        wbs_id = req.wbsId.strip()
        if not wbs_id:
            repository.link_wbs_item(cur, document_id, None)
        else:
            dashboard_service.ensure_wbs_loaded(cur, project_id)
            item = wbs_repository.find_item(cur, project_id, wbs_id)
            if item is None:
                raise errors.validation_failed(f"WBS 항목 {wbs_id} 이(가) 이 사업에 없습니다.")
            repository.link_wbs_item(cur, document_id, str(item["id"]))

    if req.productType is not None:
        product_type = req.productType.strip() or None
        if product_type is not None and product_type not in DISPLAY_NAMES:
            raise errors.validation_failed(f"알 수 없는 산출물 유형입니다: {product_type}")
        repository.set_product_type(cur, document_id, product_type)

    return get_detail(cur, principal, document_id)


def get_text(cur: Any, principal: AuthPrincipal, document_id: str) -> DocumentTextResponse:
    row = repository.find_text(cur, document_id)
    if row is None:
        raise errors.not_found("문서", document_id)
    _require_project(cur, principal, str(row["project_id"]))
    return DocumentTextResponse(
        id=str(row["id"]),
        fileName=row["original_filename"],
        status=row["status"],
        charCount=len(row["extracted_text"]),
        pageCount=row["page_count"],
        text=row["extracted_text"],
    )


def _index(
    cur: Any, project_id: str, document_id: str, title: str, text: str, stored_path: str
) -> None:
    """색인은 실패해도 업로드를 되돌리지 않는다. 모델이 죽은 것과 문서가 없는 건 다른 문제다."""
    try:
        indexing.reindex(
            cur,
            embedding_port(),
            [
                indexing.IndexSource(
                    source_type="DOCUMENT_UPLOAD",
                    source_id=document_id,
                    project_id=project_id,
                    title=title,
                    body=text,
                    uri=stored_path,
                )
            ],
        )
    except errors.ApiError as exc:
        if not exc.code.startswith("AI_"):
            raise
        repository.note_error(cur, document_id, f"색인을 건너뛰었습니다 — {exc.message}")


# 열람용 조각 크기. 표가 한 조각 안에 들어가도록 줄 경계에서만 자른다.
_VIEW_SLICE_CHARS = 1200


def slice_for_reading(text: str, size: int = _VIEW_SLICE_CHARS) -> list[str]:
    """원문을 줄 경계에서 잘라 열람용 조각을 만든다.

    검색용 doc_chunk 를 그대로 보여 주면 안 된다 — 그건 15% 겹치게 자른 것이라
    이어 붙이면 같은 문단이 두 번 나온다. 목적이 다르면 자르는 방법도 달라야 한다.
    """
    if not text:
        return []
    slices, buf, count = [], [], 0
    for line in text.splitlines(keepends=True):
        if buf and count + len(line) > size:
            slices.append("".join(buf))
            buf, count = [], 0
        buf.append(line)
        count += len(line)
    if buf:
        slices.append("".join(buf))
    return slices


def list_chunks(
    cur: Any, principal: AuthPrincipal, document_id: str, page: PageQuery
) -> PageResponse[DocumentChunkResponse]:
    """원문 열람. 추출한 본문을 그대로 잘라 준다 — 이어 붙이면 원문이 된다."""
    row = repository.find_text(cur, document_id)
    if row is None:
        raise errors.not_found("문서", document_id)
    _require_project(cur, principal, str(row["project_id"]))

    slices = slice_for_reading(row["extracted_text"])
    window = slices[page.offset : page.offset + page.size]
    content = [
        DocumentChunkResponse(index=page.offset + i, content=text)
        for i, text in enumerate(window)
    ]
    return PageResponse.of(content, page, len(slices))


@dataclass
class StoredFile:
    """내려받을 원본. 파일명은 업로드 때 준 이름 그대로 돌려준다."""

    path: Path
    filename: str
    content_type: str


def get_file(cur: Any, principal: AuthPrincipal, document_id: str) -> StoredFile:
    row = repository.find_file(cur, document_id)
    if row is None:
        raise errors.not_found("문서", document_id)
    _require_project(cur, principal, str(row["project_id"]))

    path = Path(settings.document_root) / row["stored_path"]
    if not path.is_file():
        # DB 에는 있는데 파일이 없다. 보관 경로가 바뀌었거나 사람이 지운 것이다.
        raise errors.ApiError(410, "DOCUMENT_FILE_MISSING", "원본 파일이 보관소에 없습니다.")
    return StoredFile(path, row["original_filename"], row["content_type"])


def delete(cur: Any, principal: AuthPrincipal, document_id: str) -> None:
    """문서를 지운다. 색인된 청크와 보관 원본도 함께 사라진다."""
    row = repository.find_file(cur, document_id)
    if row is None:
        raise errors.not_found("문서", document_id)
    _require_project(cur, principal, str(row["project_id"]))

    rag_repo.delete_by_source(cur, "DOCUMENT_UPLOAD", document_id)
    repository.delete(cur, document_id)

    # 같은 내용을 다른 사업에서도 올렸을 수 있다. 마지막 하나일 때만 원본을 지운다.
    if repository.count_by_stored_path(cur, row["stored_path"]) == 0:
        Path(settings.document_root).joinpath(row["stored_path"]).unlink(missing_ok=True)
