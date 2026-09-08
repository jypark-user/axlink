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
