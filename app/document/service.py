"""문서 업로드 → 접수 → (뒤에서) 추출·색인·초안.

업로드 요청은 파일을 저장하고 문서 행을 남기는 데서 끝난다. 추출·색인·초안은 처리 대기열에
들어가 API 안의 작업자가 한다(app/document/worker.py). 3MB 문서의 임베딩이 7분 넘게 걸리는
동안 요청 안에서 돌리다 API 전체가 멈췄다(GH-121).

파일은 해시 이름으로 저장한다. 사용자가 준 파일명을 경로에 쓰지 않는다 —
경로 조작을 원천에서 막고, 같은 내용을 두 번 저장하지 않는다.
"""

import hashlib
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from app.activity import service as activity
from app.ai.embedding import embedding_port
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.config import settings
from app.dashboard import service as dashboard_service
from app.db import tx
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
HEARTBEAT_SECONDS = 30  # 처리 중임을 알리는 간격. 멈춘 작업 판정(document_stale_seconds)보다 짧다

log = logging.getLogger(__name__)


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
        processingState=row["processing_state"],
        processingError=row["processing_error"],
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
    designated_id: str | None = None,
) -> DocumentUploadResponse:
    """문서를 올린다. wbs_id 를 주면 그 WBS 항목의 산출물로 바로 붙는다(ARC-016).
    designated_id 를 주면 발주기관이 지정한 산출물 항목의 제출본으로 붙는다(UC-033). 그
    항목의 작업에도 함께 붙는다. 확정(초안 확정)해야 제출로 센다(DEC-14).

    항목이 없으면 올리기 전에 거절한다. 조용히 안 붙이면 용역사는 올렸다고 믿고 판정은 그대로다.
    """
    _require_project(cur, principal, project_id)
    wbs_item_id: str | None = None
    designated = designated_id.strip() if designated_id and designated_id.strip() else None
    if designated:
        from app.dashboard import designation

        dashboard_service.ensure_wbs_loaded(cur, project_id)
        wbs_item_id = designation.resolve_for_upload(cur, project_id, designated)
    elif wbs_id:
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
        # 내용이 같으면 같은 파일이다. 막지 않는다. 처리에 실패했던 것이면 다시 대기열에 넣고,
        # WBS 항목을 지정했으면 잇는다. 사용자는 "다시 올리기" 로 재시도한다고 여긴다.
        document_id = str(existing["id"])
        if wbs_item_id:
            repository.link_wbs_item(cur, document_id, wbs_item_id)
        if designated and wbs_item_id:
            _link_designated(cur, document_id, designated, wbs_item_id)
        if existing["processing_state"] == "FAILED":
            repository.requeue(cur, document_id)
            _after_enqueue(cur, document_id)
        return _to_response(repository.find_by_id(cur, document_id))

    stored_path = _store(project_id, file_hash, ext, content)
    try:
        with cur.connection.transaction():
            document_id = repository.insert(
                cur, project_id, principal.user_id, filename.strip(), stored_path,
                extractor.MIME_BY_EXT.get(ext, "application/octet-stream"),
                ext, len(content), file_hash,
            )
    except psycopg.errors.UniqueViolation:
        # 같은 파일이 동시에 두 번 올라왔다. 먼저 들어간 행을 돌려준다. 파일은 해시 경로라 하나다
        existing = repository.find_by_hash(cur, project_id, file_hash)
        assert existing is not None
        return _to_response(existing)
    if wbs_item_id:
        repository.link_wbs_item(cur, document_id, wbs_item_id)
    if designated and wbs_item_id:
        _link_designated(cur, document_id, designated, wbs_item_id)
    where = f" ({wbs_id.strip()} 항목)" if wbs_id else ""
    activity.record(
        cur, project_id=project_id, kind=activity.DOCUMENT_UPLOADED,
        audience=activity.other_side(principal.role),
        summary=f"문서 올림: {filename.strip()}{where}", actor=principal,
        target_type="DOCUMENT", target_key=document_id,
    )
    _after_enqueue(cur, document_id)
    return _to_response(repository.find_by_id(cur, document_id))


