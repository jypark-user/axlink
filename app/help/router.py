"""/api/help — 사용 안내 문서 (SWFR.CON.006).

안내 글을 화면 코드에 박아 두지 않는다. 납품 문서 `docs/40-manual` 의 마크다운이 원천이고
API 는 그 파일을 낸다. 문서를 고치면 화면도 같이 바뀐다. 어떤 문서를 낼지는 아래
목록으로만 정한다. 경로를 요청에서 받지 않는다.

읽는 사람의 역할에 맞춰 거른다. 문서마다 볼 수 있는 역할이 있고(AUDIENCE), 문서 안에서는
`<!-- 대상: 발주기관, 용역사 -->` 와 `<!-- /대상 -->` 사이가 그 역할에게만 나간다. 주석이라
저장소에서 마크다운으로 열면 표시가 보이지 않는다. 플랫폼 관리자는 전부 받고, 단락마다
누구에게 보이는지 한 줄이 붙는다(설명서 검토용).
"""

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth.deps import Principal
from app.common import errors
from app.config import settings

router = APIRouter(prefix="/api/help", tags=["help"])

# 화면 주소의 이름 → docs/40-manual 안의 파일. 순서가 설명서 목차 순서다.
# 문서끼리는 파일 이름으로 링크한다(저장소에서 그대로 열린다). 화면이 아래 목록으로 주소를 바꾼다
GUIDES = {
    "manual": "사용-설명서.md",
    "account": "로그인과-계정.md",
    "status": "현황-보기.md",
    "requirement-baseline": "요구사항-등록.md",
    "tool-integration": "도구-연동-가이드.md",
    "reviews": "확인-요청.md",
    "deliverables": "산출물과-자료.md",
    "ask": "AI-질의.md",
    "project-setup": "사업-설정.md",
    "admin": "플랫폼-관리.md",
}

ADMIN, CLIENT, CONTRACTOR = "SUPER_ADMIN", "CLIENT", "CONTRACTOR"

# 문서를 볼 수 있는 역할. 여기 없는 문서는 모두에게 보인다. 플랫폼 관리자는 늘 본다
AUDIENCE: dict[str, frozenset[str]] = {
    "ask": frozenset({CLIENT}),  # AI 질의 화면은 용역사에게 없다(routes EXCEPT_CONTRACTOR)
    "admin": frozenset(),  # 관리자 전용 화면
}

# 문서 안 단락 표시의 이름 → 역할
_ROLE_NAMES = {"관리자": ADMIN, "플랫폼 관리자": ADMIN, "발주기관": CLIENT, "용역사": CONTRACTOR}
_ROLE_LABELS = {ADMIN: "플랫폼 관리자", CLIENT: "발주기관", CONTRACTOR: "용역사"}
_BLOCK = re.compile(r"<!--\s*대상:\s*(.*?)\s*-->\n?(.*?)<!--\s*/대상\s*-->\n?", re.S)


def can_read(slug: str, role: str) -> bool:
    return role == ADMIN or slug not in AUDIENCE or role in AUDIENCE[slug]


def for_role(markdown: str, role: str) -> str:
    """역할에 맞는 단락만 남긴다. 관리자에게는 전부 두고 단락마다 보이는 사람을 적는다."""

    def keep(m: re.Match[str]) -> str:
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        roles = {_ROLE_NAMES[n] for n in names if n in _ROLE_NAMES}
        body = m.group(2)
        if role == ADMIN:
            if body.lstrip().startswith("|"):
                return body  # 표의 줄이다. 설명 줄을 끼우면 표가 끊긴다
            who = ", ".join(_ROLE_LABELS[r] for r in (CLIENT, CONTRACTOR, ADMIN) if r in roles)
            return f"> 이 단락은 {who}에게 보입니다.\n\n{body}"
        return body if role in roles else ""

    return _BLOCK.sub(keep, markdown)


# 문서에 넣는 화면 캡처. images/ 아래 그림 파일만 낸다. svg 는 스크립트를 품을 수 있어 받지 않는다
_ASSET = re.compile(r"^images/(?:[\w.\-]+/)*[\w.\-]+\.(png|jpe?g|webp)$")
_ASSET_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


class HelpEntryResponse(BaseModel):
    slug: str
    title: str
    file: str  # 문서끼리의 링크가 가리키는 파일 이름


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


def _title(path: Path, slug: str) -> str:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("# "):
                return line[2:].strip()
    return slug


@router.get("", response_model=list[HelpEntryResponse])
def help_index(principal: Principal) -> list[HelpEntryResponse]:
    """설명서 목차. 파일이 없거나 읽는 사람의 역할에 맞지 않는 항목은 빼고 낸다."""
    out = []
    for slug, name in GUIDES.items():
        path = manual_dir() / name
        if path.is_file() and can_read(slug, principal.role):
            out.append(HelpEntryResponse(slug=slug, title=_title(path, slug), file=name))
    return out


@router.get("/assets/{path:path}")
def help_asset(path: str, _principal: Principal) -> FileResponse:
    """문서 안 그림(`images/도구-연동/01.png`). 경로 꼴과 위치를 둘 다 본다."""
    m = _ASSET.match(path)
    root = (manual_dir() / "images").resolve()
    target = (manual_dir() / path).resolve() if m and ".." not in path.split("/") else None
    if target is None or not target.is_relative_to(root) or not target.is_file():
        raise errors.not_found("안내 그림", path)
    return FileResponse(
        target, media_type=_ASSET_TYPES[m.group(1).lower()],
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{slug}", response_model=HelpDocResponse)
def help_doc(slug: str, principal: Principal) -> HelpDocResponse:
    name = GUIDES.get(slug)
    # 볼 수 없는 문서는 없는 문서와 같게 답한다
    if name is None or not can_read(slug, principal.role):
        raise errors.not_found("안내 문서", slug)
    path = manual_dir() / name
    if not path.is_file():
        raise errors.ApiError(404, "NOT_FOUND", f"안내 문서 파일이 없습니다: {name}")
    text = for_role(path.read_text(encoding="utf-8"), principal.role)
    first = next((line for line in text.splitlines() if line.startswith("# ")), "")
    return HelpDocResponse(
        slug=slug,
        title=first[2:].strip() or slug,
        # 제목 줄은 화면 머리말로 따로 그린다
        markdown=text.replace(first + "\n", "", 1) if first else text,
        updatedAt=datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
    )
