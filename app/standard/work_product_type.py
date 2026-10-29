"""산출물 22종. ISO/IEC 29110-5-1-2 Basic Profile 관리객체 (SWFR.PIP.001).

값과 화면 이름을 한 곳에 둔다. 프런트가 라벨을 따로 들고 있으면 둘이 어긋나고,
발주기관 화면에 영문 코드가 그대로 노출되는 사고가 난다.
표는 파일럿 02-logical-datamodel.md §산출물 22종 그대로다.
"""

DISPLAY_NAMES: dict[str, str] = {
    "STATEMENT_OF_WORK": "과업지시서",
    "PROJECT_PLAN": "사업수행계획서",
    "PROGRESS_STATUS_RECORD": "진척 보고",
    "MEETING_RECORD": "회의록",
    "CHANGE_REQUEST": "변경 요청서",
    "CORRECTION_REGISTER": "시정조치 대장",
    "ACCEPTANCE_RECORD": "검수확인서",
    "PROJECT_REPOSITORY": "사업 저장소",
    "REPOSITORY_BACKUP": "저장소 백업",
    "REQUIREMENTS_SPEC": "요구사항정의서",
    "TRACEABILITY_RECORD": "요구사항추적표",
    "SOFTWARE_DESIGN": "설계서",
    "TEST_CASES_PROCEDURES": "시험계획서",
    "SOFTWARE_COMPONENT": "프로그램 구성요소",
    "SOFTWARE": "통합 소프트웨어",
    "TEST_REPORT": "시험결과서",
    "PRODUCT_OPERATION_GUIDE": "운영지침서",
    "SOFTWARE_USER_DOC": "사용자취급설명서",
    "SOFTWARE_CONFIGURATION": "소프트웨어 형상",
    "MAINTENANCE_DOC": "유지보수문서",
    "VERIFICATION_RESULTS": "검토 결과",
    "VALIDATION_RESULTS": "확인 결과",
}


# 활동 구분. V1 시드가 데모 사업에 넣은 표와 같다. 사업을 새로 만들 때 이 표로
# 22개 항목을 먼저 만든다(ARC-005 4절). 활동은 유형이 정한다. 사람이 고르지 않고,
# 수집·문서 확정이 새 버전을 만들 때도 이 표에서 다시 읽는다.
ACTIVITIES: dict[str, tuple[str | None, str | None]] = {
    "STATEMENT_OF_WORK": ("PM_1", None),
    "PROJECT_PLAN": ("PM_1", None),
    "PROGRESS_STATUS_RECORD": ("PM_2", None),
    "MEETING_RECORD": ("PM_2", None),
    "CHANGE_REQUEST": ("PM_2", None),
    "CORRECTION_REGISTER": ("PM_3", None),
    "ACCEPTANCE_RECORD": ("PM_4", None),
    "PROJECT_REPOSITORY": ("PM_1", None),
    "REPOSITORY_BACKUP": ("PM_2", None),
    "VERIFICATION_RESULTS": ("PM_3", None),
    "VALIDATION_RESULTS": ("PM_4", None),
    "REQUIREMENTS_SPEC": (None, "SI_2"),
    "TRACEABILITY_RECORD": (None, "SI_2"),
    "SOFTWARE_DESIGN": (None, "SI_3"),
    "TEST_CASES_PROCEDURES": (None, "SI_3"),
    "SOFTWARE_COMPONENT": (None, "SI_4"),
    "SOFTWARE": (None, "SI_5"),
    "TEST_REPORT": (None, "SI_5"),
    "PRODUCT_OPERATION_GUIDE": (None, "SI_5"),
    "SOFTWARE_USER_DOC": (None, "SI_5"),
    "SOFTWARE_CONFIGURATION": (None, "SI_6"),
    "MAINTENANCE_DOC": (None, "SI_6"),
}


def activity_of(product_type: str) -> tuple[str | None, str | None]:
    """유형의 (PM 활동, SI 활동). 모르는 유형은 스키마 CHECK 가 막지만, 활동 제약
    (둘 중 하나는 있어야 한다)에 먼저 걸리지 않게 계획 단계로 둔다."""
    return ACTIVITIES.get(product_type, ("PM_1", None))


def display_name(product_type: str) -> str:
    """모르는 유형이 와도 화면이 비지 않게 코드를 그대로 돌려준다."""
    return DISPLAY_NAMES.get(product_type, product_type)
