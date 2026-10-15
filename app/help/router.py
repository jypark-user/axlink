"""/api/help — 사용 안내 문서 (SWFR.CON.006).

안내 글을 화면 코드에 박아 두지 않는다. 납품 문서 `docs/40-manual` 의 마크다운이 원천이고
API 는 그 파일을 그대로 낸다. 문서를 고치면 화면도 같이 바뀐다. 어떤 문서를 낼지는 아래
목록으로만 정한다. 경로를 요청에서 받지 않는다.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.deps import Principal
from app.common import errors
from app.config import settings

router = APIRouter(prefix="/api/help", tags=["help"])

# 화면 주소의 이름 → docs/40-manual 안의 파일
GUIDES = {"tool-integration": "도구-연동-가이드.md"}


class HelpDocResponse(BaseModel):
    slug: str
    title: str
    markdown: str
    updatedAt: str  # noqa: N815 — 파일 수정 시각


def manual_dir() -> Path:
    """운영 이미지는 AXLINK_MANUAL_DIR 로 준다. 없으면 저장소의 docs/40-manual."""
    if settings.manual_dir:
        return Path(settings.manual_dir)
    return Path(__file__).resolve().parents[2] / "docs" / "40-manual"


@router.get("/{slug}", response_model=HelpDocResponse)
def help_doc(slug: str, _principal: Principal) -> HelpDocResponse:
    name = GUIDES.get(slug)
    if name is None:
        raise errors.not_found("안내 문서", slug)
    path = manual_dir() / name
    if not path.is_file():
        raise errors.ApiError(404, "NOT_FOUND", f"안내 문서 파일이 없습니다: {name}")
    text = path.read_text(encoding="utf-8")
    first = next((line for line in text.splitlines() if line.startswith("# ")), "")
    return HelpDocResponse(
        slug=slug,
        title=first[2:].strip() or slug,
        # 제목 줄은 화면 머리말로 따로 그린다
        markdown=text.replace(first + "\n", "", 1) if first else text,
        updatedAt=datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
    )
