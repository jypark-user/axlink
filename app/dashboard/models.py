"""진척 DTO. 프런트 types/api.ts 와 필드가 1:1 이다."""

from pydantic import BaseModel

# 측정의 성격. 화면에서 자기신고와 관측을 구분해 보여야 한다 —
# 셋이 어긋날 때 어느 쪽을 의심할지가 이 구분에서 갈린다.
SELF_REPORTED = "SELF_REPORTED"
OBSERVED = "OBSERVED"


class ProgressMeasure(BaseModel):
    """진척 한 갈래. 분모가 셋 다 달라서 값만 나란히 두면 오해를 부른다."""

    value: float | None
    numerator: int | None
    denominator: int | None
    label: str
    unit: str
    kind: str
    note: str | None


class ProgressResponse(BaseModel):
    baseDate: str  # noqa: N815 — 프런트 계약 필드명
    level: str
    representative: float | None
    basis: str
    gap: float | None

    wbs: ProgressMeasure
    wbsPlanned: float | None  # noqa: N815
    wbsDeviation: float | None  # noqa: N815
    wbsDeclaredPlanned: float | None  # noqa: N815

    issue: ProgressMeasure
    workProduct: ProgressMeasure  # noqa: N815

    behind: list[str]
    warnings: list[str]
    planVersion: str | None  # noqa: N815
    planUpdatedAt: str | None  # noqa: N815
