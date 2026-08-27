#!/usr/bin/env python3
"""
IM-001 요구사항정의서.md 를 파싱하여 GitHub 부트스트랩 스크립트를 생성한다.

수기로 이슈를 만들지 않는다. 요구사항정의서가 단일 진실 원천이고,
이 스크립트가 그것을 GitHub 이슈로 옮긴다.
요구사항이 바뀌면 문서를 고치고 이 생성기를 다시 돌린다.

usage: python3 gen_github_bootstrap.py <요구사항정의서.md> <출력.sh>
"""
import re
import sys
import json
from pathlib import Path

# ── 마일스톤 ────────────────────────────────────────────────
# 착수보고자료 v1.0 「04 수행관리 — 추진일정 및 마일스톤」 표를 그대로 옮긴다.
# 명칭·목표일·「산출·확인」 문구를 임의로 바꾸지 않는다. 발주기관 자료와 대조되는 값이다.
# (closed=True 는 이미 지난 마일스톤 — 생성 후 닫는다)
MILESTONES = [
    ("M0 착수보고", "2026-08-11",
     "추진계획서 제출, 착수보고 발표", True),
    ("M1 범위·평가기준 확정", "2026-08-29",
     "과업범위·핵심지표·완료기준 합의서", False),
    ("M2 연계·수집 기반 확보", "2026-09-12",
     "대표 데이터 반복 수집 시연", False),
    ("M3 통합 현황 시연 (중간보고, 필요시·협의)", "2026-09-30",
     "표준 데이터 모델·스냅샷·워크스페이스", False),
    ("M4 통합 PoC 완성", "2026-10-23",
     "온프레미스 LLM·RAG·End-to-End 통합", False),
    ("M5 최종보고 (통합 PoC 실증 완료)", "2026-11-13",
     "완료보고서 초안, 최종보고 발표", False),
    ("M6 최종 인도", "2026-11-30",
     "최종 결과보고서, 실행본, 소스, 산출물 일체", False),
]

MS1, MS2, MS3, MS4, MS5, MS6 = (m[0] for m in MILESTONES[1:])

# 모듈 → 담당 마일스톤 (기본 배정. 개별 조정은 아래 OVERRIDE)
MODULE_MILESTONE = {
    "CON": MS2,
    "PIP": MS3,
    "WEB": MS3,
    "RAG": MS4,
    "DEM": MS4,
    "SEC": MS4,
}
OVERRIDE_MILESTONE = {
    # 파일럿 대조 결과 A1/A2/A3 은 W4~W6 → M3
    "SWFR.PIP.010": MS3,
    "SWFR.WEB.004": MS3,
    "SWFR.WEB.005": MS3,
    "SWFR.WEB.006": MS3,
    "QUR.WEB.003": MS3,
    # 표준 모델·기반은 M2 에 먼저 선다
    "SWFR.PIP.001": MS2,
    "SWFR.PIP.002": MS2,
    "SWFR.RAG.002": MS2,
    # 폐쇄망 검증은 M4
    "SER.SEC.002": MS4,
}

MODULE_NAME = {
    "CON": "Ⅱ.1 도구 연동·수집",
    "PIP": "Ⅱ.2 데이터 집계 파이프라인",
    "WEB": "Ⅱ.3 통합 현황 대시보드",
    "RAG": "Ⅱ.4 온프레미스 LLM 질의",
    "DEM": "Ⅱ.5 PoC 데모 시스템",
    "SEC": "Ⅲ.2 보안",
}
MODULE_COLOR = {
    "CON": "1D76DB", "PIP": "0E8A16", "WEB": "5319E7",
    "RAG": "D93F0B", "DEM": "FBCA04", "SEC": "B60205",
}
TYPE_LABELS = [
    ("유형: 요구사항", "요구사항정의서 IM-001 의 SW 요구사항", "0052CC"),
    ("유형: 작업", "요구사항에 직접 대응하지 않는 조사·정비 작업", "BFD4F2"),
    ("유형: 결함", "결함 (DEF)", "D73A4A"),
    ("유형: 문서", "산출물 문서 작성", "C5DEF5"),
]
STATUS_LABELS = [
    ("파일럿: 구현", "파일럿에 이미 구현되어 있음 — 확인·통합만", "C2E0C6"),
    ("파일럿: 부분", "파일럿에 일부만 있음 — 보완 필요", "FEF2C0"),
    ("파일럿: 없음", "파일럿에 없음 — 신규 개발", "F9D0C4"),
    ("파일럿: 충돌", "파일럿 구현이 요구사항과 어긋남 — 변경 필요", "E99695"),
    ("파일럿: 확인", "파일럿 상태 미확인 — 조사 필요", "D4C5F9"),
]
VERIF_LABELS = [
    ("검증: T", "테스트", "EDEDED"),
    ("검증: D", "시연", "EDEDED"),
    ("검증: R", "공식검토", "EDEDED"),
]

