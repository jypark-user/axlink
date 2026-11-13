"""답변 재료에 들어가는 상태·심각도 코드를 발주기관 어휘로 (CLAUDE.md 설계 제약 9).

표준 모델은 상태를 코드(IN_PROGRESS 등)로 둔다. 화면은 frontend/src/lib/labels.ts 로 바꿔
보이는데, AI 답의 재료(집계 줄·목록 표)는 코드를 그대로 받아 모델이 「IN_PROGRESS 상태」라고
답했다(UC-060-S16 실모델). 화면과 같은 말을 쓰도록 같은 표를 둔다. 바꾸면 labels.ts 도 같이.
"""

import re

WORDS: dict[str, str] = {
    # 이슈·리스크
    "OPEN": "열림",
    "IN_PROGRESS": "진행중",
    "RESOLVED": "해결",
    "CLOSED": "종료",
    "MITIGATING": "완화중",
    # 요구사항
    "DEFINED": "정의",
    "DESIGNED": "설계",
    "IMPLEMENTED": "구현",
    "VERIFIED": "검증",
    "ACCEPTED": "인수",
    "REJECTED": "반려",
    # 산출물
    "DRAFT": "초안",
    "SUBMITTED": "제출",
    "APPROVED": "승인",
    # 심각도
    "BLOCKER": "치명",
    "CRITICAL": "심각",
    "MAJOR": "중대",
    "MINOR": "경미",
    "TRIVIAL": "사소",
    "HIGH": "높음",
    "MEDIUM": "보통",
    "LOW": "낮음",
}


# 지표 산출 근거 문구에 괄호로 붙은 코드. 「검증완료(VERIFIED)」의 (VERIFIED) 처럼 앞말이 이미
# 발주기관 어휘라 코드만 뺀다. (WBS)·(L1) 처럼 화면에서도 쓰는 말은 남긴다
_BASIS_CODES = frozenset(WORDS) | {"TESTS", "NONE"}
_PAREN_CODE = re.compile(r"\(([A-Z_]+)\)")


def plain(text: str | None) -> str | None:
    """산출 근거 문구에서 상태 코드 괄호를 뺀다(DEF-V061). 화면 설명과 AI 답이 같은 문구를 쓴다."""
    if not text:
        return text
    return _PAREN_CODE.sub(lambda m: "" if m.group(1) in _BASIS_CODES else m.group(0), text)


def word(value: object) -> object:
    """코드면 발주기관 어휘로, 아니면 그대로. 사업명·담당자 같은 값은 건드리지 않는다."""
    if isinstance(value, str):
        return WORDS.get(value, value)
    return value
