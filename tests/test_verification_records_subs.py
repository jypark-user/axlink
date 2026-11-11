"""검증 기록: 명세 한 행을 시험이 하위 문자로 나눠 돈 시나리오(UC-051-S03a·S03b)의 판정."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verification_records.py"
_spec = importlib.util.spec_from_file_location("verification_records", _PATH)
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)


def _scenarios() -> dict[str, dict]:
    return {
        "UC-051-S03": {"id": "UC-051-S03"},
        "UC-020-S06": {"id": "UC-020-S06"},
        "UC-060-S05a": {"id": "UC-060-S05a"},
        "UC-060-S05b": {"id": "UC-060-S05b"},
    }


def test_하위_문자_시험을_명세_행에_잇는다():
    sc = _scenarios()
    tests = {
        "UC-051-S03a", "UC-051-S03b", "UC-020-S06", "UC-020-S06b", "UC-060-S05a", "UC-060-S05b",
    }
    subs = vr.attach_subs(sc, tests)
    assert subs == {
        "UC-051-S03a": "UC-051-S03", "UC-051-S03b": "UC-051-S03", "UC-020-S06b": "UC-020-S06",
    }
    assert sc["UC-051-S03"]["subs"] == ["UC-051-S03a", "UC-051-S03b"]
    # 상위 ID 그대로인 시험도 있으면 그것까지 필수 부분이다
    assert sc["UC-020-S06"]["subs"] == ["UC-020-S06", "UC-020-S06b"]
    # 명세에 따로 행이 있는 하위 문자는 그 자체로 시나리오다
    assert "subs" not in sc["UC-060-S05a"]


def test_하위가_모두_통과해야_통과다():
    assert vr.combine_sub_status(["pass", "pass"]) == "pass"
    assert vr.combine_sub_status(["pass", "not-run"]) == "not-run"
    assert vr.combine_sub_status(["pass", "fail"]) == "fail"
    assert vr.combine_sub_status(["blocked", "pass"]) == "blocked"
    assert vr.combine_sub_status(["pass", "pass-ci-only"]) == "pass-ci-only"
    assert vr.combine_sub_status(["pass-ci-only", "pass-needs-evidence"]) == "pass-needs-evidence"
    assert vr.combine_sub_status([]) == "not-run"
