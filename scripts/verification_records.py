#!/usr/bin/env python3
"""
검증 기록 도구 (docs/30-test/검증기록/).

두 가지 일을 한다.

  catalog : IM-007 유스케이스 명세서와 IM-007A 세부 의무 대응표, 구현·검증 대응표를 읽어
            UC·AC·시나리오·세부 의무·DEC 의 정적 카탈로그(catalog.json)와
            자동 시험 → AC 연결 초안(test-ac-map.csv)을 만든다.
            카탈로그는 기준 문서에서 **생성**한다. 손으로 고치지 않는다.
  status  : 실행 기록(runs.jsonl)·정정(corrections.jsonl)·영향 분석(impacts.jsonl)·
            범위 제외(exclusions.jsonl)를 전부 접어 AC 별·시나리오 별 현재 상태와
            세 지표(전체 완료율 · 실행 시험 통과율 · 별도 건수)를 다시 계산한다.
            과거 기록은 읽기만 한다. 요약은 언제든 이력에서 다시 만들 수 있다.

판정 규칙(스키마는 검증기록/README.md):
  - 한 AC 에 필수 시나리오가 여럿이면 전부 통과해야 AC 통과.
  - 변경 영향 분석이 「재검증 필요」로 표시한 실행은 통과로 세지 않는다.
  - 결정 대기(DEC)·환경 대기는 분모에서 빼지 않는다. 사용자 승인 기록이 있는
    범위 제외만 분모에서 뺀다.
  - 실제/모의/재생 구분은 기록에 그대로 남긴다. 실연동·실모델·브라우저·폐쇄망이
    필요한 AC 는 모의·재생·자동만으로 통과 처리하지 않는다(카탈로그의 needs).

usage:  python scripts/verification_records.py catalog
        python scripts/verification_records.py status [--md]
        python scripts/verification_records.py record-junit <junit.xml> --cycle C01
            --mode auto --code <commit> --env <이름> --evidence <경로>
          : 시나리오 시험(test_UC_001_S01_…)의 junit 을 읽어
            시나리오 1건 = 실행 1줄로 runs.jsonl 에 더한다
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "docs" / "10-requirements"
TEST = ROOT / "docs" / "30-test"
IM001 = REQ / "IM-001-요구사항정의서.md"
IM007 = REQ / "IM-007-유스케이스명세서.md"
IM007A = REQ / "IM-007A-요구사항-세부의무-대응표.md"
IM008 = REQ / "IM-008-용어사전.md"
IM009 = TEST / "IM-009-공통시험자료.md"
IM005 = TEST / "IM-005-시험계획및결과서.md"
MAPPING = TEST / "구현-검증-대응표.md"
RECORDS = TEST / "검증기록"

UC_HEAD = re.compile(r"^### (UC-\d{3}) (.+?)(?: \((.+)\))?$")
AC_ROW = re.compile(r"^\| (AC-\d{3}-\d+[a-z]?) \| (.+?) \|$")
SC_ROW = re.compile(
    r"^\| (UC-\d{3}-S\d{2}[a-z]?)(?: (.*?))? \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$"
)
CC_ROW = re.compile(r"^\| (CC-\d{2}) \| (.+?) \| (.*?) \| (.*?) \|$")
COMMON_ROW = re.compile(r"^\| (COMMON-S\d{2}) \| (.+?) \| (.*?) \| (.*?) \| (.*?) \|$")
DEC_ROW = re.compile(r"^\| (DEC-\d{2}) \| (.+?) \|")
OBL_ROW = re.compile(r"^\| ((?:SWFR|QUR|SER)\.[A-Z]{3}\.\d{3}-o\d+) \|")
DEC_IMPACT_ROW = re.compile(r"^\| (DEC-\d{2}) (.+?) \| (.+?) \| (.+?) \|$")
AC_RANGE = re.compile(r"AC-(\d{3})-(\d+)~(\d+)")
TEST_REF = re.compile(r"`(tests/[\w/]+\.py)(::\w+)?`")
VERSION_RE = re.compile(r"\bv(\d+\.\d+(?:\.\d+)?)\b")
AC_REF = re.compile(r"AC-(\d{3})-(\d+[a-z]?(?:·\d+[a-z]?)*)")
SC_REF = re.compile(r"UC-(\d{3})-S(\d{2}[a-z]?(?:·S?\d{2}[a-z]?)*)")

# 실연동·실모델·브라우저·폐쇄망이 필요한지는 시나리오의 「검증」 열 낱말로 가른다.
NEEDS_WORDS = {
    "API": "api",  # 실행 서버(5174)에 직접 호출. TestClient 자동 실행만으로는 통과 아님
    "실연동": "live-tool",
    "실모델": "live-model",
    "브라우저": "browser",
    "폐쇄망": "airgap",
    "설치": "airgap",
}
# 실제 환경이 아닌 실행 방식. needs 가 있는 AC 는 이것만으로 통과하지 않는다.
NON_LIVE_MODES = {"mock", "replay", "auto"}

# 증거 종류(카탈로그 needs 와 같은 낱말). 시나리오의 needs 는 5174 최신 통과 실행이 전부 증명해야
# 통과다. 실행 기록에 `proves` 가 있으면 그것을 쓰고, 없으면 방식·환경에서 보수적으로 읽는다.
# 5174 API 실행은 api 만 증명한다. 브라우저·실연동·실모델·폐쇄망은 `proves` 로 적어야 인정한다.
EVIDENCE_KINDS = ("api", "browser", "live-tool", "live-model", "airgap")


def is_target(run: dict) -> bool:
    return str((run.get("env") or {}).get("name", "")).startswith(TARGET_ENV_PREFIXES)


def unusable_evidence() -> set[str]:
    """증거 점검(evidence-audit.jsonl)에서 미확보·불일치로 나온 파일. 확정 근거로 쓰지 않는다."""
    bad: set[str] = set()
    for a in read_jsonl(RECORDS / "evidence-audit.jsonl"):
        for key in ("missing", "mismatch"):
            item = a.get(key)
            for it in item if isinstance(item, list) else [item] if item else []:
                if it.get("path"):
                    bad.add(it["path"])
    return bad


def evidence_paths(run: dict) -> list[str]:
    ev = run.get("evidence")
    items = ev if isinstance(ev, list) else [ev] if ev else []
    return [i.get("path") if isinstance(i, dict) else i for i in items if i]


def proves(run: dict) -> set[str]:
    """이 실행이 증명하는 증거 종류. 재생 도구·가짜 모델이 적힌 실행은 그 종류를 증명하지 않는다.
    증거 파일이 미확보·불일치로 점검된 실행은 아무것도 증명하지 않는다."""
    if not is_target(run):
        return set()
    if any(p in _BAD_EVIDENCE for p in evidence_paths(run)):
        return set()
    env = run.get("env") or {}
    tools = " ".join(env.get("tools") or [])
    model = str(env.get("model") or "")
    if "proves" in run:
        got = set(run["proves"])
    else:
        got = {"api"} if run.get("mode") in ("api", "live") else set()
    if "replay" in tools:
        got.discard("live-tool")
    if "가짜" in model or "fake" in model.lower():
        got.discard("live-model")
    return got


def run_time(run: dict) -> datetime:
    """실행 시각을 시간대까지 읽는다. 없거나 못 읽으면 가장 이른 시각으로 둔다."""
    try:
        t = datetime.fromisoformat(str(run.get("ts", "")).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def latest_defects() -> dict[str, dict]:
    """defects.jsonl 을 결함별로 합친 마지막 상태. 상태 변경 줄은 비어 있지 않은 필드만 덮는다."""
    out: dict[str, dict] = {}
    for d in read_jsonl(RECORDS / "defects.jsonl"):
        cur = out.setdefault(d["defect_id"], {})
        cur.update({k: v for k, v in d.items() if v not in (None, "", [])})
    return out
# Goal 조건: 통과 근거는 5174(내부 검증 환경)에서 실행한 것이어야 한다. CI 실행은 보조 근거다.
TARGET_ENV_PREFIXES = ("5174",)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def doc_version(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines()[:40]:
        m = VERSION_RE.search(line)
        if m:
            return "v" + m.group(1)
    return None


def expand_refs(text: str, kind: str) -> list[str]:
    """「AC-011-6b·7」 「UC-011-S05b·S10」 같은 축약 참조를 개별 ID 로 푼다."""
    out: list[str] = []
    if kind == "ac":
        for uc, tail in AC_REF.findall(text):
            for n in tail.split("·"):
                out.append(f"AC-{uc}-{n}")
    else:
        for uc, tail in SC_REF.findall(text):
            for n in tail.split("·"):
                out.append(f"UC-{uc}-S{n.lstrip('S')}")
    return list(dict.fromkeys(out))


def cells_of(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_im007(text: str) -> dict:
    ucs: dict[str, dict] = {}
    acs: dict[str, dict] = {}
    scenarios: dict[str, dict] = {}
    commons: dict[str, dict] = {}
    ccs: dict[str, dict] = {}
    decs: dict[str, dict] = {}
    cur_uc = None
    section = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            section = line[3:]
            cur_uc = None
        m = UC_HEAD.match(line)
        if m and section.startswith("3."):
            cur_uc = m.group(1)
            ucs[cur_uc] = {
                "id": cur_uc,
                "title": m.group(2).strip(),
                "note": (m.group(3) or "").strip(),
                "acs": [],
                "scenarios": [],
            }
            continue
        m = AC_ROW.match(line)
        if m and cur_uc:
            acs[m.group(1)] = {"id": m.group(1), "uc": cur_uc, "text": m.group(2).strip()}
            ucs[cur_uc]["acs"].append(m.group(1))
            continue
        m = SC_ROW.match(line)
        if m and cur_uc:
            sid, title, state, steps, expected, pass_cond, verify = m.groups()
            needs = sorted({v for k, v in NEEDS_WORDS.items() if k in verify})
            scenarios[sid] = {
                "id": sid,
                "uc": cur_uc,
                "title": (title or "").strip(),
                "state": state.strip(),
                "input": steps.strip(),
                "expected": expected.strip(),
                "pass": pass_cond.strip(),
                "verify": verify.strip(),
                "acs": expand_refs(pass_cond, "ac"),
                "decs": sorted(set(re.findall(r"DEC-\d{2}", pass_cond + " " + verify))),
                "needs": needs,
            }
            ucs[cur_uc]["scenarios"].append(sid)
            continue
        m = COMMON_ROW.match(line)
        if m:
            commons[m.group(1)] = {
                "id": m.group(1),
                "title": m.group(2).strip(),
                "input": m.group(3).strip(),
                "expected": m.group(4).strip(),
                "verify": m.group(5).strip(),
            }
            continue
        m = CC_ROW.match(line)
        if m:
            ccs[m.group(1)] = {
                "id": m.group(1),
                "text": m.group(2).strip(),
                "requirements": m.group(3).strip(),
                "verify": m.group(4).strip(),
            }
            continue
        m = DEC_ROW.match(line)
        if m and section.startswith("6."):
            c = cells_of(line)
            decs[m.group(1)] = {
                "id": m.group(1),
                "title": c[1].split("**")[1] if "**" in c[1] else c[1][:60],
                "text": c[1],
                "ucs": c[2] if len(c) > 2 else "",
                "blocked": c[3] if len(c) > 3 else "",
                "status": c[5] if len(c) > 5 else "",
            }
    for sc in scenarios.values():
        for ac in sc["acs"]:
            if ac in acs:
                acs[ac].setdefault("scenarios", []).append(sc["id"])
    for ac in acs.values():
        ac.setdefault("scenarios", [])
        ac["decs"] = sorted({d for s in ac["scenarios"] for d in scenarios[s]["decs"]})
        ac["needs"] = sorted({n for s in ac["scenarios"] for n in scenarios[s]["needs"]})
    return {
        "ucs": ucs,
        "acs": acs,
        "scenarios": scenarios,
        "commons": commons,
        "ccs": ccs,
        "decs": decs,
    }


def parse_im007a(text: str) -> dict[str, dict]:
    obligations: dict[str, dict] = {}
    for line in text.splitlines():
        if not OBL_ROW.match(line):
            continue
        c = cells_of(line)
        if len(c) < 10:
            continue
        oid = c[0]
        obligations[oid] = {
            "id": oid,
            "requirement": oid.split("-o")[0],
            "text": c[1],
            "uc_flow": c[2],
            "acs": expand_refs(c[3], "ac"),
            "ac_text": c[3],
            "scenarios": expand_refs(c[4], "sc"),
            "data_expected": c[5],
            "verify": c[6],
            "link": c[7],
            "decision": c[8],
            "decs": sorted(set(re.findall(r"DEC-\d{2}", c[8]))),
            "execution": c[9],
            "supplement": c[10] if len(c) > 10 else "",
        }
    return obligations


def parse_dec_impacts(text: str) -> dict[str, dict]:
    """IM-007A 부록 A.2 「결정 대기에 걸린 수용 기준」 → DEC 별 영향 AC·시나리오."""
    out: dict[str, dict] = {}
    in_a2 = False
    for line in text.splitlines():
        if line.startswith("### A.2"):
            in_a2 = True
            continue
        if in_a2 and line.startswith("### "):
            break
        if not in_a2:
            continue
        m = DEC_IMPACT_ROW.match(line)
        if not m:
            continue
        dec, title, acs_raw, scs_raw = m.groups()
        acs = expand_refs(acs_raw, "ac")
        for uc, a, b in AC_RANGE.findall(acs_raw):
            acs += [f"AC-{uc}-{n}" for n in range(int(a), int(b) + 1)]
        out[dec] = {
            "dec": dec,
            "title": title.strip(),
            "acs": sorted(set(acs)),
            "acs_raw": acs_raw.strip(),
            "scenarios": expand_refs(scs_raw, "sc"),
            "scenarios_raw": scs_raw.strip(),
        }
    return out


def parse_test_map(text: str) -> list[dict]:
    """구현·검증 대응표 「확보된 근거」 행에서 시험 파일 → AC 연결 초안을 뽑는다.

    산문이라 어림이다. 실행 기록을 남길 때 실제 시험 이름으로 확정한다."""
    rows: list[dict] = []
    blocks = re.split(r"\n### (UC-\d{3}) ", text)
    for i in range(1, len(blocks), 2):
        uc, body = blocks[i], blocks[i + 1]
        m = re.search(r"^\| 확보된 근거 \| (.+?) \|$", body, re.M)
        if not m:
            continue
        for seg in m.group(1).split(" · "):
            tests = TEST_REF.findall(seg)
            if not tests:
                continue
            acs = expand_refs(seg, "ac")
            for f, fn in tests:
                rows.append(
                    {
                        "uc": uc,
                        "test": f + (fn or ""),
                        "acs": "·".join(acs) or "(대응표 본문 참조)",
                        "partial": "부분" in seg or "한정" in seg,
                        "note": seg.strip()[:160].replace("`", ""),
                    }
                )
    return rows


def build_catalog() -> dict:
    im007 = parse_im007(IM007.read_text(encoding="utf-8"))
    im007a_text = IM007A.read_text(encoding="utf-8")
    obligations = parse_im007a(im007a_text)
    dec_impacts = parse_dec_impacts(im007a_text)
    for dec, imp in dec_impacts.items():
        for ac in imp["acs"]:
            if ac in im007["acs"] and dec not in im007["acs"][ac]["decs"]:
                im007["acs"][ac]["decs"].append(dec)
                im007["acs"][ac]["decs"].sort()
    for ob in obligations.values():
        for ac in ob["acs"]:
            if ac in im007["acs"]:
                im007["acs"][ac].setdefault("obligations", []).append(ob["id"])
    for ac in im007["acs"].values():
        ac.setdefault("obligations", [])
    sources = {
        p.name: {"version": doc_version(p), "sha256": sha256(p)}
        for p in (IM001, IM007, IM007A, IM008, IM009, IM005, MAPPING)
    }
    return {
        "generated": date.today().isoformat(),
        "sources": sources,
        "counts": {
            "ucs": len(im007["ucs"]),
            "acs": len(im007["acs"]),
            "scenarios": len(im007["scenarios"]),
            "commons": len(im007["commons"]),
            "ccs": len(im007["ccs"]),
            "decs": len(im007["decs"]),
            "obligations": len(obligations),
        },
        **im007,
        "obligations": obligations,
        "dec_impacts": dec_impacts,
        "test_map_draft": parse_test_map(MAPPING.read_text(encoding="utf-8")),
    }


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.exit(f"{path.name}:{n}: JSON 오류 {e}")
    return rows


_BAD_EVIDENCE: set[str] = set()


def compute_status(cat: dict) -> dict:
    _BAD_EVIDENCE.clear()
    _BAD_EVIDENCE.update(unusable_evidence())
    runs = read_jsonl(RECORDS / "runs.jsonl")
    corrections = read_jsonl(RECORDS / "corrections.jsonl")
    impacts = read_jsonl(RECORDS / "impacts.jsonl")
    exclusions = read_jsonl(RECORDS / "exclusions.jsonl")

    # 정정: 원 기록은 남기고, 정정 기록이 가리키는 run 의 판정만 덮어 읽는다.
    corrected: dict[str, dict] = {c["run_id"]: c for c in corrections}
    # 영향 분석: 재검증 필요로 표시된 run 은 통과 근거로 쓰지 않는다.
    invalidated: set[str] = set()
    for imp in impacts:
        invalidated.update(imp.get("invalidates_runs", []))

    by_sc: dict[str, list[dict]] = defaultdict(list)
    # 시나리오 없이 AC 에 바로 붙는 실행(자동 시험 등)은 AC 별로 따로 모은다
    by_ac_direct: dict[str, list[dict]] = defaultdict(list)
    # 시각은 UTC(Z)와 +09:00 이 섞여 있다. 글자 순으로 줄 세우면 순서가 틀린다
    for r in sorted(runs, key=lambda r: (run_time(r), r.get("run_id", ""))):
        rid = r["run_id"]
        verdicts = dict(r.get("ac_verdicts") or {})
        overall = r.get("verdict")
        if rid in corrected:
            overall = corrected[rid].get("verdict", overall)
            verdicts.update(corrected[rid].get("ac_verdicts") or {})
        view = {
            **r,
            "_verdict": overall,
            "_ac_verdicts": verdicts,
            "_invalidated": rid in invalidated,
        }
        for sid in r.get("scenarios", []):
            by_sc[sid].append(view)
        if not r.get("scenarios"):
            for aid in set(list(verdicts) + list(r.get("acs") or [])):
                by_ac_direct[aid].append(view)

    def latest(sid: str) -> dict | None:
        rs = by_sc.get(sid)
        return rs[-1] if rs else None

    def latest_target(sid: str) -> dict | None:
        """5174 에서 돈 가장 최근 실행. 뒤에 돈 로컬 실행이 이 근거를 지우지 않는다."""
        rs = [r for r in by_sc.get(sid, []) if is_target(r)]
        return rs[-1] if rs else None

    excluded_acs = {e["ac"] for e in exclusions if e.get("approved_by")}
    # 열린 결함과 고쳤지만 다시 확인하지 않은 결함이 걸린 AC 는 통과로 세지 않는다
    open_defect_acs: dict[str, list[str]] = defaultdict(list)
    for did, d in latest_defects().items():
        if d.get("status") in ("open", "fixed"):
            for aid in d.get("acs") or []:
                open_defect_acs[aid].append(did)

    sc_status: dict[str, dict] = {}
    for sid, sc in cat["scenarios"].items():
        r = latest(sid)
        t = latest_target(sid)
        missing: list[str] = []
        if r is None:
            st = "not-run"
        elif r["_invalidated"]:
            st = "revalidate"
        elif r["_verdict"] != "pass":
            # 실패·차단은 어느 환경에서 났든 최신 결과로 본다
            st = r["_verdict"]
        elif t is not None and t["_invalidated"]:
            # 5174 통과가 뒤 변경으로 무효가 됐다. 로컬 통과로 메우지 않는다
            st = "revalidate"
        elif t is None or t["_verdict"] != "pass":
            # 통과했지만 5174 통과 근거가 없거나, 5174 의 마지막 결과가 통과가 아니다
            st = "pass-ci-only"
        else:
            missing = [n for n in sc["needs"] if n not in proves(t)]
            st = "pass-needs-evidence" if missing else "pass"
        sc_status[sid] = {
            "scenario": sid,
            "uc": sc["uc"],
            "status": st,
            "run_id": r["run_id"] if r else "",
            "target_run_id": t["run_id"] if t else "",
            "mode": r.get("mode", "") if r else "",
            "decs": "·".join(sc["decs"]),
            "needs": "·".join(sc["needs"]),
            "missing_evidence": "·".join(missing),
            "runs": len(by_sc.get(sid, [])),
        }

    ac_status: dict[str, dict] = {}
    for aid, ac in cat["acs"].items():
        scs = ac["scenarios"]
        direct_runs = [r for r in by_ac_direct.get(aid, []) if not r["_invalidated"]]
        direct_latest = direct_runs[-1] if direct_runs else None
        if aid in excluded_acs:
            st = "excluded"
        elif not scs and direct_latest is None:
            st = "no-scenario"
        else:
            sc_sts = [sc_status[s]["status"] for s in scs]
            direct = []
            for s in scs:
                r = latest(s)
                if r and not r["_invalidated"] and aid in r["_ac_verdicts"]:
                    direct.append(r["_ac_verdicts"][aid])
            if direct_latest is not None:
                direct.append(direct_latest["_ac_verdicts"].get(aid, direct_latest["_verdict"]))
            every = sc_sts + direct
            # 시나리오가 있으면 시나리오 판정이 기준이다. 직접 근거(자동 시험)는 실패만 반영한다
            if "fail" in every:
                st = "fail"
            elif "revalidate" in every:
                st = "revalidate"
            elif "blocked" in every:
                st = "blocked"
            elif scs and all(x == "pass" for x in sc_sts) and all(x == "pass" for x in direct):
                # 시나리오 전부 + 직접 근거 전부 통과(5174 근거와 필요한 증거 종류까지)
                st = "pass"
            elif scs and all(x.startswith("pass") for x in sc_sts):
                # 전부 통과했지만 일부는 5174 근거가 없거나 필요한 증거 종류가 빠졌다
                st = (
                    "pass-needs-evidence"
                    if any(x == "pass-needs-evidence" for x in sc_sts)
                    else "pass-ci-only"
                )
            elif (
                direct and all(x == "not-run" for x in sc_sts) and all(x == "pass" for x in direct)
            ):
                # 자동 시험 등 직접 근거만 통과, 명세의 시나리오는 아직 안 돌림 → 완료 아님
                st = "auto-only"
            elif all(x == "not-run" for x in every):
                st = "decision-wait" if ac["decs"] else "not-run"
            else:
                st = "partial"
            if st == "pass" and open_defect_acs.get(aid):
                # 통과 근거가 있어도 이 AC 에 걸린 결함이 열려 있거나 재확인 전이다
                st = "pass-defect-open"
            if st == "pass" and ac["decs"]:
                # 결정 전에는 통과 판정을 내리지 않는다(IM-007 0.6)
                st = "pass-decision-wait"
        ac_status[aid] = {
            "ac": aid,
            "uc": ac["uc"],
            "status": st,
            "decs": "·".join(ac["decs"]),
            "needs": "·".join(ac["needs"]),
            "obligations": "·".join(ac["obligations"]),
            "scenarios": "·".join(scs),
            "open_defects": "·".join(sorted(open_defect_acs.get(aid, []))),
        }

    total = len(cat["acs"])
    excluded = sum(1 for a in ac_status.values() if a["status"] == "excluded")
    passed = sum(1 for a in ac_status.values() if a["status"] == "pass")
    executed = [r for r in runs if r.get("verdict") in ("pass", "fail")]
    exec_pass = sum(
        1
        for r in executed
        if (corrected.get(r["run_id"], {}).get("verdict") or r["verdict"]) == "pass"
    )
    counts: dict[str, int] = defaultdict(int)
    for a in ac_status.values():
        counts[a["status"]] += 1
    denom = total - excluded

    # AC 밖 의무는 따로 센다. AC 완료율에 섞지 않는다
    obl_total = len(cat["obligations"])
    obl_ac = [o for o in cat["obligations"].values() if o.get("acs")]
    obl_pass = sum(
        1 for o in obl_ac if all(ac_status.get(a, {}).get("status") == "pass" for a in o["acs"])
    )
    obl_direct_pass = {
        ob
        for r in runs
        if not r.get("scenarios") and (corrected.get(r["run_id"], {}).get("verdict") or r.get(
            "verdict"
        )) == "pass" and is_target(r)
        for ob in r.get("obligations") or []
    }
    obl_non_ac = [o["id"] for o in cat["obligations"].values() if not o.get("acs")]
    common_pass = sum(
        1 for cid in cat["commons"]
        if (lambda t: t is not None and t["_verdict"] == "pass" and not t["_invalidated"])(
            latest_target(cid)
        )
    )
    cc_runs = {
        a for r in runs if is_target(r) and r.get("verdict") == "pass"
        for a in (r.get("acs") or []) if a.startswith("CC-")
    }
    extra = {
        "obligations_total": obl_total,
        "obligations_with_ac": len(obl_ac),
        "obligations_with_ac_pass": obl_pass,
        "obligations_without_ac": len(obl_non_ac),
        "obligations_without_ac_pass": sum(1 for o in obl_non_ac if o in obl_direct_pass),
        "commons_total": len(cat["commons"]),
        "commons_pass": common_pass,
        "ccs_total": len(cat["ccs"]),
        "ccs_pass": sum(1 for c in cat["ccs"] if c in cc_runs),
        "open_defects": sorted({d for ds in open_defect_acs.values() for d in ds}),
        # 과거 증거 미완비: 증거 파일이 미확보·불일치인 실행. 확정 근거로 쓰지 않는다
        "evidence_incomplete_runs": sum(
            1 for r in runs if any(p in _BAD_EVIDENCE for p in evidence_paths(r))
        ),
        "evidence_incomplete_target_runs": sum(
            1 for r in runs if is_target(r) and any(p in _BAD_EVIDENCE for p in evidence_paths(r))
        ),
    }
    metrics = {
        "ac_total": total,
        "ac_excluded_approved": excluded,
        "ac_denominator": denom,
        "ac_pass": passed,
        "overall_completion": round(passed / denom * 100, 1) if denom else 0.0,
        "runs_executed": len(executed),
        "runs_pass": exec_pass,
        "executed_pass_rate": round(exec_pass / len(executed) * 100, 1) if executed else None,
        "ac_by_status": dict(sorted(counts.items())),
        "runs_total": len(runs),
        "runs_invalidated": len(invalidated),
        **extra,
    }
    return {
        "generated": date.today().isoformat(),
        "catalog_sources": cat["sources"],
        "metrics": metrics,
        "acs": ac_status,
        "scenarios": sc_status,
    }


STATUS_LEGEND = (
    "상태 뜻: pass 통과 · fail 실패 · blocked 실행 차단 · not-run 미실행 · "
    "decision-wait 결정 대기(미실행) · pass-decision-wait 근거는 통과했으나 결정 전(미완료) · "
    "auto-only 자동 시험만 통과, 명세 시나리오 미실행(미완료) · "
    "pass-ci-only 통과했으나 5174 실행 근거 없음(미완료) · revalidate 재검증 필요 · "
    "partial 일부만 · pass-needs-evidence 5174 통과했으나 필요한 증거 종류 없음(미완료) · "
    "pass-defect-open 통과했으나 걸린 결함이 열림·재확인 전(미완료) · "
    "excluded 공식 범위 제외 · "
    "no-scenario 시나리오 없음"
)


def write_csv(path: Path, fields: list[str], rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_status(st: dict, md: bool) -> None:
    write_csv(
        RECORDS / "status-ac.csv",
        ["ac", "uc", "status", "decs", "needs", "obligations", "scenarios", "open_defects"],
        st["acs"].values(),
    )
    write_csv(
        RECORDS / "status-scenario.csv",
        [
            "scenario", "uc", "status", "run_id", "target_run_id", "mode", "decs", "needs",
            "missing_evidence", "runs",
        ],
        st["scenarios"].values(),
    )
    (RECORDS / "status.json").write_text(
        json.dumps(st["metrics"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not md:
        return
    m = st["metrics"]
    rate = "—" if m["executed_pass_rate"] is None else f"{m['executed_pass_rate']}%"
    lines = [
        f"# 검증 상태 요약 ({st['generated']})",
        "",
        "이 파일은 `python scripts/verification_records.py status --md` 가 이력(runs.jsonl 등)에서 "
        "다시 만든다. 손으로 고치지 않는다.",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| 합의된 전체 AC | {m['ac_total']} |",
        f"| 공식 범위 제외(승인 기록 있음) | {m['ac_excluded_approved']} |",
        f"| 통과 AC | {m['ac_pass']} |",
        f"| **전체 완료율** (통과 AC ÷ 분모 {m['ac_denominator']}) | "
        f"**{m['overall_completion']}%** |",
        f"| 실행한 시험(통과·실패) | {m['runs_executed']} |",
        f"| **실행 시험 통과율** | **{rate}** |",
        f"| 재검증 필요로 표시된 실행 | {m['runs_invalidated']} |",
        "",
        "## AC 상태별 건수 (별도 건수)",
        "",
        "| 상태 | 건수 |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in m["ac_by_status"].items()]
    lines += ["", STATUS_LEGEND, ""]
    (RECORDS / "status.md").write_text("\n".join(lines), encoding="utf-8")


SCENARIO_TEST = re.compile(r"test_UC_(\d{3})_S(\d{2}[a-z]?)_")


def next_run_number(cycle: str) -> int:
    runs = read_jsonl(RECORDS / "runs.jsonl")
    nums = [int(r["run_id"].split("-R")[1]) for r in runs if r["run_id"].startswith(cycle + "-R")]
    return (max(nums) + 1) if nums else 1


def _verdict_of(tc) -> tuple[str, str]:
    skipped = tc.find("skipped")
    if skipped is not None:
        if (skipped.get("type") or "") == "pytest.xfail":
            # 알려진 실패(KNOWN_FAILURES). 판정은 실패, 사유는 결함·결정 ID
            return "fail", "xfail: " + (skipped.get("message") or "")[:300]
        return "not-run", (skipped.get("message") or "skipped")[:300]
    failure, error = tc.find("failure"), tc.find("error")
    if failure is not None and (failure.get("message") or "").startswith("[XPASS(strict)]"):
        # 알려진 실패로 표시했는데 통과했다. 판정은 통과, KNOWN_FAILURES 를 갱신해야 한다
        return "pass", "XPASS: " + (failure.get("message") or "")[:300]
    if error is not None:
        return "blocked", (error.get("message") or error.text or "")[:600]
    if failure is not None:
        return "fail", (failure.get("message") or failure.text or "")[:600]
    return "pass", ""


def record_junit(a: argparse.Namespace) -> int:
    """시나리오 시험 junit → runs.jsonl.

    시험 이름의 UC-###-S## 로 시나리오를 찾고 AC 는 카탈로그에서 푼다."""
    import xml.etree.ElementTree as ET

    cat = json.loads((RECORDS / "catalog.json").read_text(encoding="utf-8"))
    root = ET.parse(a.junit).getroot()
    junit_sha = sha256(Path(a.junit))
    n = next_run_number(a.cycle)
    written = 0
    src = cat["sources"]
    with (RECORDS / "runs.jsonl").open("a", encoding="utf-8") as out:
        only = set(a.only.split(",")) if a.only else None
        for tc in root.iter("testcase"):
            m = SCENARIO_TEST.search(tc.get("name", ""))
            if not m:
                continue
            sid = f"UC-{m.group(1)}-S{m.group(2)}"
            if only is not None and sid not in only:
                continue
            sc = cat["scenarios"].get(sid)
            if sc is None:
                print(f"카탈로그에 없는 시나리오 {sid}: {tc.get('name')}")
                continue
            verdict, reason = _verdict_of(tc)
            acs = sc["acs"]
            obligations = sorted(
                {o for x in acs for o in cat["acs"].get(x, {}).get("obligations", [])}
            )
            evidence = [{"path": a.evidence, "sha256": junit_sha, "kind": "junit"}]
            if a.url:
                evidence.append({"path": a.url, "kind": "url"})
            row = {
                "run_id": f"{a.cycle}-R{n:04d}",
                "cycle_id": a.cycle,
                "ts": a.ts or datetime_now(),
                "operator": a.operator,
                "scenarios": [sid],
                "acs": acs,
                "ac_verdicts": {x: verdict for x in acs},
                "obligations": obligations,
                "requirements": sorted({o.split("-o")[0] for o in obligations}),
                "spec": {
                    "im007": src["IM-007-유스케이스명세서.md"]["version"],
                    "im007a": src["IM-007A-요구사항-세부의무-대응표.md"]["version"],
                    "im009": src["IM-009-공통시험자료.md"]["version"],
                    "baseline": a.baseline,
                },
                "code": {"commit": a.code, "db_version": a.db},
                "env": {
                    "name": a.env,
                    "tools": a.tools.split(",") if a.tools else [],
                    "model": a.model,
                },
                "mode": a.mode,
                **({"proves": a.proves.split(",")} if a.proves else {}),
                "start_state": {"state": sc["state"][:200], "actor": "", "project": ""},
                "procedure": f"pytest {tc.get('classname')}::{tc.get('name')}",
                "expected": sc["expected"],
                "actual": "통과" if verdict == "pass" else reason,
                "verdict": verdict,
                "reason": reason,
                "evidence": evidence,
                "defects": a.defects.split(",") if a.defects else [],
                "rerun_of": a.rerun_of or None,
                "notes": a.notes,
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
            written += 1
    print(f"runs.jsonl 에 {written}줄 추가")
    return 0


def datetime_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["catalog", "status", "record-junit"])
    ap.add_argument("junit", nargs="?")
    ap.add_argument("--md", action="store_true", help="status.md 도 만든다")
    ap.add_argument("--cycle", default="C01")
    ap.add_argument("--mode", default="auto", choices=["auto", "api", "replay", "mock", "live"])
    ap.add_argument(
        "--proves", default="",
        help="이 실행이 증명하는 증거 종류(쉼표): api·browser·live-tool·live-model·airgap",
    )
    ap.add_argument("--code", default="")
    ap.add_argument("--db", default="")
    ap.add_argument("--env", default="github-actions ubuntu-latest")
    ap.add_argument("--tools", default="")
    ap.add_argument("--model", default="없음")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--operator", default="claude-code")
    ap.add_argument("--baseline", default="baseline-2026-11-05")
    ap.add_argument("--ts", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--only", default="", help="기록할 시나리오 ID 들(쉼표). 비우면 전부")
    ap.add_argument("--rerun-of", default="", help="재실행이면 이전 실행 ID")
    ap.add_argument("--defects", default="", help="관련 결함 ID 들(쉼표)")
    a = ap.parse_args()
    RECORDS.mkdir(parents=True, exist_ok=True)
    if a.cmd == "record-junit":
        if not a.junit:
            ap.error("junit 경로가 필요하다")
        return record_junit(a)
    if a.cmd == "catalog":
        cat = build_catalog()
        (RECORDS / "catalog.json").write_text(
            json.dumps(cat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        write_csv(
            RECORDS / "test-ac-map.csv",
            ["uc", "test", "acs", "partial", "note"],
            cat["test_map_draft"],
        )
        print(json.dumps(cat["counts"], ensure_ascii=False))
        missing = [s["id"] for s in cat["scenarios"].values() if not s["acs"]]
        if missing:
            print(f"통과 조건에 AC 가 없는 시나리오 {len(missing)}: " + ", ".join(missing))
        orphan = [x["id"] for x in cat["acs"].values() if not x["scenarios"]]
        if orphan:
            print(f"시나리오가 없는 AC {len(orphan)}: " + ", ".join(orphan))
        return 0
    cat = json.loads((RECORDS / "catalog.json").read_text(encoding="utf-8"))
    st = compute_status(cat)
    write_status(st, a.md)
    print(json.dumps(st["metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
