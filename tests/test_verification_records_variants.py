"""검증 기록: 매개변수로 경우가 나뉜 시험(UC-060-S10)과 모의 모델 실행의 판정."""

import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verification_records.py"
_spec = importlib.util.spec_from_file_location("verification_records", _PATH)
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)

_ENV = "5174 http://127.0.0.1:5174/ax-link"


def _run(rid: str, ts: str, verdict: str, variant: str | None = None, **extra) -> dict:
    row = {
        "run_id": rid, "ts": ts, "scenarios": ["UC-060-S10"], "acs": ["AC-060-9"],
        "ac_verdicts": {"AC-060-9": verdict}, "verdict": verdict, "mode": "api",
        "env": {"name": _ENV, "tools": [], "model": ""}, "evidence": [],
    }
    if variant:
        row["variant"] = variant
    row.update(extra)
    return row


def _catalog() -> dict:
    return {
        "scenarios": {"UC-060-S10": {"uc": "UC-060", "needs": [], "decs": [], "acs": ["AC-060-9"]}},
        "acs": {"AC-060-9": {
            "uc": "UC-060", "scenarios": ["UC-060-S10"], "decs": [], "needs": [], "obligations": [],
        }},
        "obligations": {}, "ccs": {}, "commons": {}, "sources": {},
    }


def _status(tmp_path, monkeypatch, runs: list[dict]) -> dict:
    (tmp_path / "runs.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in runs), encoding="utf-8"
    )
    monkeypatch.setattr(vr, "RECORDS", tmp_path)
    monkeypatch.setattr(vr, "unusable_evidence", lambda: set())
    return vr.compute_status(_catalog())


def _sc(st: dict) -> str:
    rows = st["scenarios"]
    rows = rows if isinstance(rows, list) else list(rows.values())
    return next(r["status"] for r in rows if r["scenario"] == "UC-060-S10")


def test_경우마다_최신이_통과여야_통과다(tmp_path, monkeypatch):
    runs = [
        _run("C-R1", "2026-11-11T09:00:00+09:00", "fail", "캐시없음-집계"),
        _run("C-R2", "2026-11-11T09:00:01+09:00", "pass", "캐시있음-집계"),
    ]
    assert _sc(_status(tmp_path, monkeypatch, runs)) == "fail"
    # 뒤 경우의 통과가 앞 경우의 실패를 가리지 않는다. 실패한 경우를 다시 돌려 통과해야 통과
    runs.append(_run("C-R3", "2026-11-11T10:00:00+09:00", "pass", "캐시없음-집계"))
    assert _sc(_status(tmp_path, monkeypatch, runs)) == "pass"


def test_경우_구분_전_실행은_보지_않는다(tmp_path, monkeypatch):
    runs = [
        _run("C-R1", "2026-11-10T09:00:00+09:00", "fail"),
        _run("C-R2", "2026-11-11T09:00:00+09:00", "pass", "캐시없음-집계"),
    ]
    assert _sc(_status(tmp_path, monkeypatch, runs)) == "pass"


def test_모의_모델_실행은_실모델을_증명하지_않는다():
    run = _run("C-R1", "2026-11-11T09:00:00+09:00", "pass", proves=["api", "live-model"],
               model_kind="mock")
    assert vr.proves(run) == {"api"}


def test_junit_의_경우와_모의_모델_표시를_적는다(tmp_path, monkeypatch):
    junit = tmp_path / "j.xml"
    junit.write_text(
        '<testsuite><testcase classname="tests.scenarios.test_group_gh" '
        'name="test_UC_060_S10_모델_장애[\\uce90\\uc2dc\\uc788\\uc74c-\\ubb38\\uc11c]"><properties>'
        '<property name="model" value="mock-replay"/></properties></testcase></testsuite>',
        encoding="utf-8",
    )
    recs = tmp_path / "rec"
    recs.mkdir()
    (recs / "catalog.json").write_text(json.dumps({
        "sources": {k: {"version": "v0"} for k in (
            "IM-002-유스케이스명세서.md",
            "IM-002A-요구사항-세부의무-대응표.md",
            "IM-005A-공통시험자료.md",
        )},
        "scenarios": {"UC-060-S10": {"acs": ["AC-060-9"], "state": "S0", "expected": "x"}},
        "acs": {"AC-060-9": {"obligations": []}},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(vr, "RECORDS", recs)
    args = vr.argparse.Namespace(
        junit=str(junit), cycle="C", only="", evidence="e.xml", url="", proves="api", ts="",
        operator="t", baseline="b", code="c", db="d", env=_ENV, tools="", model="실모델",
        mode="api", defects="", rerun_of="", notes="",
    )
    vr.record_junit(args)
    row = json.loads((recs / "runs.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["variant"] == "캐시있음-문서"
    assert row["model_kind"] == "mock"
    assert "모의 모델" in row["env"]["model"] and "실모델 증거 아님" in row["env"]["model"]


def test_junit_의_실모델_이름은_모의_모델로_읽지_않는다(tmp_path, monkeypatch):
    """실모델 시험은 대상이 쓴 모델 이름과 proves=live-model 을 남긴다. 그 실행은 실모델 증거다."""
    junit = tmp_path / "j.xml"
    junit.write_text(
        '<testsuite><testcase classname="tests.scenarios.test_live_model" '
        'name="test_UC_060_S10_모델_장애[\uc2e4\ubaa8\ub378]"><properties>'
        '<property name="model" value="gemma4:31b-cloud"/>'
        '<property name="proves" value="live-model"/></properties></testcase></testsuite>',
        encoding="utf-8",
    )
    recs = tmp_path / "rec"
    recs.mkdir()
    (recs / "catalog.json").write_text(json.dumps({
        "sources": {k: {"version": "v0"} for k in (
            "IM-002-유스케이스명세서.md",
            "IM-002A-요구사항-세부의무-대응표.md",
            "IM-005A-공통시험자료.md",
        )},
        "scenarios": {"UC-060-S10": {"acs": ["AC-060-9"], "state": "S0", "expected": "x"}},
        "acs": {"AC-060-9": {"obligations": []}},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(vr, "RECORDS", recs)
    args = vr.argparse.Namespace(
        junit=str(junit), cycle="C", only="", evidence="e.xml", url="", proves="api", ts="",
        operator="t", baseline="b", code="c", db="d", env=_ENV, tools="", model="",
        mode="api", defects="", rerun_of="", notes="",
    )
    vr.record_junit(args)
    row = json.loads((recs / "runs.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["variant"] == "실모델"
    assert "model_kind" not in row and row["env"]["model"] == "gemma4:31b-cloud"
    assert vr.proves(row) == {"api", "live-model"}
