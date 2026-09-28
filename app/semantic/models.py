"""위젯 명세·데이터 DTO. 프런트 types/api.ts 와 필드가 1:1 이다.

위젯은 코드가 아니라 데이터(spec_json)다. 여기 모델이 그 데이터의 모양이다.
"""

from typing import Any

from pydantic import BaseModel, Field


class WidgetFilter(BaseModel):
    field: str
    op: str
    value: Any = None


class WidgetQuery(BaseModel):
    measure: str
    dimensions: list[str] = Field(default_factory=list)
    filters: list[WidgetFilter] = Field(default_factory=list)
    projectScope: list[str] = Field(default_factory=list)  # noqa: N815 (프런트 계약 필드명)
    limit: int | None = None


class WidgetThreshold(BaseModel):
    warn: float
    critical: float


class WidgetOptions(BaseModel):
    unit: str | None = None
    sort: str | None = None
    threshold: WidgetThreshold | None = None
    stacked: bool | None = None
    showLegend: bool | None = None  # noqa: N815
    compareWithPrevious: bool | None = None  # noqa: N815
    columns: list[str] | None = None


class WidgetSpec(BaseModel):
    template: str
    title: str = ""
    query: WidgetQuery
    options: WidgetOptions | None = None


class WidgetColumn(BaseModel):
    key: str
    label: str
    type: str


class WidgetRow(BaseModel):
    values: dict[str, Any]


class WidgetDataResponse(BaseModel):
    measure: str
    measureLabel: str  # noqa: N815
    unit: str | None
    dimensions: list[str]
    columns: list[WidgetColumn]
    rows: list[WidgetRow]
    total: WidgetRow | None
    previousTotal: WidgetRow | None  # noqa: N815
    target: float | None
    appliedProjectIds: list[str]  # noqa: N815
    truncated: bool
    generatedAt: str  # noqa: N815
    basis: str | None = None  # 산출 근거. 화면 설명과 답변 프롬프트가 같이 쓴다


class SemanticMeasureResponse(BaseModel):
    key: str
    label: str
    description: str | None
    unit: str | None
    allowedDimensions: list[str]  # noqa: N815
    allowedFilters: list[str]  # noqa: N815
    defaultTemplates: list[str]  # noqa: N815
    status: str


class SemanticDimensionResponse(BaseModel):
    key: str
    label: str
    description: str | None
    valueType: str  # noqa: N815
    enumValues: list[str]  # noqa: N815
    status: str


class SemanticFilterResponse(BaseModel):
    key: str
    field: str
    op: str
    label: str
    valueType: str  # noqa: N815
    enumValues: list[str]  # noqa: N815
    status: str


class SemanticCatalogResponse(BaseModel):
    measures: list[SemanticMeasureResponse]
    dimensions: list[SemanticDimensionResponse]
    filters: list[SemanticFilterResponse]
