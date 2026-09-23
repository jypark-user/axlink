"""서버 오류 기록 (운영). 500 이 표에 남고 최고관리자만 본다."""

from app.common import error_log
from app.db import tx
from tests.conftest import requires_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@requires_db
def test_잡히지_않은_예외는_기록되고_관리자만_본다(client, client_token, monkeypatch):
    from app.document import service as document_service

    def boom(*a, **k):
        raise RuntimeError("일부러 낸 오류")

    monkeypatch.setattr(document_service, "list_for_project", boom)
    with tx() as cur:
        error_log.clear(cur)

    # 기본 시험 클라이언트는 서버 예외를 다시 던진다. 여기서는 500 응답까지 가야 한다
    from fastapi.testclient import TestClient

    from app.main import app

    lenient = TestClient(app, raise_server_exceptions=False)
    r3 = client_token("r3")
    res = lenient.get(
        "/api/projects/c0000000-0000-4000-8000-000000000001/documents", headers=_auth(r3)
    )
    assert res.status_code == 500 and res.json()["code"] == "INTERNAL"

    # 용역사·발주기관은 못 본다
    assert client.get("/api/admin/errors", headers=_auth(r3)).status_code == 403

    page = client.get("/api/admin/errors", headers=_auth(client_token("r1")))
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["totalElements"] == 1
    entry = body["content"][0]
    assert entry["statusCode"] == 500 and entry["method"] == "GET"
    assert entry["path"].endswith("/documents")
    assert "RuntimeError: 일부러 낸 오류" in entry["message"]
    assert "boom" in entry["traceback"]
    assert entry["username"] == "r3"  # 누가 겪었는지

    admin = _auth(client_token("r1"))
    assert client.delete("/api/admin/errors", headers=admin).status_code == 204
    assert client.get("/api/admin/errors", headers=admin).json()["totalElements"] == 0