# 파일럿 대조표 판정 (docs/20-design/파일럿-대조표.md 기준)
PILOT = {
    "SWFR.CON.001": "구현", "SWFR.CON.002": "구현", "SWFR.CON.003": "구현",
    "SWFR.CON.004": "구현", "SWFR.CON.005": "부분", "SWFR.CON.006": "구현",
    "SWFR.CON.007": "구현", "QUR.CON.001": "확인",
    "SWFR.PIP.001": "부분", "SWFR.PIP.002": "구현", "SWFR.PIP.003": "구현",
    "SWFR.PIP.004": "부분", "QUR.PIP.001": "구현", "SWFR.PIP.005": "없음",
    "SWFR.PIP.006": "없음", "SWFR.PIP.007": "구현", "SWFR.PIP.008": "부분",
    "SWFR.PIP.009": "구현", "SWFR.PIP.010": "없음",
    "SWFR.WEB.001": "구현", "SWFR.WEB.002": "구현", "SWFR.WEB.003": "구현",
    "QUR.WEB.001": "구현", "QUR.WEB.002": "구현",
    "SWFR.WEB.004": "없음", "SWFR.WEB.005": "없음", "SWFR.WEB.006": "없음",
    "QUR.WEB.003": "없음",
    "SWFR.RAG.001": "구현", "SWFR.RAG.002": "구현", "QUR.RAG.001": "충돌",
    "SWFR.RAG.003": "확인", "SWFR.RAG.004": "구현", "SWFR.RAG.005": "구현",
    "SWFR.RAG.006": "구현", "SWFR.RAG.007": "확인", "QUR.RAG.002": "구현",
    "SWFR.DEM.001": "부분",
    "SER.SEC.001": "구현", "SER.SEC.002": "구현", "SER.SEC.003": "구현",
}

