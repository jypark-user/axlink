"""이슈 → WBS 항목 연결 규칙 (ARC-016 3-4). 정확히 맞는 번호 토큰만 잇는다."""

from app.dashboard import wbs_issue

IDS = {"3.1", "3.2", "3.3"}


def test_라벨_세_가지_꼴을_읽는다():
    for name in ("WBS: 3.2", "wbs-3.2", "3.2"):
        assert wbs_issue.assign(IDS, "로그인 화면", {"labels": [{"name": name}]}) == "3.2", name


def test_제목_앞머리를_읽는다():
    assert wbs_issue.assign(IDS, "[3.1] 요구사항 정리", None) == "3.1"
    assert wbs_issue.assign(IDS, "3.3 구현 착수", None) == "3.3"


def test_Redmine_커스텀_필드_WBS_ID를_읽는다():
    payload = {"custom_fields": [{"id": 2, "name": "WBS ID", "value": "3.2"}]}
    assert wbs_issue.assign(IDS, "외부 연계 규격 협의", payload) == "3.2"


def test_번호_집합에_없으면_잇지_않는다():
    assert wbs_issue.assign(IDS, "[4.1] 다음 단계", None) is None
    assert wbs_issue.assign(IDS, "로그인", {"labels": [{"name": "WBS: 9.9"}]}) is None


def test_서로_다른_번호가_둘이면_잇지_않는다():
    payload = {"labels": [{"name": "WBS: 3.1"}, {"name": "WBS: 3.2"}]}
    assert wbs_issue.assign(IDS, "정리", payload) is None


def test_같은_번호가_여러_곳에_있으면_하나로_잇는다():
    payload = {"labels": [{"name": "WBS: 3.2"}]}
    assert wbs_issue.assign(IDS, "[3.2] 설계 검토", payload) == "3.2"


def test_본문이나_비슷한_글자는_근거가_아니다():
    # 본문 참조, 번호가 섞인 문장, 요구사항 코드는 추측해서 잇지 않는다
    assert wbs_issue.assign(IDS, "버전 3.2.1 배포", None) is None
    assert wbs_issue.assign(IDS, "설계 3.2 참고", None) is None
    payload = {"labels": [{"name": "v3.2"}], "custom_fields": [{"name": "요구사항 ID", "value": "3.2"}]}
    assert wbs_issue.assign(IDS, "정리", payload) is None
