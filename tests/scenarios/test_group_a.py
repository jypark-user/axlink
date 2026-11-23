"""A 그룹: 사업·조직·계정 (UC-001 ~ UC-004) 예제 시나리오.

기대 결과는 IM-007 v0.2.4 의 시나리오 표 그대로다. 구현에 없는 기능(비밀번호 재설정, 초대 취소,
사업 종료 처리)은 기대 결과대로 단언해 **실패로 남긴다**. 그것이 결함 기록의 출발점이다.
브라우저 열이 붙은 시나리오(UC-002-S01·UC-003-S01·UC-004-S01·S03)는 API 부분만 여기서 보고
화면 확인은 따로 기록한다(이 시험의 통과가 그 AC 의 통과는 아니다).
"""

from __future__ import annotations

import re

import pytest

from tests.fixtures.im009 import data as d
from tests.fixtures.im009.seed import PASSWORD
from tests.scenarios.conftest import auth

pytestmark = pytest.mark.db


def _login(c, username: str, password: str):
    return c.post("/api/auth/login", json={"username": username, "password": password})


# ------------------------------------------------------------------ UC-001


def test_UC_001_S01_발급과_첫_로그인(target, s0):
    """발급 응답에 비밀번호 1회, 로그인 성공, 계정 조회·이력에 비밀번호 없음 (AC-001-2)."""
    adm = auth(s0.tokens["TD-ACC-A1"])
    res = target.post(
        "/api/admin/users",
        json={"organizationId": s0.ids["TD-ORG-C1"], "username": "td-c1-s01", "name": "발급 시험"},
        headers=adm,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    temp = body["temporaryPassword"]
    assert temp and len(temp) >= 8
    assert _login(target, "td-c1-s01", temp).status_code == 200
    # 조회·이력 어디에도 첫 비밀번호가 없다
    for path in ("/api/admin/users", f"/api/admin/users?organizationId={s0.ids['TD-ORG-C1']}"):
        listing = target.get(path, headers=adm)
        if listing.status_code == 200:
            assert temp not in listing.text
    org_users = target.get(f"/api/admin/organizations/{s0.ids['TD-ORG-C1']}/users", headers=adm)
    if org_users.status_code == 200:
        assert temp not in org_users.text


def test_UC_001_S02_중지_뒤_세션(target, s0):
    """중지 → 갱신 토큰 갱신·재로그인 모두 거절 (AC-001-3)."""
    adm = auth(s0.tokens["TD-ACC-A1"])
    made = target.post(
        "/api/admin/users",
        json={"organizationId": s0.ids["TD-ORG-C1"], "username": "td-c1-s02", "name": "중지 시험"},
        headers=adm,
    ).json()
    login = _login(target, "td-c1-s02", made["temporaryPassword"]).json()
    res = target.patch(
        f"/api/admin/users/{made['id']}/status", json={"status": "DISABLED"}, headers=adm
    )
    assert res.status_code == 204, res.text
    refreshed = target.post("/api/auth/refresh", json={"refreshToken": login["refreshToken"]})
    assert refreshed.status_code in (401, 403), refreshed.text
    assert _login(target, "td-c1-s02", made["temporaryPassword"]).status_code in (401, 403)
    # 접근 토큰 만료 뒤 거절은 유효 시간(30분)을 기다려야 해서 자동 시험에서는 보지 않는다.
    # 만료 전 접근 토큰이 통하는 것은 명세가 허용한다(「유효 시간이 지나면」).


def test_UC_001_S03_역할_외_시도(target, s0):
    """발주기관이 조직 등록 시도 → 거절 (AC-001-1, COMMON-S02)."""
    res = target.post(
        "/api/admin/organizations", json={"name": "임의 조직"}, headers=auth(s0.tokens["TD-ACC-C1"])
    )
    assert res.status_code == 403, res.text
    res = target.post(
        "/api/admin/users",
        json={"organizationId": s0.ids["TD-ORG-C1"], "username": "td-x", "name": "x"},
        headers=auth(s0.tokens["TD-ACC-V1"]),
    )
    assert res.status_code == 403, res.text


def test_UC_001_S04_중복_아이디(target, s0):
    """대소문자만 다른 아이디로 발급 → 거절, 중복 표시. 기존 계정 그대로 (COMMON-S03)."""
    adm = auth(s0.tokens["TD-ACC-A1"])
    before = _login(target, d.ACCOUNTS["TD-ACC-C1"].username, PASSWORD).status_code
    res = target.post(
        "/api/admin/users",
        json={"organizationId": s0.ids["TD-ORG-C1"], "username": "TD-C1", "name": "중복"},
        headers=adm,
    )
    assert res.status_code in (400, 409), res.text
    assert (
        "중복" in res.text
        or "이미" in res.text
        or res.json().get("code") in ("DUPLICATE", "CONFLICT", "USERNAME_TAKEN")
    ), res.text
    assert _login(target, d.ACCOUNTS["TD-ACC-C1"].username, PASSWORD).status_code == before == 200


def test_UC_001_S05_중지_계정의_기록_보존(target, s0):
    """C1 이 3.1 완료 확인한 뒤 중지 → 확인자 「김주무관」 그대로 (AC-001-4)."""
    adm = auth(s0.tokens["TD-ACC-A1"])
    pid = s0.ids["TD-PRJ-1"]
    c1 = s0.ids["TD-ACC-C1"]
    try:
        assert (
            target.patch(
                f"/api/admin/users/{c1}/status", json={"status": "DISABLED"}, headers=adm
            ).status_code
            == 204
        )
        summary = target.get(f"/api/projects/{pid}/wbs/completion", headers=adm).json()
        item = next(i for i in summary["items"] if i["wbsId"] == "3.1")
        assert item["completionStatus"] == "CONFIRMED"
        assert item["confirmedBy"] == d.ACCOUNTS["TD-ACC-C1"].display
    finally:
        target.patch(f"/api/admin/users/{c1}/status", json={"status": "ACTIVE"}, headers=adm)
        s0.tokens["TD-ACC-C1"] = s0.login(d.ACCOUNTS["TD-ACC-C1"].username, PASSWORD)


def test_UC_001_S06_비밀번호_재설정(target, s0):
    """관리자 재설정 → 옛 비밀번호 거절, 새 비밀번호 성공, 응답에 1회만 (AC-001-5)."""
    adm = auth(s0.tokens["TD-ACC-A1"])
    made = target.post(
        "/api/admin/users",
        json={"organizationId": s0.ids["TD-ORG-C1"], "username": "td-c1-s06", "name": "재설정"},
        headers=adm,
    ).json()
    old = made["temporaryPassword"]
    res = target.post(f"/api/admin/users/{made['id']}/password-reset", headers=adm)
    assert res.status_code == 200, f"재설정 API 없음 또는 실패: {res.status_code} {res.text[:200]}"
    new = res.json()["temporaryPassword"]
    assert _login(target, "td-c1-s06", old).status_code in (401, 403)
    assert _login(target, "td-c1-s06", new).status_code == 200


# ------------------------------------------------------------------ UC-002


def test_UC_002_S01_등록_직후_상태(target, s0, screen):
    """TD-PRJ-3: 요구사항 미등록, 진척 산출 불가, 점검표 22종 미제출, 미처리 0 (AC-002-1)."""
    h = auth(s0.tokens["TD-ACC-C1"])
    pid = s0.ids["TD-PRJ-3"]
    prog = target.get(f"/api/projects/{pid}/progress", headers=h).json()
    assert prog["representative"] is None, prog
    assert prog["level"] == "NONE", prog  # 제출본이 없으면 L4 도 세우지 않는다(DEF-V003)
    reqs = target.get(f"/api/projects/{pid}/requirements", headers=h).json()
    assert reqs["totalElements"] == 0
    wps = target.get(f"/api/projects/{pid}/work-products", headers=h).json()
    assert wps["totalCount"] == 22
    assert all(i["status"] not in ("SUBMITTED", "APPROVED") for i in wps["items"])
    rr = target.get(f"/api/projects/{pid}/review-requests", headers=h).json()
    assert rr["totalElements"] == 0
    _ui_UC_002_S01(screen, s0)


def test_UC_002_S02_다른_발주기관(target, s0):
    """C2 가 TD-PRJ-1 조회 → 거절·비노출 (AC-002-2, COMMON-S01)."""
    h = auth(s0.tokens["TD-ACC-C2"])
    pid = s0.ids["TD-PRJ-1"]
    assert target.get(f"/api/projects/{pid}", headers=h).status_code in (403, 404)
    listing = target.get("/api/projects?size=100", headers=h).json()
    assert pid not in {p["id"] for p in listing["content"]}
    # 용역사는 사업 정보를 바꿀 수 없다
    res = target.patch(
        f"/api/projects/{pid}", json={"name": "바꿈"}, headers=auth(s0.tokens["TD-ACC-V1"])
    )
    assert res.status_code == 403, res.text


def test_UC_002_S03_기간_역순_중복_이름(target, s0):
    """종료일 < 시작일 / 같은 이름 → 각각 거절, 사유 표시 (AC-002-4, COMMON-S03)."""
    h = auth(s0.tokens["TD-ACC-C1"])
    base = {"description": "시험", "contractorName": "", "deletePassword": "im009-delete"}
    res = target.post(
        "/api/projects",
        json={"name": "기간 역순", "startDate": "2026-12-01", "endDate": "2026-11-01", **base},
        headers=h,
    )
    assert res.status_code == 400, res.text
    res = target.post(
        "/api/projects",
        json={
            "name": d.PROJECTS["TD-PRJ-1"].name,
            "startDate": "2026-03-02",
            "endDate": "2026-11-30",
            **base,
        },
        headers=h,
    )
    assert res.status_code in (400, 409), res.text
    assert res.status_code < 500


def test_UC_002_S04_종료_처리(target, s0):
    """종료 처리 → 데이터 그대로, 예약 수집 멈춤 (AC-002-3)."""
    h = auth(s0.tokens["TD-ACC-C1"])
    pid = s0.ids["TD-PRJ-1"]
    res = target.patch(f"/api/projects/{pid}", json={"status": "CLOSED"}, headers=h)
    assert res.status_code == 200 and res.json().get("status") == "CLOSED", (
        f"종료 처리 수단 없음: {res.status_code} {res.text[:200]}"
    )


def test_UC_002_S05_삭제_비밀번호(target, s0):
    """틀린 비밀번호 거절, 맞는 비밀번호 삭제 (E5). 삭제용 사업을 따로 만든다."""
    h = auth(s0.tokens["TD-ACC-C1"])
    made = target.post(
        "/api/projects",
        json={
            "name": "[시험] 삭제",
            "startDate": "2026-09-01",
            "endDate": "2026-12-31",
            "description": "삭제 시험",
            "contractorName": "",
            "deletePassword": "right-pass",
        },
        headers=h,
    ).json()
    pid = made["id"]
    res = target.request("DELETE", f"/api/projects/{pid}", json={"password": "wrong"}, headers=h)
    assert res.status_code in (400, 403), res.text
    assert target.get(f"/api/projects/{pid}", headers=h).status_code == 200
    res = target.request(
        "DELETE", f"/api/projects/{pid}", json={"password": "right-pass"}, headers=h
    )
    assert res.status_code == 204, res.text
    # 삭제된 사업의 조회 응답 코드(403·404)는 명세가 정하지 않았다. 사라졌는지만 본다(DEF-V007)
    assert target.get(f"/api/projects/{pid}", headers=h).status_code in (403, 404)


# ------------------------------------------------------------------ UC-003


def test_UC_003_S01_초대_가입_범위(target, s0, screen):
    """업체 지정 초대 → 가입 → 조직 V1·역할 용역사·TD-PRJ-1 만, TD-PRJ-2 거절 (AC-003-1·2)."""
    h = auth(s0.tokens["TD-ACC-C1"])
    inv = target.post(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/invites",
        json={"organizationId": s0.ids["TD-ORG-V1"]},
        headers=h,
    ).json()
    login = target.post(
        "/api/auth/invitations/accept",
        json={
            "token": inv["token"],
            "username": "td-v0-s01",
            "name": "한신입(가입)",
            "password": PASSWORD,
        },
    )
    assert login.status_code == 200, login.text
    me = login.json()["user"]
    assert me["role"] == "CONTRACTOR"
    assert me["allowedProjectIds"] == [s0.ids["TD-PRJ-1"]]
    tok = auth(login.json()["accessToken"])
    assert target.get(f"/api/projects/{s0.ids['TD-PRJ-2']}", headers=tok).status_code in (403, 404)
    listing = target.get("/api/projects?size=100", headers=tok).json()
    assert {p["id"] for p in listing["content"]} == {s0.ids["TD-PRJ-1"]}
    s0.ids["UC-003-S01:token"] = inv["token"]
    _ui_UC_003_S01(screen, s0)


def test_UC_003_S02_취소된_링크(target, s0):
    """C1 취소 → 다른 사람 가입 시도 거절 (AC-003-4)."""
    h = auth(s0.tokens["TD-ACC-C1"])
    inv = target.post(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/invites",
        json={"organizationId": s0.ids["TD-ORG-V1"]},
        headers=h,
    ).json()
    cancel = (
        target.delete(f"/api/projects/{s0.ids['TD-PRJ-1']}/invites/{inv['id']}", headers=h)
        if "id" in inv
        else target.post(
            f"/api/projects/{s0.ids['TD-PRJ-1']}/invites/revoke",
            json={"token": inv["token"]},
            headers=h,
        )
    )
    assert cancel.status_code in (200, 204), (
        f"초대 취소 수단 없음: {cancel.status_code} {cancel.text[:200]}"
    )
    res = target.post(
        "/api/auth/invitations/accept",
        json={
            "token": inv["token"],
            "username": "td-v0-s02",
            "name": "x",
            "password": PASSWORD,
        },
    )
    assert res.status_code in (400, 401, 403, 404, 410), res.text


def test_UC_003_S03_대표사의_권한_확대_시도(target, s0):
    """V1(대표사)이 사용자 추가·배정·초대·연결 소유 변경 시도 → 모두 거절 (AC-003-3)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    pid = s0.ids["TD-PRJ-1"]
    assert (
        target.post(
            f"/api/projects/{pid}/participants",
            json={"organizationName": "새 업체", "role": "PARTICIPANT"},
            headers=v1,
        ).status_code
        == 403
    )
    assert (
        target.post(
            f"/api/projects/{pid}/assignments",
            json={"contractorOrgId": s0.ids["TD-ORG-V1"], "userIds": [s0.ids["TD-ACC-V0"]]},
            headers=v1,
        ).status_code
        == 403
    )
    assert target.post(f"/api/projects/{pid}/invites", json={}, headers=v1).status_code == 403
    # 초대 목록·취소(GH-209)도 용역사는 못 쓴다. 404 는 미구현, 403 이 권한 거절이다
    assert target.get(f"/api/projects/{pid}/invites", headers=v1).status_code == 403
    assert (
        target.patch(
            f"/api/connections/{s0.ids['TD-CON-3']}/owner",
            json={"organizationId": s0.ids["TD-ORG-V1"]},
            headers=v1,
        ).status_code
        == 403
    )


def test_UC_003_S04_업체_제외_뒤_보존(target, s0):
    """V2 제외 → TD-CON-3 남음·소유 표시, V2 접근 거절 (AC-003-5). 끝에 복원한다."""
    h = auth(s0.tokens["TD-ACC-C1"])
    pid = s0.ids["TD-PRJ-1"]
    parts = target.get(f"/api/projects/{pid}/participants", headers=h).json()
    v2 = next(p for p in parts if p["organizationId"] == s0.ids["TD-ORG-V2"])
    try:
        res = target.delete(f"/api/projects/{pid}/participants/{v2['id']}", headers=h)
        assert res.status_code == 200, res.text
        conns = target.get(f"/api/projects/{pid}/connections", headers=h).json()
        rows = conns if isinstance(conns, list) else conns.get("content", [])
        con3 = next((c for c in rows if c["id"] == s0.ids["TD-CON-3"]), None)
        assert con3 is not None, "제외 뒤 TD-CON-3 가 사라졌다"
        owner_text = str(con3.get("ownerOrgName") or con3.get("ownerOrgId") or "")
        assert owner_text, f"소유 업체 표시가 없다: {con3}"
        v2_res = target.get(f"/api/projects/{pid}", headers=auth(s0.tokens["TD-ACC-V2"]))
        assert v2_res.status_code in (403, 404), v2_res.text
        s0.ids["UC-003-S04:removed"] = "1"
    finally:
        target.post(
            f"/api/projects/{pid}/participants",
            json={"organizationId": s0.ids["TD-ORG-V2"], "role": "PARTICIPANT"},
            headers=h,
        )
        target.post(
            f"/api/projects/{pid}/assignments",
            json={"contractorOrgId": s0.ids["TD-ORG-V2"], "userIds": [s0.ids["TD-ACC-V2"]]},
            headers=h,
        )


def test_UC_003_S05_제외된_업체의_링크(target, s0):
    """제외된 업체를 지정한 링크로 가입 시도 → 거절 (AC-003-4)."""
    h = auth(s0.tokens["TD-ACC-C1"])
    pid = s0.ids["TD-PRJ-9"]
    # TD-PRJ-9 에 V2 를 넣고 초대 링크를 만든 뒤 제외한다
    parts = target.post(
        f"/api/projects/{pid}/participants",
        json={"organizationId": s0.ids["TD-ORG-V2"], "role": "PARTICIPANT"},
        headers=h,
    ).json()
    v2 = next(p for p in parts if p["organizationId"] == s0.ids["TD-ORG-V2"])
    inv = target.post(
        f"/api/projects/{pid}/invites", json={"organizationId": s0.ids["TD-ORG-V2"]}, headers=h
    ).json()
    assert (
        target.delete(f"/api/projects/{pid}/participants/{v2['id']}", headers=h).status_code == 200
    )
    res = target.post(
        "/api/auth/invitations/accept",
        json={
            "token": inv["token"],
            "username": "td-v2-s05",
            "name": "x",
            "password": PASSWORD,
        },
    )
    assert res.status_code in (400, 401, 403, 404, 410), res.text


# ------------------------------------------------------------------ UC-004


def test_UC_004_S02_틀린_자격증명(target, s0):
    """잘못된 비밀번호 · 중지 계정 → 같은 문안, 세션 없음 (AC-004-1)."""
    adm = auth(s0.tokens["TD-ACC-A1"])
    made = target.post(
        "/api/admin/users",
        json={"organizationId": s0.ids["TD-ORG-C1"], "username": "td-c1-s42", "name": "중지"},
        headers=adm,
    ).json()
    target.patch(f"/api/admin/users/{made['id']}/status", json={"status": "DISABLED"}, headers=adm)
    wrong = _login(target, d.ACCOUNTS["TD-ACC-C1"].username, "definitely-wrong")
    disabled = _login(target, "td-c1-s42", made["temporaryPassword"])
    assert wrong.status_code == disabled.status_code in (401, 403)
    assert wrong.json().get("message") == disabled.json().get("message")
    assert "accessToken" not in wrong.text and "accessToken" not in disabled.text


def test_UC_004_S01_역할별_첫_화면(target, s0, screen):
    """화면 로그인 직후: C1 자기 조직 사업, V1 배정 사업(TD-PRJ-1·9)만, A1 다른 기관 사업까지."""
    if not screen:
        pytest.skip("화면 시나리오. 원격 대상 + AXLINK_BROWSER_CHROME 에서 돈다")
    from tests.fixtures.im009.seed import ADMIN_PASS, ADMIN_USER

    name = {k: d.PROJECTS[k].name for k in ("TD-PRJ-1", "TD-PRJ-2", "TD-PRJ-9")}
    for acc, password, see, hidden in (
        ("TD-ACC-C1", PASSWORD, ("TD-PRJ-1", "TD-PRJ-9"), ("TD-PRJ-2",)),
        ("TD-ACC-V1", PASSWORD, ("TD-PRJ-1", "TD-PRJ-9"), ("TD-PRJ-2",)),
        (ADMIN_USER, ADMIN_PASS, ("TD-PRJ-1", "TD-PRJ-2"), ()),
    ):
        sc = screen(acc, fresh_password=password)
        assert sc.page.url.rstrip("/").endswith("/projects"), f"{acc} 첫 화면 {sc.page.url}"
        sc.see("사업 목록", *(name[k] for k in see))
        sc.not_see(*(name[k] for k in hidden))
        sc.done()


def test_UC_004_S03_직접_주소_접근(target, s0, screen):
    """V1 이 플랫폼 설정 주소·TD-PRJ-2 주소 → 서버 거절 (AC-004-2)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    assert target.get("/api/admin/organizations", headers=v1).status_code == 403
    assert target.get("/api/ai/settings", headers=v1).status_code in (403, 404)
    assert target.get(f"/api/projects/{s0.ids['TD-PRJ-2']}", headers=v1).status_code in (403, 404)
    assert target.get(f"/api/projects/{s0.ids['TD-PRJ-2']}/progress", headers=v1).status_code in (
        403,
        404,
    )
    _ui_UC_004_S03(screen, s0)


def test_UC_004_S04_비밀번호_변경(target, s0):
    """변경 → 옛 비밀번호 거절, 새 비밀번호 성공 (AC-004-3). 끝에 복원한다."""
    user = d.ACCOUNTS["TD-ACC-C1"].username
    h = auth(s0.tokens["TD-ACC-C1"])
    new = PASSWORD + "-2"
    res = target.post(
        "/api/auth/password", json={"currentPassword": PASSWORD, "newPassword": new}, headers=h
    )
    assert res.status_code == 204, res.text
    try:
        assert _login(target, user, PASSWORD).status_code in (401, 403)
        again = _login(target, user, new)
        assert again.status_code == 200
        h2 = auth(again.json()["accessToken"])
    finally:
        back = target.post(
            "/api/auth/password", json={"currentPassword": new, "newPassword": PASSWORD}, headers=h2
        )
        assert back.status_code == 204, back.text
        s0.tokens["TD-ACC-C1"] = s0.login(user, PASSWORD)


def test_UC_004_S05_갱신_토큰_재사용(target, s0):
    """갱신 → 같은 토큰으로 재갱신 → 둘째 거절 (AC-004-4)."""
    login = _login(target, d.ACCOUNTS["TD-ACC-C1"].username, PASSWORD).json()
    first = target.post("/api/auth/refresh", json={"refreshToken": login["refreshToken"]})
    assert first.status_code == 200, first.text
    second = target.post("/api/auth/refresh", json={"refreshToken": login["refreshToken"]})
    assert second.status_code in (401, 403), second.text


def _ui_UC_002_S01(screen, s0):
    """화면: 목록 진척 칸 「-」, 일정 「산출 불가」·고지문, 요구사항·점검표·요청 없음."""
    if not screen:
        return
    sc = screen("TD-ACC-C1")
    pid, name = s0.ids["TD-PRJ-3"], d.PROJECTS["TD-PRJ-3"].name
    sc.open("/projects").see(name)
    row = sc.row(name)
    assert "%" not in row, f"등록 직후 사업의 목록 줄에 비율이 보인다: {row!r}"
    sc.shot("목록")
    sc.open(f"/p/{pid}/schedule").see("산출 불가", "WBS 가 없습니다")
    sc.not_see(re.compile(r"(?<![\d.])0(\.0)?%"))
    sc.shot("일정")
    sc.open(f"/p/{pid}/traceability").see("요구사항이 없습니다")
    sc.shot("요구사항")
    sc.open(f"/p/{pid}/deliverables")
    # 인도 점검표 대신 29110 충족 현황(11-19, 머리 버튼 → 창). WBS 가 없으니 22종 모두 계획 없음
    sc.page.get_by_role("button", name="ISO/IEC 29110 충족 현황").click()
    sc.see("ISO/IEC 29110 산출물 충족 현황", "사업수행계획서", selector='[role="dialog"]')
    rows = sc.page.locator('[role="dialog"] li').filter(has_text="계획 없음")
    assert rows.count() == 22, f"충족 현황 계획 없음 줄 {rows.count()} (기대 22)"
    sc.shot("충족 현황")
    sc.open(f"/p/{pid}/reviews").see("확인 요청이 없습니다")
    sc.done()


def _ui_UC_003_S01(screen, s0):
    """화면: 가입한 계정으로 로그인 → 업체 이름, 목록에 TD-PRJ-1 만, TD-PRJ-2 주소는 거절."""
    if not screen:
        return
    sc = screen("td-v0-s01").expect_denied()
    sc.open("/projects").see(d.PROJECTS["TD-PRJ-1"].name, "총 1건")
    sc.see(d.ORGS["TD-ORG-V1"].name, selector="body")
    sc.not_see(d.PROJECTS["TD-PRJ-2"].name, d.PROJECTS["TD-PRJ-9"].name)
    sc.shot("목록")
    sc.open(f"/p/{s0.ids['TD-PRJ-2']}").see("접근 권한이 없습니다", selector="body")
    assert sc.denied, "화면만 막고 서버가 거절하지 않았다"
    sc.done()


def _ui_UC_004_S03(screen, s0):
    """화면: V1 이 관리 화면·TD-PRJ-2 주소를 직접 열면 권한 없음 화면."""
    if not screen:
        return
    sc = screen("TD-ACC-V1").expect_denied()
    p2 = s0.ids["TD-PRJ-2"]
    for path in ("/admin/accounts", f"/p/{p2}", f"/p/{p2}/dashboard"):
        before = len(sc.denied)
        sc.open(path).see("접근 권한이 없습니다", selector="body")
        # 관리 화면은 역할을 보고 화면이 API 를 부르지 않는다. 서버 거절은 위 API 단언이 본다
        if path.startswith("/p/"):
            assert len(sc.denied) > before, f"{path}: 화면만 막고 서버가 거절하지 않았다"
        sc.shot(path.strip("/").split("/")[0])
    sc.done()
