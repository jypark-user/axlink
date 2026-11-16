"""업무 판단 권한표 (DEC-05, ARC-032).

플랫폼 관리자(SUPER_ADMIN)는 계정·조직·사업·연결·수집 같은 플랫폼 관리를 맡는다. 발주기관의
판단(확정·돌려보냄·상태 지정·승인·반려·확인 요청·확인완료·완료 확인)과 용역사의 행위(명세서
등록·정리·제출, 조치·완료 보고)는 그 역할만 한다. 관리자가 대신하면 「발주기관이 확인했다」는
기록이 사실이 아니게 된다.

행위마다 허용 역할을 여기 한 곳에 둔다. 서비스는 require() 로 묻고, 화면은 같은 표를 따른다.
사업 접근(그 사업의 발주기관인가, 배정된 용역사인가)은 서비스가 따로 본다.

이 표가 바뀌어도 이미 남은 기록은 고치지 않는다. 예전에 관리자가 확정한 기준선은 확정 역할
(SUPER_ADMIN)을 그대로 지니고 화면에 「(관리자)」로 보인다.
"""

from app.auth.models import AuthPrincipal
from app.common import errors

CLIENT = "CLIENT"
CONTRACTOR = "CONTRACTOR"
SUPER_ADMIN = "SUPER_ADMIN"

# 행위 → (허용 역할, 거절 문구)
DUTIES: dict[str, tuple[tuple[str, ...], str]] = {
    # UC-020 요구사항 명세서
    "BASELINE_AUTHOR": ((CONTRACTOR,), "요구사항 명세서 등록·정리·제출은 용역사가 합니다."),
    # UC-021 요구사항 목록 확정·돌려보냄
    "BASELINE_CONFIRM": ((CLIENT,), "요구사항 목록 확정과 돌려보내기는 발주기관이 합니다."),
    # UC-023 요구사항 상태 지정·되돌림
    "REQUIREMENT_DECIDE": ((CLIENT,), "요구사항 상태 지정은 발주기관이 합니다."),
    # UC-031 산출물 승인·반려
    "PRODUCT_APPROVE": ((CLIENT,), "산출물 승인·반려는 발주기관이 합니다."),
    # UC-050 확인 요청 등록
    "REVIEW_REQUEST": ((CLIENT,), "발주기관만 확인을 요청할 수 있습니다."),
    # UC-052 확인완료·다시 요청
    "REVIEW_CLOSE": ((CLIENT,), "확인완료와 다시 요청은 그 사업의 발주기관만 할 수 있습니다."),
    # UC-032 작업 완료 확인 요청·확인·철회
    "COMPLETION_CONFIRM": ((CLIENT,), "작업 완료 확인은 그 사업의 발주기관만 할 수 있습니다."),
    # UC-051 조치 보고 · UC-032 완료 보고
    "REVIEW_REPORT": ((CONTRACTOR,), "조치 보고는 용역사가 합니다."),
}

ADMIN_NOTE = " 플랫폼 관리자는 발주기관·용역사의 업무 판단을 대신하지 않습니다."


def allowed(principal: AuthPrincipal, duty: str) -> bool:
    return principal.role in DUTIES[duty][0]


def require(principal: AuthPrincipal, duty: str, message: str | None = None) -> None:
    """허용 역할이 아니면 403. message 를 주면 표의 문구 대신 쓴다(같은 행위의 세부 동작)."""
    roles, default = DUTIES[duty]
    message = message or default
    if principal.role in roles:
        return
    if principal.role == SUPER_ADMIN:
        message += ADMIN_NOTE
    raise errors.ApiError(403, "FORBIDDEN", message)
