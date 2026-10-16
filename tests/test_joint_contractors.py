"""공동 수급 1단계 (GH-138, SER.SEC.003, ARC-029).

업체 A(넥스트소프트, r3)와 업체 B(시험 업체)가 한 사업에 참여한다. 업무 정보는 함께 보고,
도구 연결의 설정 변경·삭제는 소유 업체와 발주기관만 한다. 용역 업체는 업체·사용자·연결 소유를
바꿔 권한을 넓히지 못한다.
"""

import uuid

import pytest

from app.db import fetch_one, tx
from tests.conftest import requires_db

SEED_PID = "c0000000-0000-4000-8000-000000000001"
ORG_A = "a0000000-0000-4000-8000-000000000003"  # 넥스트소프트(r3)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _conn_body(target: str) -> dict:
    return {"tool": "GITHUB", "name": f"연결 {target}", "baseUrl": "https://api.github.com",
            "targetResource": target, "credential": {"accessToken": "ghp_secret_tail_ABCD"}}


@pytest.fixture
def joint(client, client_token):
    tag = uuid.uuid4().hex[:6]
    po = _auth(client_token("r2"))
    a = _auth(client_token("r3"))
    res = client.post("/api/projects", headers=po, json={
        "name": f"시험 사업-공동-{tag}", "startDate": "2026-09-01", "endDate": "2026-12-31",
        "description": "공동 수급 시험", "contractorName": "넥스트소프트",
        "deletePassword": "delete-me-1234"})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    # 업체 A: r3 를 할당하면 참여 업체로 올라가고, 사업 정보의 용역사 이름과 같아 대표사가 된다
    assert client.post(f"/api/projects/{pid}/assignments", headers=po, json={
        "contractorOrgId": ORG_A, "userIds": [str(_user_id("r3"))]}).status_code == 201
    # 업체 B: 새 업체 이름으로 참여사 추가 → 업체 지정 초대 → 가입
    org_b_name = f"시험용역사-B{tag}"
    parts = client.post(f"/api/projects/{pid}/participants", headers=po, json={
        "organizationName": org_b_name, "role": "PARTICIPANT", "workNote": "연계 모듈"})
    assert parts.status_code == 201, parts.text
    org_b = next(p["organizationId"] for p in parts.json() if p["organizationName"] == org_b_name)
    inv = client.post(f"/api/projects/{pid}/invites", headers=po, json={"organizationId": org_b})
    assert inv.status_code == 201, inv.text
    assert inv.json()["organizationName"] == org_b_name
    token = inv.json()["token"]
    preview = client.get(f"/api/auth/invitations/{token}").json()
    assert preview["contractorOrgName"] == org_b_name
    # 회사명에 업체 A 이름을 적어도 업체 B 로 들어간다
    acc = client.post("/api/auth/invitations/accept", json={
        "token": token, "contractorOrgName": "넥스트소프트", "username": f"test-b{tag}",
        "name": "B 업체 사용자", "password": "password-1234"})
    assert acc.status_code == 200, acc.text
    b = _auth(acc.json()["accessToken"])
    with tx() as cur:
        user_b = fetch_one(cur, "select organization_id from app_user where username = %s",
                           (f"test-b{tag}",))
    assert str(user_b["organization_id"]) == org_b

    conn_a = client.post(f"/api/projects/{pid}/connections", headers=a,
                         json=_conn_body(f"a/{tag}")).json()
    conn_b = client.post(f"/api/projects/{pid}/connections", headers=b,
                         json=_conn_body(f"b/{tag}")).json()
    yield {"pid": pid, "po": po, "a": a, "b": b, "org_b": org_b, "org_b_name": org_b_name,
           "conn_a": conn_a["id"], "conn_b": conn_b["id"], "tag": tag, "token": token}
    with tx() as cur:
        cur.execute("delete from project where id = %s", (pid,))
        cur.execute("delete from app_user where username = %s", (f"test-b{tag}",))
        cur.execute("delete from organization where name like '시험용역사-%%' and not exists "
                    "(select 1 from app_user u where u.organization_id = organization.id)")


def _user_id(username: str) -> str:
    with tx() as cur:
        return str(fetch_one(cur, "select id from app_user where username = %s", (username,))["id"])


def _conns(client, pid, who) -> dict[str, dict]:
    res = client.get(f"/api/projects/{pid}/connections", headers=who)
    assert res.status_code == 200, res.text
    return {c["id"]: c for c in res.json()}


# ---------------------------------------------------------------- 공유 조회


