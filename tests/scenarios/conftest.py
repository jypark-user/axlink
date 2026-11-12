"""IM-007 예제 시나리오 실행 공통 설비.

시나리오 시험은 이름에 시나리오 ID 를 넣는다(`test_UC_001_S01_...`). 실행 뒤
`scripts/verification_records.py record-junit` 가 junit 에서 ID 를 읽어 runs.jsonl 에 옮긴다.

실행 대상은 둘이다.
- 기본: FastAPI TestClient + CI 시험용 DB. 기록 모드 `auto`.
- `AXLINK_TARGET_URL` 이 있으면 그 서버(5174 등)에 HTTP 로 보낸다. 기록 모드 `api`.
  투입 스크립트의 DB 작업은 `AXLINK_DATABASE_URL` 이 그 서버와 같은 전용 시험 DB 를 가리켜야 한다.

같은 모듈의 시나리오는 하나의 S0 위에서 돈다. 상태를 바꾸는 시나리오는 끝에 되돌리거나,
되돌릴 수 없으면 뒤 시나리오가 그 변화에 기대지 않게 쓴다.
"""

from __future__ import annotations

import os

import httpx
import pytest

from tests.conftest import requires_db
from tests.fixtures.im009 import data as d
from tests.fixtures.im009.seed import PASSWORD, Seeder
from tests.scenarios.ui import CHROME, open_ui

TARGET_URL = os.environ.get("AXLINK_TARGET_URL")

pytestmark = requires_db


@pytest.fixture(scope="module")
def target(client):
    """TestClient 또는 실제 서버 클라이언트. 둘 다 `.get/.post/...` 와 `/api/...` 경로를 쓴다."""
    if TARGET_URL:
        with httpx.Client(base_url=TARGET_URL.rstrip("/"), timeout=60) as c:
            yield c
    else:
        yield client


@pytest.fixture(scope="module")
def s0(target):
    """상태 S0. 모듈이 끝나면 지운다."""
    s = Seeder(target)
    try:
        s.s0()
        yield s
    finally:
        s.cleanup()


@pytest.fixture(scope="module")
def ui():
    """원격 대상 + AXLINK_BROWSER_CHROME 일 때만 브라우저. 아니면 None (tests/scenarios/ui.py)."""
    yield from open_ui(TARGET_URL, PASSWORD)


@pytest.fixture
def screen(ui, request, record_property):
    """`screen("TD-ACC-C1")`(또는 아이디) → 그 계정으로 로그인한 화면. 브라우저가 없으면 None."""
    if ui is None:
        return None
    name = request.node.originalname or request.node.name

    def make(acc: str, *, fresh_password: str | None = None):
        """fresh_password 를 주면 새 문맥에서 화면으로 로그인한 직후의 화면을 준다."""
        username = d.ACCOUNTS[acc].username if acc in d.ACCOUNTS else acc
        if fresh_password is not None:
            sc = ui.fresh(username, fresh_password, name)
        else:
            sc = ui.screen(username, name)
        sc.record_property = record_property
        return sc

    return make


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# 명세와 제품이 다른 것으로 확인돼 결함·결정으로 기록한 시나리오. strict 라서 결함이 고쳐져
# 통과하면 「예상 밖 통과(XPASS)」로 CI 가 알린다. 그때 이 표에서 지우고 다시 기록한다.
# 키는 시험 함수 이름, 값은 검증 기록의 결함(DEF-V###)·결정(DEC-##) ID 와 사유다.
KNOWN_FAILURES: dict[str, str] = {
    # A
    # B
    # C
    # 명세 충돌(결정 필요): E6 「항목 n건」이면 중복 두 행이라 2건, S03 기대값은 「1건」(1쌍)
    "test_UC_020_S03_중복_코드": "명세 충돌(결정 필요): 중복 1쌍을 1건(S03)·2건(E6, 제품)",
    # D
    "test_UC_030_S06_가중치_없는_WBS_L2": "DEF-V023 L2 산식이 ARC-016 원칙 1과 충돌(DEC-19)",
    # E
    "test_UC_041_S01_다섯_축_한_화면": "DEC-02 결함이 일반 이슈 처리율에 섞임(7/11). V022 고침",
    "test_UC_041_S02_진척률에서_작업까지": "DEF-V036 격차 경고 기준 DEC-20 대기. 연결 이슈 고침",
    "test_UC_041_S03_L3_추정": "DEF-V037 L3 추정 표시 없음",
    "test_UC_041_S12_WBS_변형": "DEF-V023 L2 산식이 ARC-016 원칙 1과 충돌(DEC-19)",
    "test_UC_042_S01_추천_구성": "DEC-02 결함이 일반 이슈 처리율에 섞임(7/11)",
    "test_UC_043_S01_목록_원천": "DEC-02 결함이 일반 이슈에 섞임(11건)",
    # F
    # G·H
    # HWP·HWPX 는 파일에 쪽 수가 없다(요약 정보 PageCount 0). 표·문단은 통과
    "test_UC_070_S10_HWP_표": "결정 필요: HWP 쪽 수를 못 낸다(명세 「2쪽」)",
    "test_UC_070_S11_HWPX_표": "결정 필요: HWPX 쪽 수를 못 낸다(명세 「2쪽」)",
    "test_UC_060_S02_집계_질문": "DEC-02 결함이 섞여(11건) 9건 문장이 수치 검문에 걸림",
    "test_UC_060_S03_결합": "DEC-02 결함이 섞여(11건) 9건 문장이 수치 검문에 걸림",
}