# 요구사항 외 작업 이슈 (파일럿 대조표 §8 도출)
EXTRA_ISSUES = [
    ("D1 조사 — 커넥터 읽기 전용 보장 검증 방법",
     MS2, ["유형: 작업", "모듈: CON"],
     "`QUR.CON.001`(원천 도구 무변경)의 검증 방법이 `R`(공식검토)이다.\n"
     "코드 검토만으로 충분한지, 아니면 원천 도구의 감사 로그를 대조하는 절차를 둘지 정한다.\n\n"
     "**산출** — IM-003 SW설계서에 검증 절차 1개 항목."),
    ("D2 조사 — 청크 원문 위치 보존 수준",
     MS2, ["유형: 작업", "모듈: RAG"],
     "`SWFR.RAG.003`은 청크마다 문서·시트·행·문단 위치를 요구한다.\n"
     "파일럿의 청킹 구현이 어느 수준까지 위치를 보존하는지 실측하고, 부족분을 정의한다.\n\n"
     "**확인 대상** — XLSX 시트·행, HWP/HWPX 문단, PDF 페이지."),
    ("D3 조사 — 근거 게이트 임계값",
     MS4, ["유형: 작업", "모듈: RAG"],
     "`SWFR.RAG.007` 근거 부족 시 답변 차단. 파일럿의 게이트 동작과 임계값을 확인하고,\n"
     "대표 질의세트로 오차단/미차단 비율을 측정하여 값을 정한다."),
    ("E 파일럿 인수 — 빌드·기동 확인",
     MS1, ["유형: 작업"],
     "파일럿 코드를 새 저장소에서 빌드·기동한다.\n\n"
     "- [ ] backend `./gradlew build` 통과\n"
     "- [ ] frontend `npm ci && npm run build` 통과\n"
     "- [ ] Flyway V1~V19 적용 확인 (pgvector 포함)\n"
     "- [ ] 로컬 Ollama 없이 `fake` 어댑터로 기동 확인"),
    ("E 파일럿 인수 — 설계검증 미해소 3건 점검",
     MS2, ["유형: 작업"],
     "`docs/90-pilot/HANDOFF.md` 의 설계검증 FAIL 항목 중 미해소 3건을 확인하고,\n"
     "본 과업 요구사항에 영향이 있는지 판정한다. 영향이 있으면 별도 이슈로 분리한다."),
    ("E 파일럿 인수 — 수직 슬라이스를 전체 경로로 확장",
     MS3, ["유형: 작업"],
     "파일럿은 349 클래스 설계 중 수직 슬라이스만 구현되어 있다.\n"
     "요구사항 41건이 요구하는 경로를 우선순위로 채운다. 설계 전체를 구현하지 않는다."),
    ("WBS 작성 — 자기참조 프로젝트 진척 기준선",
     MS2, ["유형: 문서"],
     "`docs/00-management/WBS.xlsx` 를 PM-002 양식으로 작성하여 저장소에 커밋한다.\n\n"
     "**이 파일이 자기참조 시연의 기준선이다.** 동시에 「GitHub만 쓰는 용역업체」가\n"
     "WBS를 어떻게 제공하는지에 대한 우리 답의 실증이기도 하다.\n\n"
     "항목·가중치·계획기간·연결 산출물 4개 컬럼이 필수."),
    ("최종 결과보고서 — 사례 조사",
     MS5, ["유형: 문서"],
     "과업지시서 Ⅱ.6 의 최종 결과보고서 필수 항목. W10 착수 (RSK-006)."),
    ("시험 케이스 작성 및 수행 (IM-005)",
     MS5, ["유형: 문서"],
     "요구사항 41건의 검증 방법(`T`/`D`/`R`)에 대응하는 시험 케이스를 작성하고 수행한다.\n"
     "결과는 IM-006 결함관리대장으로 이어진다.\n\n"
     "**요구사항 이행률 지표(`SWFR.PIP.008`)의 분자가 여기서 나온다.**"),
    ("산출물 일체 인도 — 소스·실행본·문서",
     MS6, ["유형: 문서"],
     "과업지시서 Ⅳ 산출물 목록에 따라 인도한다.\n\n"
     "- [ ] 소스코드 아카이브\n"
     "- [ ] 실행본\n"
     "- [ ] 요구사항정의서(IM-001) · 추적표(IM-002) · 설계서(IM-003)\n"
     "- [ ] 시험 산출물(IM-005) · 결함관리대장(IM-006) · 사용자매뉴얼(IM-007)\n"
     "- [ ] 최종 결과보고서\n\n"
     "인도 방식·지식재산권 귀속은 M1 협의 안건 8."),
]

REQ_ROW = re.compile(
    r"^\|\s*((?:SWFR|SER|QUR)\.[A-Z]{3}\.\d{3})\s*\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|\s*$"
)
SFR_HEAD = re.compile(r"^###\s+(SFR\.[A-Z]{3}\.\d{3})\s+(.+?)\s*$")