@requires_db
def test_업체_A_B_는_사업_업무_정보를_함께_보고_인증정보는_소유_업체만_본다(client, joint):
    pid = joint["pid"]
    parts = client.get(f"/api/projects/{pid}/participants", headers=joint["b"]).json()
    roles = {p["organizationName"]: p["role"] for p in parts}
    assert roles == {"넥스트소프트": "REPRESENTATIVE", joint["org_b_name"]: "PARTICIPANT"}

    for me, mine, other in ((joint["a"], joint["conn_a"], joint["conn_b"]),
                            (joint["b"], joint["conn_b"], joint["conn_a"])):
        seen = _conns(client, pid, me)
        assert set(seen) == {mine, other}  # 서로의 연결을 본다
        assert seen[mine]["canManage"] and seen[mine]["credentialMasked"].endswith("ABCD")
        assert not seen[other]["canManage"] and seen[other]["credentialMasked"] is None
        assert seen[other]["ownerState"] == "PARTICIPANT"
        # 이슈·요구사항 같은 업무 정보도 같이 본다
        assert client.get(f"/api/projects/{pid}/issues", headers=me).status_code == 200
        assert client.get(f"/api/projects/{pid}/requirements", headers=me).status_code == 200

    owners = {c["id"]: c["ownerOrgName"] for c in _conns(client, pid, joint["po"]).values()}
    assert owners == {joint["conn_a"]: "넥스트소프트", joint["conn_b"]: joint["org_b_name"]}
    # 발주기관은 모든 연결을 바꿀 수 있고 힌트도 본다
    assert all(c["canManage"] and c["credentialMasked"]
               for c in _conns(client, pid, joint["po"]).values())


# ---------------------------------------------------------------- 타 업체 연결


@requires_db
def test_다른_업체의_연결은_바꾸거나_지우거나_시험할_수_없다(client, joint):
    a_conn, b = joint["conn_a"], joint["b"]
    calls = [
        ("patch", f"/api/connections/{a_conn}", {"name": "가로채기"}),
        ("patch", f"/api/connections/{a_conn}/mapping", {"mappingRules": {}}),
        ("patch", f"/api/connections/{a_conn}/status", {"status": "PAUSED"}),
        ("post", f"/api/connections/{a_conn}/test", None),
        ("delete", f"/api/connections/{a_conn}", None),
    ]
    for method, url, body in calls:
        kwargs = {"json": body} if body is not None else {}
        res = getattr(client, method)(url, headers=b, **kwargs)
        assert res.status_code == 403, (url, res.text)
        assert res.json()["code"] == "CONNECTION_OWNER_ONLY"
    # 소유 업체와 발주기관은 된다
    assert client.patch(f"/api/connections/{a_conn}", headers=joint["a"],
                        json={"name": "A 가 바꿈"}).status_code == 200
    assert client.patch(f"/api/connections/{joint['conn_b']}", headers=joint["po"],
                        json={"name": "발주기관이 바꿈"}).status_code == 200


# ---------------------------------------------------------------- 타 사업


@requires_db
def test_참여하지_않은_사업은_볼_수_없다(client, joint):
    b = joint["b"]
    assert client.get(f"/api/projects/{SEED_PID}/connections", headers=b).status_code == 403
    assert client.get(f"/api/projects/{SEED_PID}/participants", headers=b).status_code == 403
    assert client.get(f"/api/projects/{SEED_PID}", headers=b).status_code == 403


# ---------------------------------------------------------------- 권한 우회


@requires_db
def test_용역_업체는_업체_사용자_초대_소유권을_바꿀_수_없다(client, joint):
    pid, a, b = joint["pid"], joint["a"], joint["b"]
    parts = client.get(f"/api/projects/{pid}/participants", headers=a).json()
    part_b = next(p["id"] for p in parts if p["organizationId"] == joint["org_b"])
    part_a = next(p["id"] for p in parts if p["organizationId"] == ORG_A)
    for who in (a, b):  # 대표사(A)도 마찬가지다
        assert client.post(f"/api/projects/{pid}/participants", headers=who, json={
            "organizationName": f"시험용역사-X{joint['tag']}"}).status_code == 403
        assert client.patch(f"/api/projects/{pid}/participants/{part_b}", headers=who,
                            json={"role": "REPRESENTATIVE"}).status_code == 403
        assert client.delete(f"/api/projects/{pid}/participants/{part_a}",
                             headers=who).status_code == 403
        assert client.post(f"/api/projects/{pid}/assignments", headers=who, json={
            "contractorOrgId": joint["org_b"], "userIds": []}).status_code == 403
        assert client.post(f"/api/projects/{pid}/invites", headers=who,
                           json={"organizationId": joint["org_b"]}).status_code == 403
    # 남의 연결을 자기 업체 소유로 바꾸지 못한다
    assert client.patch(f"/api/connections/{joint['conn_a']}/owner", headers=b,
                        json={"organizationId": joint["org_b"]}).status_code == 403
    # 발주기관도 참여 업체가 아닌 조직으로는 넘기지 못한다
    with tx() as cur:
        client_org = str(fetch_one(cur, "select organization_id from app_user where username='r2'")
                         ["organization_id"])
    assert client.patch(f"/api/connections/{joint['conn_a']}/owner", headers=joint["po"],
                        json={"organizationId": client_org}).status_code == 400


