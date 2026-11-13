"""고정 응답 모드 경고의 화면 확인 (AC-061-5, DEC-23).

DEC-23(2026-11-12 사용자 결정): 같은 배포 이미지를 격리 시험 인스턴스에 고정 응답 모드
(AXLINK_LLM_PROVIDER=fake)로 띄워 질의 화면의 경고를 브라우저로 본다. 5174 의 모델 설정은
바꾸지 않는다. 격리 인스턴스는 `var/verify/iso` 에서 띄운다(저장소 밖).

    AXLINK_FIXED_MODE=1 AXLINK_TARGET_URL=http://127.0.0.1:5179/ax-link \
    AXLINK_FIXED_USER=<발주기관 아이디> AXLINK_FIXED_PASS=<비밀번호> \
    AXLINK_BROWSER_CHROME=<chrome.exe> python -m pytest tests/scenarios/test_fixed_mode.py

UC-061-S01 의 경우(variant) 「격리-고정응답」으로 기록된다. 5174 에서 도는 본 경우와 둘 다
최신 실행이 통과해야 시나리오가 통과다.
"""

import os
import uuid

import httpx
import pytest

from tests.scenarios.conftest import TARGET_URL
from tests.scenarios.ui import CHROME

pytestmark = pytest.mark.skipif(
    not (os.environ.get("AXLINK_FIXED_MODE") == "1" and TARGET_URL and CHROME),
    reason="격리 인스턴스(고정 응답 모드)와 브라우저가 있을 때만 돈다(DEC-23)",
)


@pytest.mark.parametrize("where", ["격리-고정응답"])
def test_UC_061_S01_고정_응답_경고(where, ui, request, record_property):
    user, password = os.environ["AXLINK_FIXED_USER"], os.environ["AXLINK_FIXED_PASS"]
    api = httpx.Client(base_url=TARGET_URL.rstrip("/"), timeout=30)
    token = api.post("/api/auth/login", json={"username": user, "password": password}).json()[
        "accessToken"
    ]
    h = {"Authorization": f"Bearer {token}"}

    runtime = api.get("/api/ai/runtime", headers=h).json()
    assert runtime["fixed"] is True, runtime

    projects = api.get("/api/projects", headers=h).json()
    items = projects["content"]
    if items:
        pid = items[0]["id"]
    else:
        res = api.post(
            "/api/projects",
            headers=h,
            json={
                "name": "격리 시험 사업",
                "startDate": "2026-09-01",
                "endDate": "2026-11-30",
                "description": "고정 응답 모드 경고 확인용(DEC-23)",
                "deletePassword": uuid.uuid4().hex,
            },
        )
        assert res.status_code in (200, 201), res.text
        pid = res.json()["id"]

    sc = ui.fresh(user, password, request.node.originalname)
    sc.record_property = record_property
    sc.open(f"/p/{pid}/ask").see("고정 응답(시험용) 모드입니다", selector="body")
    sc.done()