def parse(md_path: Path):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    reqs = []
    cur_sfr = cur_sfr_title = None
    cur_desc: list[str] = []
    cur_basis = None

    for ln in lines:
        m = SFR_HEAD.match(ln)
        if m:
            cur_sfr, cur_sfr_title = m.group(1), m.group(2)
            cur_desc, cur_basis = [], None
            continue
        if ln.startswith("> ") and cur_sfr:
            body = ln[2:].strip()
            if body.startswith("**근거**"):
                cur_basis = body.replace("**근거**", "").strip()
            elif body.startswith("※"):
                cur_desc.append(body)
            elif not body.startswith("**"):
                cur_desc.append(body)
            continue
        m = REQ_ROW.match(ln)
        if m:
            rid, text, prio, verif, scen = (g.strip() for g in m.groups())
            reqs.append({
                "id": rid,
                "module": rid.split(".")[1],
                "text": text,
                "priority": prio,
                "verification": verif,
                "scenario": scen,
                "sfr": cur_sfr,
                "sfr_title": cur_sfr_title,
                "sfr_desc": " ".join(cur_desc).strip(),
                "basis": cur_basis or "",
            })
    return reqs


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def issue_body(r: dict) -> str:
    pilot = PILOT.get(r["id"], "확인")
    verif_full = {"T": "테스트", "D": "시연", "R": "공식검토"}
    vlist = " · ".join(
        f"`{v}` {verif_full.get(v, v)}" for v in re.split(r"[·,\s]+", r["verification"]) if v
    )
    scen = r["scenario"].replace("·", " · ")
    return f"""## 요구사항

{r['text']}

## 상위 시스템 요구사항

**{r['sfr']}** {r['sfr_title']}

{r['sfr_desc']}

## 과업지시서 근거

{r['basis']}

## 검증

| 항목 | 값 |
|---|---|
| 요구사항 ID | `{r['id']}` |
| 모듈 | `{r['module']}` — {MODULE_NAME[r['module']]} |
| 중요도 | {r['priority']} |
| 검증 방법 | {vlist} |
| 검증 시나리오 | {scen} |
| 파일럿 판정 | **{pilot}** |

## 완료 조건

- [ ] 구현 (또는 파일럿 구현 확인)
- [ ] 검증 방법대로 확인하고 근거를 남긴다
- [ ] 커밋 메시지에 `[{r['id']}]` 를 포함한다
- [ ] `docs/traceability.csv` 에 반영되는지 확인한다

---
*이 이슈는 `docs/10-requirements/IM-001-요구사항정의서.md` 에서 자동 생성되었다.
내용을 여기서 고치지 말고 문서를 고친 뒤 `scripts/github/gen_bootstrap.py` 를 다시 실행한다.*
"""


