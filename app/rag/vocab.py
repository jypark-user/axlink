"""답변 재료에 들어가는 상태·심각도 코드를 발주기관 어휘로 (CLAUDE.md 설계 제약 9).

표준 모델은 상태를 코드(IN_PROGRESS 등)로 둔다. 화면은 frontend/src/lib/labels.ts 로 바꿔
보이는데, AI 답의 재료(집계 줄·목록 표)는 코드를 그대로 받아 모델이 「IN_PROGRESS 상태」라고
답했다(UC-060-S16 실모델). 화면과 같은 말을 쓰도록 같은 표를 둔다. 바꾸면 labels.ts 도 같이.
"""

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


def word(value: object) -> object:
    """코드면 발주기관 어휘로, 아니면 그대로. 사업명·담당자 같은 값은 건드리지 않는다."""
    if isinstance(value, str):
        return WORDS.get(value, value)
    return value