@requires_db
def test_업체를_지정하지_않은_옛_초대로_기존_업체에_끼어들_수_없다(client, joint):
    """V54 이전 초대(업체 미지정)는 새 업체 등록만 받는다. 이름을 아는 것만으로 남의 업체에
    들어가 그 업체 연결을 다루지 못한다."""
    from app.common.hashes import random_token, sha256_hex

    token = random_token()
    with tx() as cur:
        cur.execute(
            """
            insert into project_invite (project_id, token_hash, expires_at, created_by_user_id)
            values (%s, %s, now() + interval '1 day', %s)
            """,
            (joint["pid"], sha256_hex(token), _user_id("r2")),
        )
    base = {"token": token, "name": "끼어들기", "password": "password-1234"}
    dup = client.post("/api/auth/invitations/accept",
                      json={**base, "contractorOrgName": "넥스트소프트",
                            "username": f"test-x{joint['tag']}"})
    assert dup.status_code == 409 and dup.json()["code"] == "ORGANIZATION_EXISTS"
    client_org = client.post("/api/auth/invitations/accept",
                             json={**base, "contractorOrgName": "한국디지털공사",
                                   "username": f"test-y{joint['tag']}"})
    assert client_org.status_code == 400
    # 새 업체 이름이면 예전처럼 가입되고 그 업체가 참여사로 올라간다
    new = client.post("/api/auth/invitations/accept",
                      json={**base, "contractorOrgName": f"시험용역사-N{joint['tag']}",
                            "username": f"test-n{joint['tag']}"})
    assert new.status_code == 200, new.text
    parts = client.get(f"/api/projects/{joint['pid']}/participants", headers=joint["po"]).json()
    assert {p["organizationName"]: p["role"] for p in parts}[
        f"시험용역사-N{joint['tag']}"] == "PARTICIPANT"
    with tx() as cur:
        cur.execute("delete from app_user where username = %s", (f"test-n{joint['tag']}",))


@requires_db
def test_참여를_끝낸_업체는_접근과_연결_권한을_잃고_연결은_소유_불명확으로_남는다(client, joint):
    pid, po = joint["pid"], joint["po"]
    parts = client.get(f"/api/projects/{pid}/participants", headers=po).json()
    part_b = next(p["id"] for p in parts if p["organizationId"] == joint["org_b"])
    res = client.delete(f"/api/projects/{pid}/participants/{part_b}", headers=po)
    assert res.status_code == 200, res.text
    assert next(p for p in res.json() if p["id"] == part_b)["status"] == "REMOVED"
    # B 사용자는 할당이 해제돼 사업에 못 들어온다
    assert client.get(f"/api/projects/{pid}/connections", headers=joint["b"]).status_code == 403
    # B 가 만든 연결은 지워지지 않고 소유 불명확으로 보인다. A 는 못 바꾸고 발주기관은 넘길 수 있다
    seen = _conns(client, pid, joint["a"])
    assert seen[joint["conn_b"]]["ownerState"] == "UNCLEAR"
    assert client.patch(f"/api/connections/{joint['conn_b']}", headers=joint["a"],
                        json={"name": "x"}).status_code == 403
    moved = client.patch(f"/api/connections/{joint['conn_b']}/owner", headers=po,
                         json={"organizationId": ORG_A})
    assert moved.status_code == 200 and moved.json()["ownerState"] == "PARTICIPANT"
    assert _conns(client, pid, joint["a"])[joint["conn_b"]]["canManage"] is True
    # 끝난 업체를 지정한 초대 링크는 더 쓸 수 없다
    late = client.post("/api/auth/invitations/accept", json={
        "token": joint["token"], "username": f"test-z{joint['tag']}", "name": "늦은 가입",
        "password": "password-1234"})
    assert late.status_code == 404


# ---------------------------------------------------------------- 기존 사업


@requires_db
def test_기존_단일_업체_사업은_전환_뒤에도_그대로_동작한다(client, client_token):
    """V54 가 기존 할당을 참여 업체로 옮겼다. r3 은 자기 연결을 그대로 다룬다."""
    po, a = _auth(client_token("r2")), _auth(client_token("r3"))
    parts = client.get(f"/api/projects/{SEED_PID}/participants", headers=po).json()
    assert {p["organizationId"] for p in parts if p["status"] == "ACTIVE"} == {ORG_A}
    tag = uuid.uuid4().hex[:6]
    made = client.post(f"/api/projects/{SEED_PID}/connections", headers=a,
                       json=_conn_body(f"seed/{tag}"))
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    try:
        assert made.json()["canManage"] and made.json()["ownerState"] == "PARTICIPANT"
        assert client.patch(f"/api/connections/{cid}", headers=a,
                            json={"name": "고침"}).status_code == 200
        assert client.delete(f"/api/connections/{cid}", headers=a).status_code == 204
    finally:
        with tx() as cur:
            cur.execute("delete from tool_connection where id = %s", (cid,))
