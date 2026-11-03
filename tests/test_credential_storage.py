"""도구 인증정보는 암호문으로만 저장하고 화면·로그에 내보내지 않는다 (SER.SEC.001).

AES-256-GCM 으로 감싸고(app/common/crypto.py), 화면에는 뒤 4자 힌트만 나간다. 여기서는
저장 칸이 원문을 품지 않는지, 같은 원문도 매번 다른 암호문이 되는지, 원천 확인 때 복호화한
원문이 커넥터에만 건네지고 로그·응답에 남지 않는지를 본다.
"""

import base64
import logging

import pytest

from app.common import crypto, errors
from app.db import fetch_one, tx
from app.integration.adapter import github_connector as github
from tests.conftest import requires_db
from tests.test_connections import PID, _auth, as_pm  # noqa: F401  # as_pm 은 fixture

TOKEN = "ghp_secretValue_SEC001_abcdefghijkl"


def test_암호문은_원문을_품지_않고_되돌리면_원문이다():
    sealed = crypto.encrypt(TOKEN)
    assert sealed is not None and TOKEN not in sealed
    assert TOKEN.encode() not in base64.b64decode(sealed)
    assert crypto.decrypt(sealed) == TOKEN


def test_같은_원문도_매번_다른_암호문이_된다():
    assert crypto.encrypt(TOKEN) != crypto.encrypt(TOKEN)


def test_암호문을_건드리면_풀리지_않는다():
    blob = bytearray(base64.b64decode(crypto.encrypt(TOKEN)))
    blob[-1] ^= 0x01
    with pytest.raises(errors.ApiError):
        crypto.decrypt(base64.b64encode(bytes(blob)).decode())


def test_힌트는_뒤_4자만_남긴다():
    assert crypto.hint(TOKEN) == "****" + TOKEN[-4:]
    assert crypto.hint("") == "****"


@requires_db
def test_저장_칸과_응답과_로그에_원문이_없다(client, as_pm, monkeypatch, caplog):  # noqa: F811
    token, created = as_pm
    received: list[str] = []

    def verify(base, target, tok):
        received.append(tok)
        return github.ProbeResult("jypark-user/axlink", ["issue"], [])

    monkeypatch.setattr(github, "verify", verify)
    caplog.set_level(logging.DEBUG)

    res = client.post(
        f"/api/projects/{PID}/connections",
        json={
            "tool": "GITHUB",
            "name": "인증정보 저장 확인",
            "baseUrl": "https://api.github.com",
            "targetResource": "jypark-user/axlink",
            "credential": {"accessToken": TOKEN},
        },
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    cid = res.json()["id"]
    created.append(cid)
    tested = client.post(f"/api/connections/{cid}/test", headers=_auth(token))
    listed = client.get(f"/api/projects/{PID}/connections", headers=_auth(token))
    assert tested.status_code == 200 and listed.status_code == 200

    with tx() as cur:
        row = fetch_one(
            cur, "select auth_encrypted, auth_hint from tool_connection where id = %s", (cid,)
        )
    assert TOKEN not in row["auth_encrypted"]
    assert crypto.decrypt(row["auth_encrypted"]) == TOKEN
    assert row["auth_hint"] == "****" + TOKEN[-4:]

    # 복호화한 원문은 커넥터 확인 호출에만 건네진다
    assert received == [TOKEN]
    for body in (res.text, tested.text, listed.text):
        assert TOKEN not in body
    assert TOKEN not in caplog.text
