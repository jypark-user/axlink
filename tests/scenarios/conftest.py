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
    "test_UC_001_S06_비밀번호_재설정": "DEF-V002 관리자 비밀번호 재설정 API 없음 (수정 PR #207)",
    "test_UC_002_S01_등록_직후_상태": "DEF-V003 재료 없는 사업 진척 0.0% (정책 확인 DEC 후보 19)",
    "test_UC_002_S03_기간_역순_중복_이름": "DEF-V004 같은 이름 사업 500 (수정 PR #205)",
    "test_UC_002_S04_종료_처리": "DEF-V005 사업 종료 처리 없음 (수정 PR #210)",
    "test_UC_003_S02_취소된_링크": "DEF-V006 초대 취소 없음 (수정 PR #211)",
    "test_UC_003_S03_대표사의_권한_확대_시도": "DEF-V006 초대 목록 API 없음(405) (수정 PR #211)",
    # B
    "test_UC_010_S02_Redmine_REST_비활성": "DEF-V014 REST 비활성 안내 구분 없음",
    "test_UC_011_S02_변경_없는_증분": "DEF-V008 신규·갱신이 재승격 수 (수정 PR #216)",
    "test_UC_011_S05b_필수_대상_권한_없음": "DEF-V009 GitHub 이슈 필수 아님 (수정 PR #215)",
    "test_UC_011_S11_GitHub_종류별_필드": "DEF-V010 PR 본문 Closes #n 미연결",
    "test_UC_011_S12_Redmine_종류별_필드": "DEF-V011 Redmine 버전 미승격 (수정 PR #217)",
    "test_UC_012_S04_WBS_경로_변경": "DEF-V012 수집 파일 경로가 서버 전역",
    # C
    "test_UC_020_S01_표_형식_명세서_등록_제출": "DEF-V015 상위 코드 SR.PORT.01 자리수 (명세 확인)",
    "test_UC_020_S09_명세서_문서_삭제_시도": "DEF-V016 명세서 문서 삭제 허용 (수정 PR #219)",
    "test_UC_021_S03_돌려보내기": "DEF-V034 기준선 돌려보냄이 활동 기록에 없음",
    "test_UC_021_S07_확정_뒤_재수집": "DEF-V018 확정 뒤 출처 이슈 처리 (정책 확인)",
    "test_UC_022_S04_같은_번호_다른_연결": "DEF-V017 TD-CMT-4 → G3 기대가 출처 이슈 정책과 충돌",
    "test_UC_022_S08_구조적_긍정": "DEF-V010 PR 본문 Closes #n 미연결",
    # D
    "test_UC_030_S02_업로드_계획서": "DEF-V019 업로드 계획서 WBS 미인식",
    "test_UC_030_S06_가중치_없는_WBS_L2": "DEF-V023 L2 추정 없음",
    "test_UC_031_S04_반려_뒤_재제출_이력": "DEF-V020 점검표 버전 이력·반려 사유 없음",
    "test_UC_030_S04_머리글_없음": "DEF-V038 머리글 없는 WBS 가 이전 기준선을 지운다",
    "test_UC_032_S05_계획서_교체_뒤": "DEF-V039 완료 확인이 수집 뒤 계획서를 다시 읽지 않는다",
    "test_UC_032_S06_요청_뒤_변경": "DEF-V039 완료 확인이 수집 뒤 계획서를 다시 읽지 않는다",
    # E
    "test_UC_040_S01_세_사업_목록": "DEF-V021 목록 진척·편차 칸 없음",
    "test_UC_040_S03_현황과_일치": "DEF-V021 목록 진척 칸 없음",
    "test_UC_041_S01_다섯_축_한_화면": "DEF-V022 위험 처리율 지표 없음 + DEC-02 결함 분리",
    "test_UC_041_S02_진척률에서_작업까지": "DEF-V036 일정 줄 작업 단위 격차 경고·연결 이슈 없음",
    "test_UC_041_S03_L3_추정": "DEF-V037 L3 추정 표시 없음",
    "test_UC_041_S04_재료_없음": "DEF-V003 재료 없는 사업 진척 0.0% (정책 확인)",
    "test_UC_041_S12_WBS_변형": "DEF-V023 L2 추정 없음",
    "test_UC_042_S01_추천_구성": "DEC-02 결함이 일반 이슈 처리율에 섞임(7/11)",
    "test_UC_043_S01_목록_원천": "DEC-02 결함이 일반 이슈에 섞임(11건)",
    "test_UC_043_S02_트래커_버전": "DEF-V024 트래커·커스텀 필드 미표시 (#225) + DEF-V011 (#217)",
    "test_UC_043_S03_번호_겹침": "DEF-V017 G3 는 S0 에서 출처 이슈 (명세 확인)",
    # F
    "test_UC_050_S01_WBS_작업_요청": "DEF-V027 요청 저장 상태에 연결 이슈·보고 진척률 없음",
    "test_UC_050_S02_이슈_리스크_산출물_요청": "DEF-V026 요청 저장 상태에 우선순위·관련 지표 없음",
    "test_UC_051_S01_조치_뒤_보고": "DEF-V027 변경 내역에 연결 이슈·보고 진척률 없음",
    "test_UC_051_S03a_발주기관_공백_보고": "DEF-V028 공백 보고 수락 (수정 PR #226)",
    "test_UC_053_S03_활동_기록": "DEF-V029 수집이 활동 기록에 없음 (수정 PR #223)",
    # G·H
    "test_UC_060_S02_집계_질문": "DEC-02 결함이 섞여(11건) 9건 문장이 수치 검문에 걸림",
    "test_UC_060_S10_모델_장애": "DEF-V035 모델 장애 때 「쓸 수 없음」 안내 없이 일반 오류",
    "test_UC_060_S14_DOCX_문단_위치": "DEF-V032 DOCX 출처 위치(절·문단) 비어 있음",
    "test_UC_060_S15_XLSX_시트_행_위치": "DEF-V031 저장소 WBS.xlsx 미색인",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/scenarios/" not in item.nodeid.replace("\\", "/"):
            continue
        reason = KNOWN_FAILURES.get(item.originalname or item.name)
        if reason:
            item.add_marker(pytest.mark.xfail(strict=True, reason=reason))
