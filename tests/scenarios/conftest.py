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
from tests.fixtures.im009.seed import Seeder

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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# 명세와 제품이 다른 것으로 확인돼 결함·결정으로 기록한 시나리오. strict 라서 결함이 고쳐져
# 통과하면 「예상 밖 통과(XPASS)」로 CI 가 알린다. 그때 이 표에서 지우고 다시 기록한다.
# 키는 시험 함수 이름, 값은 검증 기록의 결함(DEF-V###)·결정(DEC-##) ID 와 사유다.
KNOWN_FAILURES: dict[str, str] = {
    # A
    # B
    "test_UC_010_S02_Redmine_REST_비활성": "DEF-V014 REST 비활성 안내 구분 없음",
    # C
    "test_UC_021_S03_돌려보내기": "DEF-V034 기준선 돌려보냄이 활동 기록에 없음",
    # D
    "test_UC_030_S02_업로드_계획서": "DEF-V019 업로드 계획서 WBS 미인식",
    "test_UC_030_S06_가중치_없는_WBS_L2": "DEF-V023 L2 추정 없음",
    "test_UC_031_S04_반려_뒤_재제출_이력": "DEF-V020 점검표 버전 이력·반려 사유 없음",
    "test_UC_030_S04_머리글_없음": "DEF-V038 머리글 없는 WBS 가 이전 기준선을 지운다",
    # E
    "test_UC_040_S01_세_사업_목록": "DEF-V021 목록 진척·편차 칸 없음",
    "test_UC_040_S03_현황과_일치": "DEF-V021 목록 진척 칸 없음",
    "test_UC_041_S01_다섯_축_한_화면": "DEF-V022 위험 처리율 지표 없음 + DEC-02 결함 분리",
    "test_UC_041_S02_진척률에서_작업까지": "DEF-V036 일정 줄 작업 단위 격차 경고·연결 이슈 없음",
    "test_UC_041_S03_L3_추정": "DEF-V037 L3 추정 표시 없음",
    "test_UC_041_S12_WBS_변형": "DEF-V023 L2 추정 없음",
    "test_UC_042_S01_추천_구성": "DEC-02 결함이 일반 이슈 처리율에 섞임(7/11)",
    "test_UC_043_S01_목록_원천": "DEC-02 결함이 일반 이슈에 섞임(11건)",
    # F
    "test_UC_050_S01_WBS_작업_요청": "DEF-V027 요청 저장 상태에 연결 이슈·보고 진척률 없음",
    "test_UC_050_S02_이슈_리스크_산출물_요청": "DEF-V026 요청 저장 상태에 우선순위·관련 지표 없음",
    "test_UC_051_S01_조치_뒤_보고": "DEF-V027 변경 내역에 연결 이슈·보고 진척률 없음",
    # G·H
    "test_UC_060_S02_집계_질문": "DEC-02 결함이 섞여(11건) 9건 문장이 수치 검문에 걸림",
    "test_UC_060_S15_XLSX_시트_행_위치": "DEF-V031 저장소 WBS.xlsx 미색인",
}


# 원격 대상(AXLINK_TARGET_URL)에서는 돌 수 없는 시험. 시험 프로세스 안의 설정을 바꾸는데 그 값이
# 대상 서버에 닿지 않는다. 가짜 모델(llm 픽스처)을 쓰는 시험도 같은 이유로 건너뛴다(실모델은 따로)
LOCAL_ONLY: dict[str, str] = {
    "test_UC_031_S02_설정_경로_커밋": "수집 파일 경로(서버 설정)를 시험 안에서 바꾼다. DEF-V012",
}


# 원격 대상에서만 드러나는 실패. 프로세스 안 재생기는 어댑터를 통째로 바꿔 오류 문장까지 지어내지만,
# 원격은 실제 어댑터가 HTTP 응답을 읽는다. 시험 프로세스 안 실행에서는 통과하므로 따로 둔다
REMOTE_KNOWN_FAILURES: dict[str, str] = {
}

# 이 표시가 붙은 예상 실패는 고친 PR 이 아직 병합 전이다. 통과해도(XPASS) 실패로 보지 않는다
PENDING_FIX = "수정 PR"


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/scenarios/" not in item.nodeid.replace("\\", "/"):
            continue
        if TARGET_URL:
            name = item.originalname or item.name
            why = LOCAL_ONLY.get(name) or (
                "가짜(대본) 모델은 대상 서버에 닿지 않는다. 실모델 실행으로 본다"
                if "llm" in getattr(item, "fixturenames", ()) else None
            )
            if why:
                item.add_marker(pytest.mark.skip(reason=f"원격 대상 제외: {why}"))
                continue
        reason = KNOWN_FAILURES.get(item.originalname or item.name)
        if TARGET_URL:
            reason = reason or REMOTE_KNOWN_FAILURES.get(item.originalname or item.name)
        if reason:
            # 수정 PR 이 열린 결함은 그 PR 에서 시험이 통과해도 실패로 보지 않는다. 수정 PR 마다
            # 이 표의 줄을 지우면 이웃한 줄끼리 병합 충돌이 난다. 수정 PR 이 병합되면 줄을 지운다
            item.add_marker(pytest.mark.xfail(strict=PENDING_FIX not in reason, reason=reason))
