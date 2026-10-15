"""사용 안내 문서 API (SWFR.CON.006). 화면은 docs/40-manual 의 글을 그대로 받는다."""

from app.help import router as help_router
from tests.conftest import requires_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_목록에_있는_문서는_모두_저장소에_있다():
    for name in help_router.GUIDES.values():
        assert (help_router.manual_dir() / name).is_file(), name


@requires_db
def test_로그인한_사용자는_역할과_관계없이_도구_연동_가이드를_받는다(client, client_token):
    for user in ("r1", "r2", "r3"):
        res = client.get("/api/help/tool-integration", headers=_auth(client_token(user)))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["title"] == "도구 연동 가이드"
        assert body["markdown"].lstrip().startswith("용역사가")  # 제목 줄은 따로 낸다
        assert "## 4. Redmine 연동" in body["markdown"]
        assert body["updatedAt"]


@requires_db
def test_목록에_없는_이름이나_경로는_없는_것으로_본다(client, client_token):
    auth = _auth(client_token("r2"))
    assert client.get("/api/help/unknown", headers=auth).status_code == 404
    assert client.get("/api/help/..%2F..%2F.env", headers=auth).status_code == 404


def test_로그인하지_않으면_받지_못한다(client):
    assert client.get("/api/help/tool-integration").status_code == 401
