"""사용 설명서 API (SWFR.CON.006). 화면은 docs/40-manual 의 글을 그대로 받는다."""

import re

from app.help import router as help_router
from tests.conftest import requires_db

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
_ANCHOR = re.compile(r"^#{2,6} .+?\{#([\w-]+)\}\s*$", re.M)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _read(name: str) -> str:
    return (help_router.manual_dir() / name).read_text(encoding="utf-8")


def test_목록에_있는_문서는_모두_저장소에_있다():
    for name in help_router.GUIDES.values():
        assert (help_router.manual_dir() / name).is_file(), name


def test_설명서_안의_링크는_있는_문서와_있는_절을_가리킨다():
    """문서끼리는 파일 이름#절 로 링크한다. 화면은 이 링크를 설명서 주소로 바꾼다.
    파일 이름이나 절 이름을 바꾸고 링크를 안 고치면 여기서 떨어진다."""
    anchors = {name: set(_ANCHOR.findall(_read(name))) for name in help_router.GUIDES.values()}
    broken = []
    for name in help_router.GUIDES.values():
        for href in _LINK.findall(_read(name)):
            if href.startswith(("http://", "https://")):
                continue
            path, _, anchor = href.partition("#")
            target = path or name
            if target not in anchors:
                broken.append(f"{name}: {href} (문서 없음)")
            elif anchor and anchor not in anchors[target]:
                broken.append(f"{name}: {href} (절 없음)")
    assert not broken, broken


def test_설명서의_그림은_저장소에_있고_그림_API_가_내는_꼴이다():
    missing = []
    for name in help_router.GUIDES.values():
        for src in _IMAGE.findall(_read(name)):
            if not help_router._ASSET.match(src) or not (help_router.manual_dir() / src).is_file():
                missing.append(f"{name}: {src}")
    assert not missing, missing


def test_화면이_바로_여는_절이_설명서에_있다():
    """화면 코드가 /guide/<문서>#<절> 로 여는 절. 문서에서 지우면 화면 링크가 맨 위로 떨어진다."""
    anchors = set(_ANCHOR.findall(_read("요구사항-등록.md")))
    assert {"flow", "spec-format"} <= anchors


_ALL = list(help_router.GUIDES)
_OPEN = re.compile(r"<!--\s*대상:\s*(.*?)\s*-->")
_CLOSE = re.compile(r"<!--\s*/대상\s*-->")


def test_역할에_맞는_단락만_남기고_관리자에게는_보이는_사람을_적는다():
    md = "\n".join([
        "공통",
        "<!-- 대상: 발주기관 -->",
        "발주기관 단락",
        "<!-- /대상 -->",
        "<!-- 대상: 용역사, 발주기관 -->",
        "둘 다",
        "<!-- /대상 -->",
        "끝",
        "",
    ])
    client_view = "\n".join(["공통", "발주기관 단락", "둘 다", "끝", ""])
    assert help_router.for_role(md, "CLIENT") == client_view
    assert help_router.for_role(md, "CONTRACTOR") == "\n".join(["공통", "둘 다", "끝", ""])
    admin = help_router.for_role(md, "SUPER_ADMIN")
    assert "발주기관 단락" in admin and "둘 다" in admin
    assert "> 이 단락은 발주기관에게 보입니다." in admin
    assert "> 이 단락은 발주기관, 용역사에게 보입니다." in admin
    assert not _OPEN.search(admin) and not _CLOSE.search(admin)


def test_설명서의_단락_표시는_짝이_맞고_아는_역할만_쓴다():
    names = set(help_router._ROLE_NAMES)
    bad = []
    for name in help_router.GUIDES.values():
        text = _read(name)
        opens = _OPEN.findall(text)
        if len(opens) != len(_CLOSE.findall(text)):
            bad.append(f"{name}: 여는 표시와 닫는 표시 수가 다르다")
        bad += [
            f"{name}: 모르는 역할 {n}"
            for o in opens for n in (x.strip() for x in o.split(",")) if n not in names
        ]
        for role in ("CLIENT", "CONTRACTOR", "SUPER_ADMIN"):
            left = help_router.for_role(text, role)
            if _OPEN.search(left) or _CLOSE.search(left):
                bad.append(f"{name}: {role} 에게 표시가 남는다")
    assert not bad, bad


@requires_db
def test_설명서_목차와_문서는_역할에_맞게_나간다(client, client_token):
    expected = {
        "r1": _ALL,  # 플랫폼 관리자는 전부
        "r2": [s for s in _ALL if s != "admin"],  # 발주기관
        "r3": [s for s in _ALL if s not in ("admin", "ask")],  # 용역사는 AI 질의 화면이 없다
    }
    for user, slugs in expected.items():
        auth = _auth(client_token(user))
        index = client.get("/api/help", headers=auth)
        assert index.status_code == 200, index.text
        assert [e["slug"] for e in index.json()] == slugs, user
        for slug in _ALL:
            res = client.get(f"/api/help/{slug}", headers=auth)
            assert res.status_code == (200 if slug in slugs else 404), (user, slug)

    body = client.get("/api/help/tool-integration", headers=_auth(client_token("r2"))).json()
    assert body["title"] == "도구 연동"
    assert body["markdown"].lstrip().startswith("용역사가")  # 제목 줄은 따로 낸다
    assert "## 5. Redmine 연동 {#redmine}" in body["markdown"]
    assert body["updatedAt"]


@requires_db
def test_목록에_없는_이름이나_경로는_없는_것으로_본다(client, client_token):
    auth = _auth(client_token("r2"))
    assert client.get("/api/help/unknown", headers=auth).status_code == 404
    assert client.get("/api/help/..%2F..%2F.env", headers=auth).status_code == 404


@requires_db  # client 고정물이 앱을 띄우며 DB 에 붙는다
def test_로그인하지_않으면_받지_못한다(client):
    assert client.get("/api/help/tool-integration").status_code == 401
    assert client.get("/api/help").status_code == 401


@requires_db
def test_설명서_그림은_로그인한_사용자에게만_images_아래_그림_파일만_낸다(client, client_token):
    auth = _auth(client_token("r3"))
    url = "/api/help/assets/images/tool-integration/01-connections.png"
    ok = client.get(url, headers=auth)
    assert ok.status_code == 200, ok.text
    assert ok.headers["content-type"] == "image/png"
    assert ok.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get(url).status_code == 401
    for bad in ("images/../요구사항-등록.md", "images/%2E%2E/요구사항-등록.md", "요구사항-등록.md",
                "images/x.svg", "images/없는-그림.png", "../../.env"):
        assert client.get(f"/api/help/assets/{bad}", headers=auth).status_code == 404, bad
