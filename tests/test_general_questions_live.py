"""일반 질문 답변율 (ARC-015). Ollama 와 개발 DB 가 떠 있을 때만 돈다.

불특정 다수가 던질 질문은 특정 문서를 가리키지 않는다. "잘 되고 있어?", "문제 있어?",
"뭐부터 봐야 해?" 같은 질문에 몇 개나 답하는지를 숫자로 재고, 경로·게이트를 손볼 때마다
같은 세트로 다시 잰다. 본문 생성은 하지 않는다. 답을 만들 수 있는지는 판정과 근거 게이트,
블록 유무에서 갈리므로 거기까지만 돌려 시간을 아낀다.

    AXLINK_DATABASE_URL=...axlink pytest tests/test_general_questions_live.py -s

결과는 var/general_questions_report.md 에 남는다.
"""

import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.ai.embedding import embedding_port
from app.ai.llm import llm_port
from app.auth.models import AuthPrincipal
from app.config import settings
from app.db import tx
from app.rag import entity_table, overview, route_cache, routing, search
from app.semantic import catalog as catalog_module
from tests.conftest import _db_reachable

PID = "c0000000-0000-4000-8000-000000000001"
ADMIN = AuthPrincipal(
    user_id="d0000000-0000-4000-8000-000000000001",
    org_id="00000000-0000-0000-0000-000000000000",
    org_type="CLIENT",
    role="SUPER_ADMIN",
)

# 발주기관 담당자가 던질 법한 일반 질문. 문서를 가리키는 질문은 일부러 적게 넣었다.
QUESTIONS: list[tuple[str, str]] = [
    # 전체 상태
    ("상태", "지금 사업 잘 되고 있어?"),
    ("상태", "요즘 어떻게 진행되고 있나요?"),
    ("상태", "문제 있는 거 있어?"),
    ("상태", "현재 사업 현황 알려줘"),
    ("상태", "이번 주에 특별히 볼 게 있나?"),
    ("상태", "전체적으로 괜찮은 거야?"),
    ("상태", "진행 상황 요약해 줘"),
    ("상태", "뭐가 제일 걱정이야?"),
    # 우선순위
    ("우선순위", "지금 가장 급한 작업이 뭐야?"),
    ("우선순위", "먼저 처리해야 할 이슈가 뭐지?"),
    ("우선순위", "뭐부터 봐야 해?"),
    ("우선순위", "가장 심각한 문제는 뭐야?"),
    ("우선순위", "오늘 확인해야 할 거 있어?"),
    # 진척·일정
    ("진척", "진척률이 얼마나 돼?"),
    ("진척", "일정 늦어지고 있어?"),
    ("진척", "계획보다 얼마나 밀렸어?"),
    ("진척", "지연된 작업 있어?"),
    ("진척", "언제쯤 끝나?"),
    ("진척", "이번 달 목표는 뭐야?"),
    # 이슈
    ("이슈", "이슈가 몇 건이야?"),
    ("이슈", "열린 이슈 목록 보여줘"),
    ("이슈", "아직 작업이 안 된 이슈 목록 조회해줘"),
    ("이슈", "완료된 이슈는 뭐가 있어?"),
    ("이슈", "심각한 이슈 있어?"),
    ("이슈", "이슈 처리는 잘 되고 있어?"),
    ("이슈", "누가 이슈를 제일 많이 갖고 있어?"),
    # 요구사항
    ("요구사항", "요구사항이 몇 개야?"),
    ("요구사항", "요구사항 목록 보여줘"),
    ("요구사항", "요구사항 이행률은?"),
    ("요구사항", "아직 구현 안 된 요구사항 있어?"),
    ("요구사항", "필수 요구사항은 다 되고 있어?"),
    # 산출물
    ("산출물", "산출물 제출 현황 알려줘"),
    ("산출물", "아직 안 낸 산출물이 뭐야?"),
    ("산출물", "승인된 산출물은 몇 개야?"),
    ("산출물", "설계서는 나왔어?"),
    # 리스크
    ("리스크", "리스크 있어?"),
    ("리스크", "등록된 리스크 목록 보여줘"),
    ("리스크", "위험 요소 뭐가 있어?"),
    # 품질·시험
    ("품질", "시험은 통과했어?"),
    ("품질", "품질은 어때?"),
    ("품질", "결함이 얼마나 나왔어?"),
    # 문서 내용
    ("문서", "이 사업의 목적이 뭐야?"),
    ("문서", "납품해야 하는 산출물이 뭐뭐야?"),
    ("문서", "인수 조건이 뭐야?"),
    ("문서", "도구 연동은 어떤 방식으로 해?"),
    ("문서", "진척률은 어떻게 계산해?"),
    # 무관
    ("무관", "오늘 날씨 어때?"),
    ("무관", "파이썬 리스트 정렬 방법 알려줘"),
]


