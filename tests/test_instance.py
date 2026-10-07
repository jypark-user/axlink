"""실행 환경 이름표. 개발 환경은 화면에 띠가 보이고, 공개 환경은 비어 있다."""

from app.config import settings
from tests.conftest import requires_db


# 앱을 통째로 띄우는 client 는 DB 풀을 연다
@requires_db
def test_이름표가_없으면_비어_있다(client, monkeypatch):
    monkeypatch.setattr(settings, "instance_label", None)
    res = client.get("/api/instance")
    assert res.status_code == 200 and res.json() == {"label": None}


@requires_db
def test_이름표는_로그인_없이_보인다(client, monkeypatch):
    monkeypatch.setattr(settings, "instance_label", "내부 개발 환경")
    assert client.get("/api/instance").json() == {"label": "내부 개발 환경"}