def _link_designated(cur: Any, document_id: str, designated_id: str, wbs_item_id: str) -> None:
    from app.dashboard import designation_repository

    designation_repository.link_document(cur, document_id, designated_id, wbs_item_id)


def _after_enqueue(cur: Any, document_id: str) -> None:
    """대기열에 넣은 뒤. 기본은 작업자가 가져간다. 시험 실행(document_processing=inline)은
    이 요청 안에서 바로 처리한다. 같은 처리 함수를 쓴다."""
    if settings.document_processing != "inline":
        return
    job = repository.start(cur, document_id)
    if job is not None:
        run_job(job, lambda: _same(cur))


@contextmanager
def _same(cur: Any) -> Iterator[Any]:
    yield cur


# ---------------------------------------------------------------- 처리 작업 (GH-121)


def process_next() -> bool:
    """대기열에서 하나를 가져와 처리한다. 가져올 것이 없으면 False."""
    with tx() as cur:
        job = repository.claim_next(cur)
    if job is None:
        return False
    run_job(job, tx)
    return True


def recover(all_running: bool) -> tuple[int, int]:
    """멈춘 작업을 되살린다. 기동 때는 처리 중인 것 전부(이 API 하나만 처리한다), 그 뒤로는
    heartbeat 가 오래 없는 것만."""
    with tx() as cur:
        return repository.recover_abandoned(
            cur, settings.document_stale_seconds, settings.document_max_attempts, all_running
        )


def run_job(job: dict[str, Any], txf: Callable[[], AbstractContextManager[Any]]) -> None:
    """추출 → 색인 → 초안. 단계마다 걸린 시간을 남긴다. 어디서 실패해도 처리 중으로 남지 않는다.

    오래 걸리는 임베딩·LLM 호출은 문서 행을 잠그지 않은 채 하고, 쓸 때만 잠근다. 그사이
    문서가 지워졌으면 아무것도 쓰지 않고 끝낸다."""
    document_id = job["id"]
    steps: dict[str, Any] = {"attempt": job["processing_attempts"]}
    beat = _Heartbeat(document_id, steps) if txf is tx else None
    try:
        _run_steps(job, txf, steps)
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 실패 상태와 이유로 남긴다
        log.exception("문서 처리 실패 document=%s", document_id)
        with txf() as cur:
            repository.fail(cur, document_id, f"처리 중 오류: {type(exc).__name__}: {exc}", steps)
    finally:
        if beat is not None:
            beat.stop()


def _run_steps(
    job: dict[str, Any], txf: Callable[[], AbstractContextManager[Any]], steps: dict[str, Any]
) -> None:
    document_id, project_id = job["id"], job["project_id"]
    filename, ext, stored_path = job["original_filename"], job["file_ext"], job["stored_path"]

    t = time.perf_counter()
    try:
        result = extractor.extract(Path(settings.document_root) / stored_path, ext)
    except extractor.UnsupportedDocument as exc:
        # 암호·스캔: 손상이 아니라 지원 제한이다. 사유와 대응 방법을 남긴다(AC-070-10)
        steps["extract_s"] = _since(t)
        _fail_extract(txf, document_id, str(exc), steps, label=f"지원 제한({exc.kind})")
        return
    except Exception as exc:  # noqa: BLE001 — 파서가 죽어도 업로드 자체는 남긴다
        steps["extract_s"] = _since(t)
        _fail_extract(txf, document_id, f"{type(exc).__name__}: {exc}", steps)
        return
    steps["extract_s"] = _since(t)
    steps["pages"] = result.page_count
    steps["chars"] = len(result.text)
    if not result.text.strip():
        _fail_extract(txf, document_id, result.warning or "본문을 읽지 못했습니다.", steps)
        return
    with txf() as cur:
        if not repository.lock_for_write(cur, document_id):
            return
        repository.mark_extracted(cur, document_id, result.text, result.page_count, result.warning)

    # 색인. 임베딩은 읽기 트랜잭션에서, 청크 교체는 문서를 잠근 쓰기 트랜잭션에서 한다
    t = time.perf_counter()
    source = indexing.IndexSource(
        source_type="DOCUMENT_UPLOAD", source_id=document_id, project_id=project_id,
        title=filename, body=result.text, uri=stored_path,
        block_positions=ext.upper() in extractor.BLOCK_POSITION_EXTS,
    )
    port = embedding_port()
    try:
        with txf() as cur:
            prepared = indexing.prepare(cur, port, [source], settings.document_embed_batch)
        steps["chunks"] = sum(len(drafts) for _, drafts in prepared.plan)
        with txf() as cur:
            if not repository.lock_for_write(cur, document_id):
                return
            indexing.write(cur, port, prepared)
    except errors.ApiError as exc:
        if not exc.code.startswith("AI_"):
            raise
        steps["index_s"] = _since(t)
        with txf() as cur:
            if repository.lock_for_write(cur, document_id):
                repository.fail(cur, document_id, f"색인 실패: {exc.message}", steps)
        return
    steps["index_s"] = _since(t)

    # 읽은 김에 초안까지 만든다. 사람이 확인할 것이 생겨야 업로드가 끝난 것이다
    t = time.perf_counter()
    with txf() as cur:
        if not repository.lock_for_write(cur, document_id):
            return
        draft_service.propose_for_upload(cur, document_id, filename, result.text)
    steps["draft_s"] = _since(t)
    with txf() as cur:
        repository.finish(cur, document_id, steps)


