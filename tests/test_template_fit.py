"""인포 템플릿이 알맞게 쓰이는가 (PoC 보완 F-11, 2026-11-16 검토).

검토에서 나온 것: 구성비 그림(도넛·상태 흐름)에 요구사항 이행률(비율)이 들어가 가운데 합계가
이행률의 합으로 찍히고, 띠가 VERIFIED·ACCEPTED 로만 갈렸다. 요구사항·산출물 건수 지표가 없어
「요구사항 구성비」 같은 예문은 그대로는 성립하지 않았다.

여기서는 위젯 추가 대화상자의 예문 하나하나와 대시보드 프리셋 하나하나가 실제 카탈로그의
지표·차원으로 성립하고 템플릿 계약(지표 유형·차원 수·기간축)에 맞는지 본다.
"""

import re
from pathlib import Path

import pytest

from app.dashboard import widget_template
from app.dashboard.widget_template import CATALOG, PROMPT_EXAMPLES, fits
from app.db import tx
from app.semantic import catalog as catalog_module
from tests.conftest import requires_db

_ROOT = Path(__file__).resolve().parent.parent
_TIME = {"period_day", "period_week", "period_month"}


def test_구성비_그림은_건수_지표만_받는다():
    for key in ("PIE_CHART", "DONUT_CHART", "STATUS_FLOW", "TREEMAP", "PARETO",
                "STACKED_BAR_CHART", "CUMULATIVE_FLOW"):
        assert widget_template.get(key).measure_types == ("COUNT",), key
    reason = fits("DONUT_CHART", "RATE_PCT", ["requirement_priority"], _TIME)
    assert reason is not None and "COUNT" in reason


def test_예문마다_지표와_차원을_적어_둔다():
    assert set(PROMPT_EXAMPLES) == {t.key for t in CATALOG}
    for key, examples in PROMPT_EXAMPLES.items():
        assert examples, key
        for text, measure, dims in examples:
            assert text and measure and isinstance(dims, tuple), (key, text)


def _presets() -> list[tuple[str, str, str, tuple[str, ...]]]:
    """dashboard-presets.ts 의 위젯 (템플릿, 제목, 지표, 차원)."""
    src = (_ROOT / "frontend/src/features/dashboard/dashboard-presets.ts").read_text("utf-8")
    out = []
    for block in re.findall(r"\{\s*template: '([A-Z_]+)',(.*?)\n\s*\}", src, re.DOTALL):
        template, body = block
        title = re.search(r"title: '([^']*)'", body)
        measure = re.search(r"measure: '([a-z_0-9]+)'", body)
        dims = re.search(r"dimensions: \[([^\]]*)\]", body)
        if not (title and measure):
            continue
        out.append((
            template, title.group(1), measure.group(1),
            tuple(re.findall(r"'([a-z_]+)'", dims.group(1))) if dims else (),
        ))
    return out


def test_프리셋을_읽어_낸다():
    presets = _presets()
    assert len(presets) >= 20
    titles = {t for _, t, _, _ in presets}
    assert {"우선순위별 요구사항 비중", "요구사항 단계 분포"} <= titles


@pytest.fixture(scope="module")
def catalog():
    with tx() as cur:
        return catalog_module.load(cur)


def _check(catalog, template: str, measure_key: str, dims: tuple[str, ...]) -> str | None:
    measure = catalog.measure(measure_key)
    if measure is None or measure.status != "ACTIVE":
        return f"카탈로그에 없는 지표 {measure_key}"
    bad = [d for d in dims if d not in measure.allowed_dimensions]
    if bad:
        return f"{measure_key} 가 받지 않는 차원 {bad}"
    return fits(template, measure.value_type, list(dims), _TIME)


@requires_db
def test_예문은_모두_카탈로그에서_성립하고_계약에_맞는다(catalog):
    problems = [
        f"{key} 「{text}」: {why}"
        for key, examples in PROMPT_EXAMPLES.items()
        for text, measure, dims in examples
        if (why := _check(catalog, key, measure, dims))
    ]
    assert problems == []


@requires_db
def test_프리셋_위젯은_모두_카탈로그에서_성립하고_계약에_맞는다(catalog):
    problems = [
        f"{template} 「{title}」: {why}"
        for template, title, measure, dims in _presets()
        if (why := _check(catalog, template, measure, dims))
    ]
    assert problems == []


@requires_db
@pytest.mark.parametrize(
    ("measure", "dimension"),
    [("requirement_count", "requirement_status"), ("work_product_count", "work_product_status")],
)
def test_건수_지표는_짝_비율_지표와_모집단이_같다(client, client_token, measure, dimension):
    """요구사항 건수의 합 = 이행률의 분모, 산출물 건수의 합 = 승인률의 분모."""
    pair = {"requirement_count": "requirement_fulfillment_rate",
            "work_product_count": "work_product_approval_rate"}[measure]
    headers = {"Authorization": f"Bearer {client_token('r1')}"}

    def run(key: str, dims: list[str]) -> dict:
        res = client.post(
            "/api/widgets/preview",
            json={"spec": {"template": "DATA_TABLE", "title": key, "query": {
                "measure": key, "dimensions": dims, "filters": [], "projectScope": [],
                "limit": None}, "options": None}},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        return res.json()

    by_status = run(measure, [dimension])
    total = sum(r["values"]["value"] or 0 for r in by_status["rows"])
    with tx() as cur:
        rate = catalog_module.load(cur).measure(pair)
        assert rate is not None and rate.denominator_expr == "count(*)"
        cur.execute(
            f"select count(*) as n from {rate.base_table} e where {rate.row_filter}"  # noqa: S608
        )
        assert total == cur.fetchone()["n"]
