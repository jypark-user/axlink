"""문서 DTO. 필드명은 프런트 types/api.ts 의 DocumentUploadResponse 와 1:1 이다."""

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
    pmActivity: str | None  # noqa: N815
    siActivity: str | None  # noqa: N815
    requirements: list[DraftRequirement]
    createdAt: str  # noqa: N815


class StructuringConfirmRequest(BaseModel):
    type: str
    title: str
    version: str
    authoredDate: str | None = None  # noqa: N815
    pmActivity: str | None = None  # noqa: N815
    siActivity: str | None = None  # noqa: N815
    requirements: list[DraftRequirement] = []
    workProductStatus: str = "DRAFT"  # noqa: N815


class StructuringConfirmResponse(BaseModel):
    workProductId: str  # noqa: N815
    createdRequirementIds: list[str]  # noqa: N815
    indexedChunkCount: int  # noqa: N815
