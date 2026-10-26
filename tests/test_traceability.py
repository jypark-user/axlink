"""추적표 생성기 — 규약 검사와 파싱.

추적표는 납품 산출물(요구사항추적표)이면서 자기참조 시연의 원천이다. 파서가 조용히
틀리면 빈 표가 나오고, 빈 표는 우리가 규약을 안 지킨 것처럼 보인다. ARC-002 로 ID 체계를
바꾸면서 실제로 그 상태가 한동안 이어졌다.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_traceability", ROOT / "scripts" / "build_traceability.py"
)
tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tr)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("feat(integration): 수집한다  [SWFR.CON.004]", ["SWFR.CON.004"]),
        ("docs(docs): 읽기 전용 검증  [QUR.CON.001]", ["QUR.CON.001"]),
        ("feat(infra): 폐쇄망 기동  [SER.SEC.002]", ["SER.SEC.002"]),
        ("chore(infra): 의존성 정리  [chore]", []),
        # 옛 체계는 더 이상 요구사항으로 읽지 않는다.
        ("feat(rag): 무언가  [REQ-012]", []),
    ],
)
def test_요구사항_ID_추출(text, expected):
    assert tr.REQ_RE.findall(text) == expected


def test_상위_과업항목은_요구사항이_아니다():
    """SFR 은 과업지시서 항목이라 추적표의 행이 아니라 열이다."""
    assert tr.REQ_RE.findall("SFR.CON.001 확장 가능한 커넥터 구조") == []
    assert tr.TASK_RE.findall("### SFR.CON.001 확장 가능한 커넥터 구조") == ["SFR.CON.001"]


def test_요구사항정의서를_읽는다():
    titles, tasks = tr.scan_requirements()

    assert len(titles) == 41, "IM-001 이 확정한 요구사항은 41건이다"
    assert titles["SWFR.CON.004"].startswith("Redmine에서")
    # 굵은 글씨 표기가 제목에 섞여 들어오면 안 된다.
    assert not titles["SWFR.PIP.006"].startswith("**")
    # 요구사항은 자기가 속한 과업 항목을 안다.
    assert tasks["SWFR.CON.004"] == "SFR.CON.002"


def _fake_log(monkeypatch, *commits: tuple[str, str]) -> None:
    """(제목, 본문) 쌍을 git log 출력 형식으로 흉내낸다."""
    raw = "".join(
        f"{'a' * 40}{subject}{body}" for subject, body in commits
    )
    monkeypatch.setattr(tr, "git", lambda *a: raw)


def test_추적_ID_없는_커밋은_위반이다(monkeypatch):
    _fake_log(
        monkeypatch,
        ("feat(integration): 추적 ID 를 안 붙였다", ""),
        ("chore(infra): 의존성 정리  [chore]", ""),
        ("feat(integration): 제대로 붙였다  [SWFR.CON.004]", ""),
    )

    commits, _, violations = tr.scan_commits({"SWFR.CON.004"})

    assert len(violations) == 1 and "추적 ID 누락" in violations[0]
    assert set(commits) == {"SWFR.CON.004"}


def test_이슈_참조는_접두가_있어야_한다(monkeypatch):
    _fake_log(
        monkeypatch,
        ("feat(integration): 수집한다  [SWFR.CON.004]", "Refs: GH-4, RM-12"),
        ("feat(integration): 또 수집한다  [SWFR.CON.004]", "Refs: #17"),
    )

    _, issues, violations = tr.scan_commits({"SWFR.CON.004"})

    # 맨 #17 은 어느 도구인지 알 수 없으므로 수집하지 않고 위반으로만 남긴다.
    assert issues["SWFR.CON.004"] == {"GH-4", "RM-12"}
    assert len(violations) == 1 and "접두 없는 이슈 참조" in violations[0]


def test_오타난_요구사항_ID_는_커밋에서도_걸린다(monkeypatch):
    _fake_log(monkeypatch, ("feat(integration): 수집한다  [SWFR.CON.040]", ""))

    commits, _, violations = tr.scan_commits({"SWFR.CON.004"})

    assert len(violations) == 1 and "정의되지 않은 요구사항 ID" in violations[0]
    assert commits["SWFR.CON.040"] == {"a" * 8}


def test_정의되지_않은_ID_는_문서에서도_걸린다(tmp_path, monkeypatch):
    doc = tmp_path / "20-design" / "임시.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# ARC-009 임시\n\n| | |\n|---|---|\n| 상태 | **초안** |\n"
        "| 관련 | `SWFR.CON.004` |\n\n"
        "본문에서 `SWFR.CON.005` 와 `SWFR.CON.099` 를 지나가듯 다룬다.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tr, "DOCS", tmp_path)
    monkeypatch.setattr(tr, "ROOT", tmp_path)

    designs, _, violations = tr.scan_docs({"SWFR.CON.004", "SWFR.CON.005"})

    # 관련 행만 설계 근거다. 초안이면 표시가 붙는다(ARC-024). 본문 언급은 근거가 아니다
    assert designs["SWFR.CON.004"] == {"ARC-009(초안)"}
    assert "SWFR.CON.005" not in designs
    assert "SWFR.CON.099" not in designs
    assert len(violations) == 1 and "SWFR.CON.099" in violations[0]


def test_저장소_전체가_규약을_지킨다():
    """CI 와 같은 검사. 여기서 깨지면 커밋 메시지나 문서 ID 가 규약을 벗어난 것이다."""
    titles, _ = tr.scan_requirements()
    known = set(titles)
    _, _, commit_violations = tr.scan_commits(known)
    _, _, doc_violations = tr.scan_docs(known)

    assert commit_violations + doc_violations == []


def test_git_이_실패하면_빈_표를_만들지_않고_멈춘다(monkeypatch):
    # 저장소가 아니거나 git 이 깨지면 커밋이 0건으로 읽혀 표가 조용히 빈다(점검 DOC-01)
    with pytest.raises(tr.GitError):
        tr.git("log", "--no-such-option")
    monkeypatch.setattr(tr, "ROOT", ROOT / "no-such-dir")
    with pytest.raises(tr.GitError):
        tr.scan_commits(set())


def test_git_이_실패하면_검사도_실패로_끝난다(monkeypatch, capsys):
    def broken(*_args):
        raise tr.GitError("git log 실패: fatal: not a git repository")
    monkeypatch.setattr(tr, "git", broken)
    monkeypatch.setattr("sys.argv", ["build_traceability.py", "--check"])
    assert tr.main() == 2
    assert "git log 실패" in capsys.readouterr().err
