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


def test_PR_본문의_닫기_키워드는_같은_저장소_이슈와_구조적으로_잇는다():
    """IM-005A TD-PR-1: 「버튼 정렬 수정」 본문 Closes #4 → 이슈 G4, 근거 유형 구조적 (DEF-V010)."""
    found = tr.pull_request_evidence({"title": "버튼 정렬 수정", "body": "Closes #4"}, KNOWN, PATHS)
    assert [(e.kind, e.target, e.link_kind) for e in found] == [
        ("ISSUE_RELATION", ("GH", "4"), "IMPLEMENTS")
    ]
    assert found[0].text == "Closes #4"


def test_닫기_키워드는_변형을_읽고_다른_저장소와_맨_번호는_읽지_않는다():
    body = "fixes: #5\nResolved #6\nclose #5\ncloses other/repo#7\n관련 #8\nsee #9"
    found = tr.pull_request_evidence({"title": "docs: 정리", "body": body}, KNOWN, PATHS)
    assert [e.target for e in found] == [("GH", "5"), ("GH", "6")]


def test_커밋_메시지의_닫기_키워드는_근거가_아니다():
    """규약 3절: 커밋의 맨 #n 은 Redmine 이 자기 이슈로 읽을 수 있다. PR 본문만 예외다."""
    found = tr.commit_evidence(_commit("fix(x): 고친다  [SWFR.CON.004]\n\nCloses #4"), KNOWN, PATHS)
    assert [e.target for e in found] == [("REQ", "SWFR.CON.004")]


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


# --- 변경 분류 (ARC-024 2-3) ---------------------------------------------------

DESIGN = ["docs/20-design/*.md"]


def test_변경_파일을_모르면_지금_규칙을_그대로_쓴다():
    assert tr.change_link_kinds("test(rag): 시험  [X]", None, DESIGN) == (["TESTS"], None)
    assert tr.change_link_kinds("docs: 문서  [X]", None, DESIGN) == (["IMPLEMENTS"], None)


def test_변경_파일이_관계를_정한다():
    kinds = tr.change_link_kinds
    assert kinds("feat: x", ["app/a.py"], DESIGN) == (["IMPLEMENTS"], None)
    assert kinds("feat: x", ["tests/test_a.py"], DESIGN) == (["TESTS"], None)
    assert kinds("docs: x", ["docs/20-design/ARC-024.md"], DESIGN) == (["DESIGNS"], None)
    # 섞이면 관계가 여럿이다
    assert kinds("feat: x", ["app/a.py", "tests/test_a.py", "docs/20-design/ARC-1.md"],
                 DESIGN) == (["IMPLEMENTS", "TESTS", "DESIGNS"], None)
    # 제목이 test 여도 코드만 바꿨으면 시험 연결이 아니다
    assert kinds("test: x", ["app/a.py"], DESIGN) == (["IMPLEMENTS"], None)
    # 관리·매뉴얼 문서만 바꾼 변경은 구현으로 세지 않는다
    got, reason = kinds("docs: WBS 갱신", ["docs/00-management/WBS.xlsx"], DESIGN)
    assert got == [] and "문서만" in reason
    # 설계 경로를 설정하지 않은 저장소에서는 설계 문서도 그냥 문서다
    assert kinds("docs: x", ["docs/20-design/ARC-1.md"], [])[0] == []


def test_시험_파일_관례():
    cat = tr.file_category
    assert cat("frontend/src/a.test.tsx", []) == "test"
    assert cat("pkg/foo_test.py", []) == "test"
    assert cat("README.md", []) == "doc"
    assert cat("infra/docker-compose.yml", []) == "code"


def test_문서만_바꾼_커밋의_근거는_제외로_남는다():
    payload = {"commit": {"message": "docs: 대장 갱신  [SWFR.CON.002]"},
               "files": [{"filename": "docs/00-management/a.md"}]}
    found, dropped = tr.commit_evidence_with_exclusions(
        payload, {"SWFR.CON.002"}, set(), DESIGN)
    assert found == []
    assert [(x.target, x.link_kind) for x in dropped] == [(("REQ", "SWFR.CON.002"), "IMPLEMENTS")]


def test_설계_문서와_코드를_함께_바꾼_커밋은_두_관계다():
    payload = {"commit": {"message": "feat: x  [SWFR.CON.002]"},
               "files": ["app/a.py", "docs/20-design/ARC-024.md"]}
    found = tr.commit_evidence(payload, {"SWFR.CON.002"}, set(), DESIGN)
    assert sorted(e.link_kind for e in found) == ["DESIGNS", "IMPLEMENTS"]


def test_병합_커밋_번호():
    merge = {"commit": {"message": "Merge pull request #12 from a/b\n\nfeat: x"},
             "parents": [{}, {}]}
    assert tr.merged_pr_number(merge) == "12"
    assert tr.merged_pr_number({**merge, "parents": [{}]}) is None
    other = {"commit": {"message": "Merge branch 'main' into x"}, "parents": [{}, {}]}
    assert tr.merged_pr_number(other) is None


def test_설계_문서_근거는_위치와_상태를_남긴다():
    payload = {
        "repo": "o/r", "path": "docs/20-design/ARC-007.md", "commit_sha": "c" * 40,
        "blob_sha": "b" * 40, "html_url": "https://github.com/o/r/blob/" + "c" * 40 +
        "/docs/20-design/ARC-007.md",
        "text": "# ARC-007 규칙\n\n| | |\n|---|---|\n| 상태 | **초안** |\n"
                "| 관련 | SWFR.CON.002 |\n",
    }
    (e,) = tr.design_doc_evidence(payload, {"SWFR.CON.002"})
    assert (e.kind, e.link_kind, e.target) == ("DOC_REQ_REF", "DESIGNS", ("REQ", "SWFR.CON.002"))
    assert e.url.endswith("ARC-007.md#L6")
    assert e.meta["docStatus"] == "DRAFT" and e.meta["line"] == 6
    assert e.meta["commitSha"] == "c" * 40 and e.meta["blobSha"] == "b" * 40
    assert tr.design_doc_evidence({**payload, "deleted": True}, {"SWFR.CON.002"}) == []
