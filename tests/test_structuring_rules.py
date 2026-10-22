"""문서 정형화 규칙 (SWFR.CON.007 · SWFR.PIP.001). DB 도 모델도 없이 돈다.

여기서 나오는 코드·제목·중요도는 문서 글자를 옮긴 것이어야 한다. 규칙이 지어낸 것이
하나라도 있으면 그 시험이 떨어져야 한다.
"""

from pathlib import Path

from app.document import structuring as s

IM001 = Path(__file__).resolve().parent.parent / "docs/10-requirements/IM-001-요구사항정의서.md"


def test_요구사항정의서에서_41건이_그대로_나온다():
    text = IM001.read_text(encoding="utf-8")
    reqs = s.extract_requirements(text)
    assert len(reqs) == 41
    assert reqs[0].code == "SWFR.CON.001"
    assert reqs[0].title.startswith("커넥터는 공통 인터페이스를 구현하며")
    assert reqs[-1].code == "SER.SEC.003"
    assert {r.priority for r in reqs} == {"MUST"}  # 문서의 중요도가 전부 "필수" 다
    assert len({r.code for r in reqs}) == 41  # 같은 코드가 뒤 표(시나리오 연계)에 또 나와도 한 번


def test_표_머리행으로_열을_정한다():
    text = (
        "| ID | 요구사항명 | 설명 | 우선순위 |\n"
        "|---|---|---|---|\n"
        "| REQ-001 | 로그인 | 아이디와 비밀번호로 들어간다 | 상 |\n"
        "| REQ-002 | 로그아웃 | 세션을 끝낸다 | 하 |\n"
        "| 비고 | 표 밖 설명 | 코드가 아니다 | |\n"
    )
    reqs = s.extract_requirements(text)
    assert [(r.code, r.title, r.body, r.priority) for r in reqs] == [
        ("REQ-001", "로그인", "아이디와 비밀번호로 들어간다", "MUST"),
        ("REQ-002", "로그아웃", "세션을 끝낸다", "COULD"),
    ]


def test_머리행_없는_표는_첫_열이_코드다():
    text = "| FR-01 | 조회 |\n| FR-02 | 등록 |\n"
    reqs = s.extract_requirements(text)
    assert [r.code for r in reqs] == ["FR-01", "FR-02"]
    assert reqs[0].body == "조회"  # 본문 열이 없으면 제목이 본문이다


def test_코드_열이_없는_표는_요구사항이_아니다():
    text = "| 항목 | 내용 |\n|---|---|\n| 대표 형상관리 | GitHub |\n"
    assert s.extract_requirements(text) == []


def test_표가_없으면_줄머리_코드를_읽는다():
    text = (
        "1. 개요\n\n"
        "[SWFR.CON.001] 커넥터 공통 인터페이스\n"
        "신규 도구는 구현체 추가만으로 붙는다.\n"
        "두 줄째 설명.\n\n"
        "SWFR.CON.002: 매핑 설정화\n"
        "## 다음 절\n"
        "SWFR.CON.001 다시 나온 코드는 무시한다\n"
    )
    reqs = s.extract_requirements(text)
    assert [r.code for r in reqs] == ["SWFR.CON.001", "SWFR.CON.002"]
    assert reqs[0].title == "커넥터 공통 인터페이스"
    assert reqs[0].body == "신규 도구는 구현체 추가만으로 붙는다. 두 줄째 설명."
    assert reqs[1].body == "매핑 설정화"


def test_표가_있으면_줄_규칙은_돌지_않는다():
    """표를 설명하는 문장이 요구사항으로 섞이면 건수가 부풀어 오른다."""
    text = (
        "SWFR.CON.009 표 밖에 적힌 줄\n\n"
        "| ID | 요구사항 |\n|---|---|\n| SWFR.CON.001 | 표 안 |\n"
    )
    assert [r.code for r in s.extract_requirements(text)] == ["SWFR.CON.001"]


def test_중요도_표기를_MoSCoW_로_옮긴다():
    assert s.priority_of("필수") == "MUST"
    assert s.priority_of("High") == "MUST"
    assert s.priority_of("권장") == "SHOULD"
    assert s.priority_of("선택") == "COULD"
    assert s.priority_of("보류") == "WONT"
    assert s.priority_of("") == "SHOULD"
    assert s.priority_of("알 수 없는 말") == "SHOULD"


def test_긴_요구사항은_제목만_줄이고_본문은_남긴다():
    long = "가" * 150
    text = f"| ID | 요구사항 |\n|---|---|\n| REQ-001 | {long} |\n"
    req = s.extract_requirements(text)[0]
    assert len(req.title) <= s.MAX_TITLE_CHARS + 1
    assert req.body == long


def test_유형은_파일명과_문서_머리의_단서로_고른다():
    guess = s.classify_type("회의록_0901.docx", "회의 일시 2026-09-01\n참석자 김, 이\n협의 내용")
    assert guess.decided and guess.product_type == "MEETING_RECORD"
    assert 0 < guess.confidence <= 0.95