def _fail_extract(
    txf: Callable[[], AbstractContextManager[Any]],
    document_id: str,
    message: str,
    steps: dict[str, Any],
    label: str = "본문 읽기 실패",
) -> None:
    with txf() as cur:
        if repository.lock_for_write(cur, document_id):
            repository.mark_failed(cur, document_id, message)
            repository.fail(cur, document_id, f"{label}: {message}", steps)


def _since(t: float) -> float:
    return round(time.perf_counter() - t, 2)


class _Heartbeat:
    """처리 중 신호를 따로 보낸다. 임베딩 한 번이 몇 분씩 걸려도 멈춘 작업으로 오인하지 않게."""

    def __init__(self, document_id: str, steps: dict[str, Any]) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(document_id, steps), daemon=True, name="doc-heartbeat"
        )
        self._thread.start()

    def _run(self, document_id: str, steps: dict[str, Any]) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                with tx() as cur:
                    repository.heartbeat(cur, document_id, dict(steps))
            except Exception:  # noqa: BLE001 — 신호가 한 번 빠져도 작업은 계속한다
                log.warning("처리 중 신호 실패 document=%s", document_id, exc_info=True)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


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
        designatedName=row["designated_name"] if row.get("designated_active") else None,
        workProductId=str(row["draft_work_product_id"]) if row["draft_work_product_id"] else None,
        processingState=row["processing_state"],
        processingError=row["processing_error"],
        processingSteps=row["processing_steps"],
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
    # 요구사항 명세서로 등록된 문서는 등록(정리 중·확정 대기·확정본)이 살아 있는 동안 지우지 않는다.
    # 확정본은 요구사항의 원문 위치(표·행)가 이 문서를 가리킨다(IM-007 AC-020-8, GH-218).
    cur.execute(
        "select status from requirement_baseline where document_upload_id = %s limit 1",
        (document_id,),
    )
    used = cur.fetchone()
    if used is not None:
        raise errors.ApiError(
            409,
            "DOCUMENT_IN_BASELINE",
            "요구사항 명세서로 등록된 문서는 지울 수 없습니다. 등록을 먼저 취소하세요."
            if used["status"] != "CONFIRMED"
            else "확정된 요구사항 명세서 원본은 지울 수 없습니다.",
        )

    rag_repo.delete_by_source(cur, "DOCUMENT_UPLOAD", document_id)
    repository.delete(cur, document_id)

    # 같은 내용을 다른 사업에서도 올렸을 수 있다. 마지막 하나일 때만 원본을 지운다.
    if repository.count_by_stored_path(cur, row["stored_path"]) == 0:
        Path(settings.document_root).joinpath(row["stored_path"]).unlink(missing_ok=True)
