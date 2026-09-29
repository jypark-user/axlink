"""한국어 조사 붙이기. "열린 이슈 수은(는)" 같은 문장을 화면에 내지 않기 위한 것이다.

받침이 있으면 은·이·을·과, 없으면 는·가·를·와. 마지막 글자가 한글이면 종성으로, 숫자면
읽는 소리(영·일·이·삼…)로, 그 밖(영문·기호)은 받침 없는 쪽으로 본다. 영문 약자(WBS, PR)는
읽는 법이 갈려 어느 쪽도 완벽하지 않다. 라벨은 대개 한글로 끝나므로 그쪽에 맞췄다.
"""

_HANGUL_START, _HANGUL_END = 0xAC00, 0xD7A3
# 0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔 은 받침이 있고 2 이, 4 사, 5 오, 9 구 는 없다
_DIGIT_FINAL = {"0", "1", "3", "6", "7", "8"}
_PAIRS = {"은": "는", "이": "가", "을": "를", "과": "와"}


def has_final(word: str) -> bool:
    text = word.rstrip(" )]」』\"'")
    if not text:
        return False
    last = text[-1]
    code = ord(last)
    if _HANGUL_START <= code <= _HANGUL_END:
        return (code - _HANGUL_START) % 28 != 0
    if last.isdigit():
        return last in _DIGIT_FINAL
    return False


def particle(word: str, with_final: str) -> str:
    """조사 하나를 고른다. with_final 은 받침 있을 때의 꼴(은·이·을·과)."""
    if with_final not in _PAIRS:
        raise ValueError(f"모르는 조사: {with_final}")
    return with_final if has_final(word) else _PAIRS[with_final]


def attach(word: str, with_final: str) -> str:
    """단어에 조사를 붙인 문자열. attach("이슈 수", "은") → "이슈 수는"."""
    return word + particle(word, with_final)