def test_요구사항_표가_많으면_요구사항정의서로_기운다():
    text = IM001.read_text(encoding="utf-8")
    guess = s.classify_type("IM-001.docx", text, requirement_count=41)
    assert guess.product_type == "REQUIREMENTS_SPEC"


def test_단서가_없으면_정하지_않는다():
    guess = s.classify_type("memo.pdf", "특별한 말이 없는 본문이다.")
    assert not guess.decided and guess.product_type is None and guess.confidence == 0.0


def test_단서가_엇비슷하면_정하지_않는다():
    """1·2위가 붙어 있으면 사람이 고른다. 틀린 확신보다 빈칸이 낫다."""
    guess = s.classify_type("x.docx", "시험계획서 시험결과서 시험계획서 시험결과서")
    assert not guess.decided


def test_제목_버전_작성일은_문서_머리에서_읽는다():
    text = IM001.read_text(encoding="utf-8")
    assert s.guess_title(text) == "AX Link 요구사항정의서 (IM-001)"
    assert s.guess_version(text) == "0.4"
    assert s.guess_authored_date(text) == "2026-08-27"


def test_첫_줄이_길면_제목으로_삼지_않는다():
    assert s.guess_title("가" * 200 + "\n다음 줄") is None
    assert s.guess_title("| 표 | 부터 |\n") is None


def test_모델_답에서_코드_하나만_받는다():
    assert s.parse_type_answer("MEETING_RECORD") == "MEETING_RECORD"
    assert s.parse_type_answer("답: meeting_record 입니다") == "MEETING_RECORD"
    # 추론 블록에 다른 코드가 있어도 답만 본다
    assert s.parse_type_answer(
        "<think>REQUIREMENTS_SPEC 인가 SOFTWARE_DESIGN 인가</think>\nSOFTWARE_DESIGN"
    ) == "SOFTWARE_DESIGN"
    assert s.parse_type_answer("REQUIREMENTS_SPEC 또는 SOFTWARE_DESIGN") is None
    assert s.parse_type_answer("UNKNOWN") is None
    assert s.parse_type_answer("[fake:abc] 파일명: x") is None


def test_모델_답의_첫_줄이_제목이다():
    assert s.parse_title_answer('<think>...</think>\n"주간 회의록"\n부연') == "주간 회의록"
    assert s.parse_title_answer("UNKNOWN") is None
    assert s.parse_title_answer("") is None


def test_모델에_주는_머리는_표를_뺀다():
    head = s.head_for_llm("제목\n| a | b |\n본문", limit=100)
    assert head == "제목\n본문"


def test_절_제목의_상위_요구사항_코드를_따로_읽는다():
    text = (
        "문서번호 IM-001 · 버전 v1.0\n"
        "SFR.CON.001 확장 가능한 커넥터 구조\n"
        "커넥터 구조를 정의한다.\n"
        "### SFR.CON.002 대표 도구 연동\n"
        "| 요구사항 ID | 요구사항 명칭 | 요구사항 설명 | 중요도 |\n"
        "|---|---|---|---|\n"
        "| SWFR.CON.001 | 공통 인터페이스 | 공통 인터페이스 (상위 SFR.CON.001) | 필수 |\n"
        "| SWFR.CON.003 | GitHub 수집 | GitHub 을 수집한다 (상위 SFR.CON.002 대표 도구) | 필수 |\n"
        "| SWFR.CON.009 | 상위 없음 | 상위를 적지 않은 항목 | 필수 |\n"
        "SWFR.CON.001 본문에서 다시 언급해도 상위가 아니다\n"
    )
    items = s.spec_items(text)
    codes = {i.code for i in items}
    parents = s.spec_parents(text, codes)
    # 문서번호(IM-001)는 커밋이 가리킬 꼴이 아니라 상위로 읽지 않는다. 표의 코드도 아니다
    assert [(p["code"], p["title"]) for p in parents] == [
        ("SFR.CON.001", "확장 가능한 커넥터 구조"), ("SFR.CON.002", "대표 도구 연동"),
    ]
    assert parents[0]["location"] == "2번째 줄"
    parent_codes = [p["code"] for p in parents]
    assert [s.parent_of(i.as_dict(), parent_codes) for i in items] == [
        "SFR.CON.001", "SFR.CON.002", None,
    ]


def test_상위_코드가_다른_코드의_일부면_상위로_보지_않는다():
    assert s.parent_of({"title": "x", "body": "SFR.CON.0012 와 XSFR.CON.001"},
                       ["SFR.CON.001"]) is None


def test_표가_없는_명세서는_상위가_없다():
    text = "SFR.CON.001 상위\nSWFR.CON.001 하위 항목\n"
    assert s.spec_parents(text, {i.code for i in s.spec_items(text)}) == []


def test_요구사항정의서의_상위_요구사항_14개를_읽는다():
    text = IM001.read_text(encoding="utf-8")
    parents = s.spec_parents(text, {i.code for i in s.spec_items(text)})
    assert len(parents) == 14
    assert parents[0]["code"] == "SFR.CON.001" and parents[-1]["code"] == "SFR.SEC.001"