# 원격 대상(AXLINK_TARGET_URL)에서는 돌 수 없는 시험. 시험 프로세스 안의 설정을 바꾸는데 그 값이
# 대상 서버에 닿지 않는다. 가짜 모델(llm 픽스처)을 쓰는 시험도 같은 이유로 건너뛴다(실모델은 따로)
LOCAL_ONLY: dict[str, str] = {
}


# 원격 대상에서만 드러나는 실패. 프로세스 안 재생기는 어댑터를 통째로 바꿔 오류 문장까지 지어내지만,
# 원격은 실제 어댑터가 HTTP 응답을 읽는다. 시험 프로세스 안 실행에서는 통과하므로 따로 둔다
REMOTE_KNOWN_FAILURES: dict[str, str] = {
}

# 화면 단계에서만 드러나는 실패. API 단언은 통과하므로 브라우저가 있는 원격 실행에만 붙인다
BROWSER_KNOWN_FAILURES: dict[str, str] = {
}

# 이 표시가 붙은 예상 실패는 고친 PR 이 아직 병합 전이다. 통과해도(XPASS) 실패로 보지 않는다
PENDING_FIX = "수정 PR"


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/scenarios/" not in item.nodeid.replace("\\", "/"):
            continue
        if TARGET_URL:
            name = item.originalname or item.name
            # remote_llm 표시가 붙은 시험은 재생 서버의 대본 모델(replay_ollama)로 원격에서도 돈다
            why = LOCAL_ONLY.get(name) or (
                "가짜(대본) 모델은 대상 서버에 닿지 않는다. 실모델 실행으로 본다"
                if "llm" in getattr(item, "fixturenames", ())
                and item.get_closest_marker("remote_llm") is None
                else None
            )
            if why:
                item.add_marker(pytest.mark.skip(reason=f"원격 대상 제외: {why}"))
                continue
        reason = KNOWN_FAILURES.get(item.originalname or item.name)
        if TARGET_URL:
            reason = reason or REMOTE_KNOWN_FAILURES.get(item.originalname or item.name)
        if TARGET_URL and CHROME:
            reason = reason or BROWSER_KNOWN_FAILURES.get(item.originalname or item.name)
        if reason:
            # 수정 PR 이 열린 결함은 그 PR 에서 시험이 통과해도 실패로 보지 않는다. 수정 PR 마다
            # 이 표의 줄을 지우면 이웃한 줄끼리 병합 충돌이 난다. 수정 PR 이 병합되면 줄을 지운다
            item.add_marker(pytest.mark.xfail(strict=PENDING_FIX not in reason, reason=reason))