def main(md: str, out: str):
    reqs = parse(Path(md))
    assert len(reqs) == 41, f"요구사항 {len(reqs)}건 — 41건이어야 한다"
    ids = [r["id"] for r in reqs]
    assert len(set(ids)) == 41, "중복 ID 존재"
    missing = set(ids) - set(PILOT)
    assert not missing, f"파일럿 판정 누락: {missing}"

    L = []
    w = L.append
    w("#!/usr/bin/env bash")
    w("# AX Link — GitHub 저장소 부트스트랩")
    w("#")
    w("# 자동 생성 파일이다. 직접 고치지 말고 gen_bootstrap.py 를 고친다.")
    w("#")
    w("# 사전 조건")
    w("#   1. gh CLI 설치 후  gh auth login")
    w("#   2. 저장소가 이미 생성되어 있어야 한다 (아래 REPO 확인)")
    w("#")
    w("# 실행:  bash scripts/github/bootstrap.sh")
    w("")
    w("set -euo pipefail")
    w('REPO="${AXLINK_REPO:-jypark-user/axlink}"')
    w('echo "대상 저장소: $REPO"')
    w('gh repo view "$REPO" >/dev/null || { echo "저장소를 찾을 수 없다: $REPO"; exit 1; }')
    w("")
    w("# 같은 이름이 이미 있으면 건너뛴다 — 여러 번 실행해도 안전하다.")
    w("mk_label() {")
    w('  gh label create "$1" --repo "$REPO" --description "$2" --color "$3" 2>/dev/null \\')
    w('    || gh label edit "$1" --repo "$REPO" --description "$2" --color "$3" >/dev/null')
    w("}")
    w("")
    w('echo "── 라벨"')
    for name, desc, color in TYPE_LABELS + STATUS_LABELS + VERIF_LABELS:
        w(f"mk_label {sh_quote(name)} {sh_quote(desc)} {color}")
    for code, color in MODULE_COLOR.items():
        w(f"mk_label {sh_quote('모듈: ' + code)} {sh_quote(MODULE_NAME[code])} {color}")
    w("")
    w('echo "── 마일스톤"')
    w("mk_milestone() {")
    w('  local state="${4:-open}"')
    w('  gh api "repos/$REPO/milestones" -f title="$1" -f due_on="$2" -f description="$3" \\')
    w('    -f state="$state" >/dev/null 2>&1 && echo "  + $1" || echo "  = $1 (이미 있음)"')
    w("}")
    for title, due, desc, closed in MILESTONES:
        state = "closed" if closed else "open"
        w(f"mk_milestone {sh_quote(title)} {sh_quote(due + 'T14:59:59Z')} "
          f"{sh_quote(desc)} {state}")
    w("")
    w('echo "── 이슈"')
    w("# 기존 이슈 제목을 한 번만 받아온다. 제목에 특수문자가 많아 검색 API 대신 정확 일치로 비교한다.")
    w('EXISTING=$(mktemp)')
    w('trap \'rm -f "$EXISTING"\' EXIT')
    w('gh issue list --repo "$REPO" --state all --limit 500 --json title --jq \'.[].title\' > "$EXISTING"')
    w('echo "  기존 이슈 $(wc -l < "$EXISTING")건 확인"')
    w("mk_issue() {")
    w('  local title="$1" milestone="$2" labels="$3" body="$4"')
    w('  if grep -Fxq "$title" "$EXISTING"; then echo "  = $title"; return; fi')
    w('  gh issue create --repo "$REPO" --title "$title" --milestone "$milestone" \\')
    w('    --label "$labels" --body "$body" >/dev/null')
    w('  echo "  + $title"')
    w("}")
    w("")

    for r in reqs:
        ms = OVERRIDE_MILESTONE.get(r["id"], MODULE_MILESTONE[r["module"]])
        pilot = PILOT[r["id"]]
        verifs = [v for v in re.split(r"[·,\s]+", r["verification"]) if v in ("T", "D", "R")]
        labels = ["유형: 요구사항", f"모듈: {r['module']}", f"파일럿: {pilot}"] + [
            f"검증: {v}" for v in verifs
        ]
        title = f"[{r['id']}] {r['text'].split('.')[0].strip()}"
        title = re.sub(r"\*\*", "", title)
        if len(title) > 100:
            title = title[:97] + "…"
        w(
            f"mk_issue {sh_quote(title)} {sh_quote(ms)} "
            f"{sh_quote(','.join(labels))} {sh_quote(issue_body(r))}"
        )

    w("")
    for title, ms, labels, body in EXTRA_ISSUES:
        w(f"mk_issue {sh_quote(title)} {sh_quote(ms)} {sh_quote(','.join(labels))} {sh_quote(body)}")

    w("")
    w('echo')
    w('echo "완료. 확인: gh issue list --repo $REPO --limit 60"')

    Path(out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"생성: {out}")
    print(f"  요구사항 이슈 {len(reqs)}건 + 작업 이슈 {len(EXTRA_ISSUES)}건 = {len(reqs)+len(EXTRA_ISSUES)}건")
    print(f"  마일스톤 {len(MILESTONES)}개")
    print(f"  라벨 {len(TYPE_LABELS)+len(STATUS_LABELS)+len(VERIF_LABELS)+len(MODULE_COLOR)}개")
    from collections import Counter
    print("  파일럿 판정:", dict(Counter(PILOT[r['id']] for r in reqs)))
    print("  마일스톤 배정:", dict(Counter(
        OVERRIDE_MILESTONE.get(r['id'], MODULE_MILESTONE[r['module']]).split()[0] for r in reqs)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
