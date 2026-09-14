"""추적관계 근거 판별. 순수 함수라 DB 없이 돈다.

근거가 없으면 링크를 만들지 않는다(QUR.PIP.001). 여기서 "없다"고 판정한 것이
곧 만들어지지 않는 링크다.
"""

from app.standard import trace_rules as tr
from app.standard.mapping_rules import MappingRules

KNOWN = {"SWFR.CON.002", "SWFR.CON.004", "QUR.WEB.001", "SWFR.RAG.007"}
PATHS = {"docs/00-management/WBS.xlsx"}


def _commit(message: str) -> dict:
    return {"sha": "a" * 40, "commit": {"message": message}, "html_url": "https://x/c/a"}


def test_커밋의_대괄호_코드와_Refs_를_읽는다():
    found = tr.commit_evidence(
        _commit("feat(integration): 매핑 판별 이름을 연결별 설정으로  [SWFR.CON.002]\n\n"
                "업체마다 다른 것은 이름이다.\n\nRefs: GH-2, RM-4"),
        KNOWN, PATHS,
    )
    targets = [(e.kind, e.target, e.link_kind) for e in found]
    assert targets == [
        ("TEXT_REQ_CODE", ("REQ", "SWFR.CON.002"), "IMPLEMENTS"),
        ("TEXT_ISSUE_REF", ("GH", "2"), "IMPLEMENTS"),
        ("TEXT_ISSUE_REF", ("RM", "4"), "IMPLEMENTS"),
    ]
    # 근거 원문은 코드가 적힌 그 줄이다.
    assert found[0].text.endswith("[SWFR.CON.002]")
    assert found[1].text == "Refs: GH-2, RM-4"


def test_사업에_없는_코드와_맨_번호는_근거가_아니다():
    found = tr.commit_evidence(
        _commit("feat(rag): 무언가  [SWFR.CON.040]\n\nRefs: #17"), KNOWN, PATHS
    )
    assert found == []


def test_test_유형_커밋은_시험으로_잇는다():
    found = tr.commit_evidence(_commit("test(rag): 게이트 시험  [SWFR.RAG.007]"), KNOWN, PATHS)
    assert [e.link_kind for e in found] == ["TESTS"]
    assert tr.commit_link_kind("fix(auth): 고친다  [QUR.WEB.001]") == "IMPLEMENTS"
    assert tr.commit_link_kind("") == "IMPLEMENTS"


def test_같은_코드가_여러_줄이면_한_번만():
    found = tr.commit_evidence(
        _commit("feat(x): 제목  [SWFR.CON.004]\n\n본문에서도 SWFR.CON.004 를 말한다"),
        KNOWN, PATHS,
    )
    assert len(found) == 1


def test_PR_은_제목과_본문을_같이_본다():
    found = tr.pull_request_evidence(
        {"title": "feat(x): 제목  [SWFR.CON.004]", "body": "Refs: GH-9"}, KNOWN, PATHS
    )
    assert [e.target for e in found] == [("REQ", "SWFR.CON.004"), ("GH", "9")]


def test_작업_이슈는_본문의_코드를_보고_라벨이_성격을_정한다():
    payload = {
        "title": "D3 조사",
        "body": "`SWFR.RAG.007` 근거 부족 시 답변 차단.\nRefs: GH-3",
        "labels": [{"name": "유형: 시험"}],
    }
    found = tr.github_issue_evidence(payload, KNOWN, PATHS)
    # 이슈끼리의 GH- 참조는 추적표의 축이 아니라 읽지 않는다.
    assert [(e.target, e.link_kind) for e in found] == [(("REQ", "SWFR.RAG.007"), "TESTS")]
    assert tr.github_issue_link_kind({"labels": [{"name": "유형: 설계"}]}) == "DESIGNS"
    assert tr.github_issue_link_kind({"labels": [{"name": "유형: 작업"}]}) == "IMPLEMENTS"


def test_요구사항_이슈는_산출물_경로만_본다():
    payload = {
        "title": "[QUR.WEB.001] 읽기 전용",
        "body": "SWFR.CON.002 와 관련. 산출물은 docs/00-management/WBS.xlsx 다.",
    }
    found = tr.requirement_issue_evidence(payload, PATHS)
    assert [(e.kind, e.target, e.link_kind) for e in found] == [
        ("TEXT_FILE_PATH", ("FILE", "docs/00-management/WBS.xlsx"), "DELIVERS")
    ]


def test_레드마인은_REQ_ID_필드와_relations_를_읽는다():
    payload = {
        "id": 4,
        "subject": "커넥터 시험",
        "description": "",
        "tracker": {"name": "시험"},
        "custom_fields": [{"name": "REQ ID", "value": "SWFR.CON.002"}],
        "relations": [
            {"id": 1, "issue_id": 4, "issue_to_id": 5, "relation_type": "relates"},
            # 상대편에서 온 관계는 그쪽이 만든다. 여기서 만들면 두 번 생긴다.
            {"id": 2, "issue_id": 6, "issue_to_id": 4, "relation_type": "blocks"},
        ],
    }
    found = tr.redmine_issue_evidence(payload, MappingRules(), KNOWN, PATHS)
    assert [(e.kind, e.target, e.link_kind) for e in found] == [
        ("CUSTOM_FIELD", ("REQ", "SWFR.CON.002"), "TESTS"),
        ("ISSUE_RELATION", ("RM", "5"), "TESTS"),
    ]
    assert found[0].text == "REQ ID: SWFR.CON.002"
    assert found[1].text == "relates RM-5"


def test_레드마인_필드_이름은_연결_설정을_따른다():
    payload = {
        "id": 7, "subject": "", "description": "",
        "tracker": {"name": "설계"},
        "custom_fields": [{"name": "요구사항", "value": ["SWFR.CON.002", "SWFR.CON.004"]}],
    }
    default = tr.redmine_issue_evidence(payload, MappingRules(), KNOWN, PATHS)
    assert default == []
    custom = tr.redmine_issue_evidence(
        payload, MappingRules(req_id_field="요구사항"), KNOWN, PATHS
    )
    assert [e.target for e in custom] == [("REQ", "SWFR.CON.002"), ("REQ", "SWFR.CON.004")]
    assert {e.link_kind for e in custom} == {"DESIGNS"}


def test_산출물_자리가_연결_종류를_정한다():
    assert tr.product_link_kind("SOFTWARE_DESIGN") == "DESIGNS"
    assert tr.product_link_kind("TEST_REPORT") == "TESTS"
    assert tr.product_link_kind("PROJECT_PLAN") == "DELIVERS"


def test_근거_원문은_길이를_자른다():
    long_line = "[SWFR.CON.004] " + "가" * 500
    found = tr.commit_evidence(_commit(long_line), KNOWN, PATHS)
    assert len(found[0].text) == 300 and found[0].text.endswith("…")
