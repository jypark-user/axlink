"""한국어 조사 (QUR.WEB.002). "열린 이슈 수은(는)" 을 화면에 내지 않는다."""

from app.common import korean


def test_받침_유무로_조사를_고른다():
    assert korean.attach("열린 이슈 수", "은") == "열린 이슈 수는"
    assert korean.attach("요구사항 이행률", "은") == "요구사항 이행률은"
    assert korean.attach("진척률", "이") == "진척률이"
    assert korean.attach("산출물 승인률", "을") == "산출물 승인률을"
    assert korean.attach("이슈 건수", "과") == "이슈 건수와"


def test_숫자와_영문_끝도_읽는_소리로_본다():
    assert korean.attach("41", "은") == "41은"
    assert korean.attach("73.9", "은") == "73.9는"
    assert korean.attach("100", "은") == "100은"
    assert korean.attach("WBS", "은") == "WBS는"
    assert korean.attach("이슈 수)", "은") == "이슈 수)는"  # 닫는 괄호는 건너뛴다
