"""문서 DTO. 필드명은 프런트 types/api.ts 의 DocumentUploadResponse 와 1:1 이다."""

from typing import Any

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: str
    projectId: str  # noqa: N815 — 프런트 계약 필드명
    fileName: str  # noqa: N815
    fileSize: int  # noqa: N815
    mimeType: str  # noqa: N815
    status: str
    uploadedBy: str  # noqa: N815
    uploadedAt: str  # noqa: N815
    extractedCharCount: int | None  # noqa: N815
    draftAvailable: bool  # noqa: N815
    workProductId: str | None  # noqa: N815
    error: str | None
    # 처리 작업 상태(GH-121). QUEUED 접수됨 · RUNNING 처리 중 · DONE 완료 · FAILED 실패
    processingState: str = "DONE"  # noqa: N815
    processingError: str | None = None  # noqa: N815


class DocumentDetailResponse(BaseModel):
    """자료 상세. 왼쪽 정보·설정, 오른쪽 추출 결과의 재료다."""

    id: str
    projectId: str  # noqa: N815
    fileName: str  # noqa: N815
    fileSize: int  # noqa: N815
    mimeType: str  # noqa: N815
    status: str
    error: str | None
    uploadedBy: str  # noqa: N815
    uploadedAt: str  # noqa: N815
    pageCount: int | None  # noqa: N815
    extractedCharCount: int | None  # noqa: N815
    wbsId: str | None  # noqa: N815  붙은 WBS 항목
    wbsName: str | None  # noqa: N815
    productType: str | None  # noqa: N815  사람이 정한 태그. 없으면 초안 추정을 보인다
    proposedType: str | None  # noqa: N815
    draftStatus: str | None  # noqa: N815
    workProductId: str | None  # noqa: N815  확정돼 22종 항목에 들어갔으면 그 항목
    downloadUrl: str  # noqa: N815
    originalUrl: str | None  # noqa: N815  원천 도구 링크. 올린 문서는 없다
    processingState: str = "DONE"  # noqa: N815
    processingError: str | None = None  # noqa: N815
    # 단계별 걸린 시간(초)·쪽수·청크 수. 처리 중에도 지금까지의 값이 보인다
    processingSteps: dict[str, Any] | None = None  # noqa: N815


class DocumentUpdateRequest(BaseModel):
    """자료 설정. 둘 다 선택이고, 빈 문자열은 지운다는 뜻이다."""

    wbsId: str | None = None  # noqa: N815
    productType: str | None = None  # noqa: N815


class DocumentTextResponse(BaseModel):
    """추출 결과 확인용. 프런트 화면에는 아직 없고 도구·검증에서 쓴다."""

    id: str
    fileName: str  # noqa: N815
    status: str
    charCount: int  # noqa: N815
    pageCount: int | None  # noqa: N815
    text: str


class DocumentChunkResponse(BaseModel):
    """색인된 본문 한 조각. 전문 열람은 이 조각을 순서대로 이어 붙여 보여 준다."""

    index: int
    content: str


class DraftRequirement(BaseModel):
    """초안 요구사항 한 건. 화면이 고쳐서 그대로 돌려보내므로 요청·응답이 같은 모양이다."""

    index: int
    code: str | None
    title: str
    body: str
    priority: str


class StructuringDraftResponse(BaseModel):
    documentId: str  # noqa: N815
    status: str
    suggestedType: str | None  # noqa: N815
    rejectedTypeRaw: str | None  # noqa: N815
    confidence: float
    title: str | None
    version: str | None
    authoredDate: str | None  # noqa: N815
    requirements: list[DraftRequirement]
    createdAt: str  # noqa: N815


class StructuringConfirmRequest(BaseModel):
    type: str
    title: str
    version: str
    authoredDate: str | None = None  # noqa: N815
    # 활동 구분(PM·SI)은 받지 않는다. 산출물 유형이 정한다. 예전 화면이 보내면 무시된다
    requirements: list[DraftRequirement] = []
    # 확정이 곧 제출이다(DEC-14). 예전 화면·스크립트가 SUBMITTED 를 보내도 받는다. 다른 값은 거절
    workProductStatus: str | None = None  # noqa: N815


class StructuringConfirmResponse(BaseModel):
    workProductId: str  # noqa: N815
    createdRequirementIds: list[str]  # noqa: N815
    indexedChunkCount: int  # noqa: N815
