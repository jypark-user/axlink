"""저장소 설계 문서의 명시적 참조 판별 (ARC-024 2-1). DB 없이 돈다."""

from app.standard import design_refs as d

KNOWN = {"SWFR.CON.002", "SWFR.CON.005", "SWFR.PIP.003", "SWFR.PIP.007", "SWFR.RAG.007",
         "QUR.WEB.001", "SWFR.CON.001", "SWFR.CON.007"}

ARC = """# ARC-007 추적관계 생성 규칙

| | |
|---|---|
| 상태 | **확정** |
| 일자 | 2026-09-14 |
| 관련 | `SWFR.PIP.003` `SWFR.PIP.007`(미결) `SWFR.ZZZ.999` |

---

## 1. 문제

본문에서 `QUR.WEB.001` 을 지나가듯 말한다. 범위 `SWFR.CON.001~007` 도 근거가 아니다.

### 4.2 매핑 설정 (SWFR.CON.002)

내용.
"""


def _codes(info: d.DocInfo) -> dict[str, d.Ref]:
    return {r.code: r for r in info.refs}


def test_머리_표_관련_행과_절_제목_괄호만_근거다():
    info = d.parse(ARC, KNOWN)
    refs = _codes(info)
    assert set(refs) == {"SWFR.PIP.003", "SWFR.PIP.007", "SWFR.CON.002"}
    assert refs["SWFR.PIP.003"].form == d.RELATED_ROW
    assert refs["SWFR.PIP.003"].line_no == 7
    assert refs["SWFR.CON.002"].form == d.SECTION_TITLE
    assert refs["SWFR.CON.002"].section == "4.2 매핑 설정 (SWFR.CON.002)"


def test_지나가는_언급과_범위_표기와_모르는_코드는_근거가_아니다():
    refs = _codes(d.parse(ARC, KNOWN))
    assert "QUR.WEB.001" not in refs      # 본문 언급
    assert "SWFR.CON.001" not in refs     # 범위 표기 앞쪽
    assert "SWFR.ZZZ.999" not in refs     # 사업에 없는 코드


def test_한정어를_그대로_남긴다():
    refs = _codes(d.parse(ARC, KNOWN))
    assert refs["SWFR.PIP.007"].qualifier == "미결"
    assert refs["SWFR.PIP.003"].qualifier is None


def test_문서가_선언한_상태와_ID():
    info = d.parse(ARC, KNOWN)
    assert (info.doc_id, info.status, info.status_text) == ("ARC-007", d.CONFIRMED, "확정")

    draft = d.parse("# SW 설계서 (IM-003)\n\n> v0.1 초안 · 2026-09-30\n", KNOWN)
    assert (draft.doc_id, draft.status) == ("IM-003", d.DRAFT)

    listed = d.parse("# ARC-017 강화\n\n- 상태: 확정 (2026-10-02)\n"
                     "- 관련 요구사항: SWFR.RAG.007\n", KNOWN)
    assert listed.status == d.CONFIRMED
    assert [(r.code, r.form) for r in listed.refs] == [("SWFR.RAG.007", d.RELATED_ROW)]

    unknown = d.parse("# 인프라 배치 방안\n\nv0.1 2026-08-21\n", KNOWN)
    assert (unknown.doc_id, unknown.status) == (None, d.UNKNOWN)


def test_요구사항_대응표_행은_첫_칸의_코드만_읽는다():
    text = """# SW 설계서 (IM-003)

## 12. 요구사항 대응표

| 요구사항 | 설계 절 | ARC |
|---|---|---|
| SWFR.CON.005 | 4.3 증분 (SWFR.CON.002 참고) | 003 |

## 13. 다음 절

| 관련 없음 | SWFR.CON.007 |
"""
    refs = _codes(d.parse(text, KNOWN))
    assert set(refs) == {"SWFR.CON.005"}
    assert refs["SWFR.CON.005"].form == d.MAPPING_TABLE
    assert refs["SWFR.CON.005"].section == "12. 요구사항 대응표"


def test_경로_패턴():
    globs = ["docs/20-design/*.md"]
    assert d.match_any("docs/20-design/ARC-007.md", globs)
    assert not d.match_any("docs/20-design/sub/x.md", globs)
    assert not d.match_any("docs/00-management/WBS.md", globs)
    assert d.match_any("design/a/b.md", ["design/**/*.md"])
    assert d.match_any("design/b.md", ["design/**/*.md"])
    assert not d.match_any("x.md", [])