def _models_ready() -> bool:
    try:
        res = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        return res.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not (_db_reachable() and _models_ready()), reason="Ollama 와 DB 가 떠 있어야 한다"
)


@pytest.fixture(autouse=True)
def real_models(monkeypatch):
    """conftest 는 모델 없이 돌게 fake 로 바꿔 둔다. 이 시험은 실모델이 목적이다."""
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_provider", "ollama")


def _answerable(cur, catalog, llm, question: str) -> dict:
    """답을 만들 수 있는가. service.stream 의 판정·블록·게이트 부분만 돌린다."""
    t0 = time.time()
    routed = route_cache.decide(cur, catalog, llm, question)
    d = routed.decision
    route_ms = int((time.time() - t0) * 1000)
    if d.type == routing.OFF_TOPIC:
        return {"route": "OFF_TOPIC", "measure": "", "blocks": 0, "gate": False, "sim": 0.0,
                "ok": False, "route_ms": route_ms, "cached": routed.cached}
    blocks = 0
    if d.type == routing.AGGREGATE:
        blocks += 1
    if d.type == routing.OVERVIEW:
        blocks += len(overview.build(cur, ADMIN, [PID]))
    if d.listing:
        entity = entity_table.FROM_SOURCE_TYPE.get(d.listing)
        table = entity_table.build(cur, entity, d.listing_status, [PID], 60) if entity else None
        blocks += 1 if table else 0
    gate_ok = False
    sim = 0.0
    if d.type != routing.AGGREGATE or not blocks:
        vec = embedding_port().embed([question])[0]
        found = search.search_with_vector(cur, vec, d.rewritten or question, [PID])
        gate_ok, sim = found.passes_gate(), found.max_similarity
    ok = bool(blocks) or gate_ok
    label = d.type if not d.listing else f"LIST:{d.listing}/{d.listing_status}"
    # 서비스와 같은 규칙. 근거도 그림도 없는 문서 질문은 현황으로 내려간다
    if not ok and d.type == routing.DOCUMENT and settings.rag_overview_fallback:
        blocks = len(overview.build(cur, ADMIN, [PID]))
        ok = bool(blocks)
        label = "DOCUMENT→OVERVIEW" if ok else label
    return {
        "route": label,
        "measure": d.measure.key if d.measure else "",
        "blocks": blocks,
        "gate": gate_ok,
        "sim": round(sim, 2),
        "ok": ok,
        "route_ms": route_ms,
        "cached": routed.cached,
    }


def test_일반_질문_답변율():
    llm = llm_port()
    rows = []
    with tx() as cur:
        catalog = catalog_module.load(cur)
        for group, q in QUESTIONS:
            r = _answerable(cur, catalog, llm, q)
            rows.append((group, q, r))
            print(f"{'O' if r['ok'] else 'X'} [{group}] {q} -> {r['route']} {r['measure']} "
                  f"blocks={r['blocks']} gate={r['gate']} sim={r['sim']} ({r['route_ms']}ms)")

    relevant = [(g, q, r) for g, q, r in rows if g != "무관"]
    answered = sum(1 for _, _, r in relevant if r["ok"])
    rate = answered / len(relevant)
    blocked_unrelated = sum(1 for g, _, r in rows if g == "무관" and not r["ok"])

    out = Path("var") / "general_questions_report.md"
    out.parent.mkdir(exist_ok=True)
    lines = [
        f"# 일반 질문 답변율 · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}Z"
        f" · {settings.llm_model}",
        "",
        f"답변 가능 {answered}/{len(relevant)} ({rate:.0%}) · 무관 질문 차단 {blocked_unrelated}/2",
        "",
        "| | 갈래 | 질문 | 경로 | 블록 | 게이트 | 유사도 | 판정 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for g, q, r in rows:
        lines.append(
            f"| {'O' if r['ok'] else 'X'} | {g} | {q} | {r['route']} {r['measure']} "
            f"| {r['blocks']} | {'통과' if r['gate'] else '차단'} | {r['sim']} "
            f"| {r['route_ms']}ms |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n답변 가능 {answered}/{len(relevant)} ({rate:.0%}) · 보고서 {out}")

    assert blocked_unrelated == 2, "무관한 질문은 막혀야 한다"
    assert rate >= settings.rag_general_answer_floor, f"답변율 {rate:.0%} 가 바닥 아래다"
