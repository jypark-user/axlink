"""인포 템플릿 쇼케이스용 예시 값 (ARC-012 4절).

관리자 화면은 실제 사업의 집계가 아니라 **계약에서 만든 예시 값**으로 23종을 전부 보여 준다.
사업에 값이 없어 빈 그림이 뜨면 쇼케이스가 되지 않기 때문이다. 값은 씨앗으로 만들어 매번
같고, 모양(차원 수·시간축·전체값·목표값)은 그 템플릿의 계약을 그대로 따른다. 프런트에 목업
파일을 두지 않는다는 규칙(작업 규약 1절 7번)은 지킨다. 값은 이 API 에서만 온다.
"""

from typing import Any

from app.dashboard.widget_template import TIME_REQUIRED, TemplateDef
from app.semantic.models import WidgetColumn, WidgetDataResponse, WidgetRow

# 차원 키 → (열 이름, 예시 범주). 실제 카탈로그의 라벨과 같은 어휘를 쓴다.
_DIM_VALUES: dict[str, tuple[str, list[str]]] = {
    "period_day": ("일", [f"2026-09-{d:02d}" for d in range(1, 29)]),
    "period_week": ("주", [f"2026-W{w:02d}" for w in range(23, 38)]),
    "period_month": ("월", [f"2026-{m:02d}" for m in range(3, 10)]),
    "contractor_org": ("용역사", ["넥스트소프트", "한빛시스템", "대성ICT", "유니콘랩"]),
    "issue_severity": ("심각도", ["긴급", "높음", "보통", "낮음"]),
    "issue_status": ("이슈 상태", ["신규", "진행", "검토", "종료"]),
    "assignee": ("담당자", ["김민준", "이서연", "박지호", "최수아", "정하준", "강예린"]),
    "work_product_type": (
        "산출물 유형",
        ["사업수행계획서", "요구사항정의서", "설계서", "시험계획서", "시험결과서", "사용자매뉴얼"],
    ),
    "iso_activity": ("활동", ["PM.1", "PM.2", "PM.3", "PM.4", "SI.1", "SI.2", "SI.3"]),
    "work_product_status": ("산출물 상태", ["미제출", "초안", "제출", "승인"]),
    "requirement_priority": ("중요도", ["필수", "권장", "선택", "제외"]),
    "requirement_status": ("요구사항 상태", ["정의", "설계", "구현", "시험", "검증"]),
    "risk_status": ("리스크 상태", ["식별", "대응중", "종료"]),
    "risk_severity": ("리스크 심각도", ["높음", "중간", "낮음"]),
    "project": ("사업", ["AX Link", "통합관제 고도화", "민원포털 개편"]),
}

_UNIT = {"COUNT": "건", "RATE_PCT": "%", "DAYS": "일", "PCT_POINT": "%p"}
_TARGET = {"RATE_PCT": 90.0}


def _seeded(seed: int, measure_type: str) -> float:
    """씨앗 하나에 값 하나. 같은 입력이면 항상 같은 값이라 그림이 흔들리지 않는다."""
    base = (seed * 37 + 11) % 97
    if measure_type == "RATE_PCT":
        return float(40 + base % 60)
    if measure_type == "DAYS":
        return float(1 + base % 30)
    if measure_type == "PCT_POINT":
        return float(round(base % 21 - 10, 1))
    return float(1 + base % 40)


def _dim(key: str) -> tuple[str, list[str]]:
    return _DIM_VALUES.get(key, (key, ["가", "나", "다", "라"]))


def _value_column_type(measure_type: str) -> str:
    return "percent" if measure_type in ("RATE_PCT", "PCT_POINT") else "number"


def sample_for(t: TemplateDef) -> WidgetDataResponse:
    measure_type = t.measure_types[0]
    dims = list(t.example_dimensions)
    columns: list[WidgetColumn] = []
    axes: list[list[str]] = []
    for i, key in enumerate(dims):
        label, values = _dim(key)
        is_time = key.startswith("period_")
        n = _category_count(t, key, i)
        columns.append(WidgetColumn(key=f"d{i}", label=label, type="date" if is_time else "string"))
        axes.append(values[:n])

    if t.key == "GANTT_SUMMARY":
        return _gantt(t, columns, axes)

    columns.append(
        WidgetColumn(key="value", label=t.example_title, type=_value_column_type(measure_type))
    )
    rows: list[WidgetRow] = []
    if not axes:
        rows.append(WidgetRow(values={"value": _seeded(1, measure_type)}))
    elif len(axes) == 1:
        rows = [
            WidgetRow(values={"d0": a, "value": _seeded(i + 1, measure_type)})
            for i, a in enumerate(axes[0])
        ]
    else:
        rows = [
            WidgetRow(values={"d0": a, "d1": b, "value": _seeded(i * 7 + j + 3, measure_type)})
            for i, a in enumerate(axes[0])
            for j, b in enumerate(axes[1])
        ]

    total = WidgetRow(values={"value": _seeded(99, measure_type)}) if t.uses_total else None
    previous = WidgetRow(values={"value": _seeded(98, measure_type)}) if t.uses_previous else None
    return WidgetDataResponse(
        measure=t.example_measure,
        measureLabel=t.example_title,
        unit=_UNIT.get(measure_type),
        dimensions=dims,
        columns=columns,
        rows=rows,
        total=total,
        previousTotal=previous,
        target=_TARGET.get(measure_type) if t.uses_target else None,
        appliedProjectIds=[],
        truncated=False,
        generatedAt="sample",
    )


def _category_count(t: TemplateDef, key: str, position: int) -> int:
    """범주 수는 계약의 상한 안에서 그림이 읽히는 만큼만."""
    _, values = _dim(key)
    if key.startswith("period_"):
        return min(len(values), 7 if key == "period_month" else len(values))
    cap = t.category_max or 6
    if position == 1:  # 둘째 축은 범례 수. 넷이면 충분하다
        return min(len(values), 4)
    return min(len(values), cap, 8 if t.time_axis == TIME_REQUIRED else cap)


def _gantt(
    t: TemplateDef, columns: list[WidgetColumn], axes: list[list[str]]
) -> WidgetDataResponse:
    """일정 요약은 계획·실적 두 열을 받는다. 시맨틱 집계가 못 만드는 모양이라 예시로만 보인다."""
    names = axes[0] if axes else ["설계", "구현", "시험"]
    columns = [columns[0] if columns else WidgetColumn(key="d0", label="항목", type="string")]
    columns += [
        WidgetColumn(key="planned", label="계획", type="percent"),
        WidgetColumn(key="actual", label="실적", type="percent"),
    ]
    rows = [
        WidgetRow(values={"d0": n, "planned": float(60 + i * 12), "actual": float(45 + i * 15)})
        for i, n in enumerate(names)
    ]
    return WidgetDataResponse(
        measure=t.example_measure, measureLabel=t.example_title, unit="%",
        dimensions=list(t.example_dimensions), columns=columns, rows=rows,
        total=None, previousTotal=None, target=None, appliedProjectIds=[],
        truncated=False, generatedAt="sample",
    )


def as_plain(data: WidgetDataResponse) -> dict[str, Any]:
    return data.model_dump()
