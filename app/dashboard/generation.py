"""자연어 → 위젯 명세 (SWFR.WEB.001 · 절대 규칙 1·2).

LLM 이 하는 일은 셋뿐이다. 카탈로그에서 지표를 고르고, 차원을 고르고, 템플릿을 고른다.
값은 시맨틱 레이어가 집계하고 화면은 템플릿이 그린다. 고른 것이 카탈로그에 없으면
NOT_EXPRESSIBLE 로 거절한다. 억지로 맞추지 않는다.
"""

import json
import re
from typing import Any

from app.ai.llm import llm_port
from app.auth.models import AuthPrincipal
from app.common import errors
from app.dashboard.models import (
    WidgetGenerateRequest,
    WidgetGenerateResponse,
    WidgetGenerationRejection,
)
from app.dashboard.widget_template import TEMPLATES, TIME_TEMPLATES, is_template
from app.semantic import catalog as catalog_module
from app.semantic import service as semantic
from app.semantic.catalog import Catalog, MeasureDef
from app.semantic.models import WidgetOptions, WidgetQuery, WidgetSpec

GENERATED = "GENERATED"
NOT_EXPRESSIBLE = "NOT_EXPRESSIBLE"

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def generate(
    cur: Any, principal: AuthPrincipal, req: WidgetGenerateRequest
) -> WidgetGenerateResponse:
    prompt = req.prompt.strip()
    if not prompt:
        raise errors.validation_failed("prompt 가 비어 있습니다.")
    if req.template is not None and not is_template(req.template):
        raise errors.validation_failed(f"알 수 없는 위젯 템플릿: {req.template}")

    catalog = catalog_module.load(cur)
    result = llm_port().complete(system_prompt(catalog), prompt)
    choice = parse_choice(result.text)
    if choice is None:
        return _reject("AI 응답을 명세로 읽지 못했습니다.", [], prompt)

    measure_key = choice.get("measure")
    if not measure_key:
        unmatched = [str(t) for t in choice.get("unmatched") or []]
        reason = str(choice.get("reason") or "카탈로그에 없는 지표를 요구했습니다.")
        return _reject(reason, unmatched, prompt)
    measure = catalog.measure(str(measure_key))
    if measure is None:
        return _reject("카탈로그에 없는 지표를 요구했습니다.", [str(measure_key)], prompt)

    template = req.template or _template_of(choice)
    dimensions = _dimensions_of(choice, measure, catalog, template)
    if template is None:
        template = _default_template(dimensions, catalog)

    spec = WidgetSpec(
        template=template,
        title=str(choice.get("title") or measure.label),
        query=WidgetQuery(
            measure=measure.key,
            dimensions=dimensions,
            filters=[],
            projectScope=list(req.projectScope),
            limit=None,
        ),
        options=WidgetOptions(sort="desc"),
    )
    try:
        preview = semantic.run(cur, principal, spec)
    except errors.ApiError as exc:
        if exc.code == "CATALOG_VALIDATION_FAILED":
            return _reject(exc.message, [], prompt)
        raise
    return WidgetGenerateResponse(status=GENERATED, spec=spec, preview=preview, rejection=None)


def system_prompt(catalog: Catalog) -> str:
    measures = "\n".join(
        f"- {m.key}: {m.label}. {m.description} (허용 차원: {', '.join(m.allowed_dimensions)})"
        for m in catalog.active_measures()
    )
    dimensions = "\n".join(
        f"- {d.key}: {d.label}. {d.description}" for d in catalog.active_dimensions()
    )
    return (
        "당신은 사업 관리 대시보드의 위젯 명세를 고르는 도우미다. 수치를 만들지 않는다. "
        "아래 카탈로그에 있는 키만 고른다.\n"
        "출력은 JSON 객체 하나뿐이다. 설명을 붙이지 않는다.\n"
        '형식: {"measure": "<지표 key>", "dimensions": ["<차원 key>"], '
        '"template": "<템플릿>", "title": "<한국어 제목>"}\n'
        "차원은 0~2개이고 지표의 허용 차원에서만 고른다. 추이를 물으면 period_ 차원을 쓴다.\n"
        "요청에 맞는 지표가 카탈로그에 없으면 "
        '{"measure": null, "reason": "<이유>", "unmatched": ["<맞출 수 없던 용어>"]} '
        "를 출력한다.\n\n"
        f"## 지표\n{measures}\n\n## 차원\n{dimensions}\n\n"
        f"## 템플릿\n{', '.join(TEMPLATES)}\n"
        "숫자 하나는 STAT_CARD, 범주 비교는 BAR_CHART, 추이는 LINE_CHART, 구성비는 PIE_CHART, "
        "두 차원은 STACKED_BAR_CHART 또는 HEATMAP."
    )


def parse_choice(text: str) -> dict[str, Any] | None:
    """모델 답에서 JSON 객체 하나를 꺼낸다. 생각 블록·코드 펜스는 걷어낸다."""
    body = _THINK.sub("", text).strip()
    fenced = _FENCE.search(body)
    if fenced:
        body = fenced.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _template_of(choice: dict[str, Any]) -> str | None:
    template = choice.get("template")
    if not isinstance(template, str):
        return None
    template = template.strip().upper()
    return template if is_template(template) else None


def _dimensions_of(
    choice: dict[str, Any], measure: MeasureDef, catalog: Catalog, template: str | None
) -> list[str]:
    """허용되지 않은 차원은 버린다. 작은 모델은 차원을 자주 틀리는데, 지표가 맞으면 값은
    그대로 카탈로그 집계라 거절보다 차원을 바로잡는 편이 낫다."""
    raw = choice.get("dimensions") or []
    if not isinstance(raw, list):
        raw = []
    picked: list[str] = []
    for key in raw:
        if isinstance(key, str) and key in measure.allowed_dimensions and key not in picked:
            picked.append(key)
    picked = picked[:2]

    if template in TIME_TEMPLATES and not any(_is_time(catalog, k) for k in picked):
        period = next((k for k in ("period_month", "period_week", "period_day")
                       if k in measure.allowed_dimensions), None)
        if period:
            picked = [period, *picked][:2]
    if not picked and template not in (None, "STAT_CARD") and measure.default_dimension:
        picked = [measure.default_dimension]
    return picked


def _default_template(dimensions: list[str], catalog: Catalog) -> str:
    if not dimensions:
        return "STAT_CARD"
    if any(_is_time(catalog, d) for d in dimensions):
        return "LINE_CHART"
    return "STACKED_BAR_CHART" if len(dimensions) == 2 else "BAR_CHART"


def _is_time(catalog: Catalog, key: str) -> bool:
    d = catalog.dimension(key)
    return d is not None and d.value_type == "TIME"


def _reject(reason: str, unmatched: list[str], prompt: str) -> WidgetGenerateResponse:
    return WidgetGenerateResponse(
        status=NOT_EXPRESSIBLE,
        spec=None,
        preview=None,
        rejection=WidgetGenerationRejection(
            reason=reason,
            unmatchedTerms=unmatched,
            suggestedAction=(
                "카탈로그에 있는 지표로 다시 묻거나, AI 질의에서 문서 근거로 확인하세요."
            ),
            suggestedQuestion=prompt,
        ),
    )
