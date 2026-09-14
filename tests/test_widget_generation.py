"""자연어 → 위젯 명세 (SWFR.WEB.001 · 절대 규칙 1·2).

모델은 스텁이다. 보려는 것은 모델이 무엇을 골랐든 값은 카탈로그 집계에서만 오고,
카탈로그 밖을 고르면 거절되는가다.
"""

from app.ai.port import LlmResult
from app.dashboard import generation
from app.semantic.catalog import Catalog, DimensionDef, MeasureDef
from tests.conftest import requires_db
from tests.test_dashboard_api import PID, _auth, seeded_issues  # noqa: F401 (픽스처)

# ---------------------------------------------------------------- DB 없이


def _catalog() -> Catalog:
    cat = Catalog()
    cat.measures["open_issue_count"] = MeasureDef(
        key="open_issue_count", label="열린 이슈 수", description="", base_table="issue",
        join_clause=None, row_filter=None, value_expr="count(*)", value_type="COUNT", unit="건",
        allowed_dimensions=("issue_severity",), allowed_filters=(),
        default_dimension="issue_severity", target_value=None, status="ACTIVE",
    )
    cat.measures["retired"] = MeasureDef(
        key="retired", label="폐기", description="", base_table="issue", join_clause=None,
        row_filter=None, value_expr="count(*)", value_type="COUNT", unit="건",
        allowed_dimensions=(), allowed_filters=(), default_dimension=None, target_value=None,
        status="DEPRECATED",
    )
    cat.dimensions["issue_severity"] = DimensionDef(
        key="issue_severity", label="이슈 심각도", description="", select_expr="e.severity",
        label_expr=None, requires_join=None, value_type="CATEGORY", status="ACTIVE",
    )
    return cat


def test_모델_답에서_JSON_만_꺼낸다():
    text = '<think>음...</think>\n```json\n{"measure": "open_issue_count", "dimensions": []}\n```'
    assert generation.parse_choice(text) == {"measure": "open_issue_count", "dimensions": []}
    assert generation.parse_choice("지표가 없습니다") is None
    assert generation.parse_choice('["list"]') is None


def test_시스템_프롬프트는_카탈로그_키만_보여준다():
    prompt = generation.system_prompt(_catalog())
    assert "open_issue_count" in prompt
    assert "retired" not in prompt  # 폐기된 지표는 고를 수 없다
    assert "STAT_CARD" in prompt


# ---------------------------------------------------------------- API


class _StubLlm:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LlmResult:
        self.calls.append((system, user))
        return LlmResult(text=self.text, model="stub")


@requires_db
def test_생성은_지표와_차원과_템플릿만_고르고_값은_집계에서_온다(
    client, client_token, monkeypatch, seeded_issues  # noqa: F811
):
    stub = _StubLlm(
        '{"measure": "open_issue_count", "dimensions": ["issue_severity"], '
        '"template": "PIE_CHART", "title": "심각도별 열린 이슈"}'
    )
    monkeypatch.setattr(generation, "llm_port", lambda: stub)
    res = client.post(
        "/api/widgets/generate",
        json={"prompt": "심각도별 열린 이슈 보여줘", "template": None,
              "projectScope": [PID], "dashboardId": None},
        headers=_auth(client_token("r2")),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "GENERATED"
    assert body["spec"]["template"] == "PIE_CHART"
    assert body["spec"]["query"]["measure"] == "open_issue_count"
    assert body["spec"]["query"]["projectScope"] == [PID]
    # 값은 모델 답에 없던 것이다. 집계에서 왔다.
    values = {r["values"]["d0"]: r["values"]["value"] for r in body["preview"]["rows"]}
    assert values["MAJOR"] >= 2
    # 프롬프트에는 카탈로그가 들어간다
    assert "open_issue_count" in stub.calls[0][0]


@requires_db
def test_사이드바에서_고른_템플릿이_모델_선택보다_우선한다(client, client_token, monkeypatch):
    stub = _StubLlm('{"measure": "open_issue_count", "dimensions": [], "template": "PIE_CHART"}')
    monkeypatch.setattr(generation, "llm_port", lambda: stub)
    body = client.post(
        "/api/widgets/generate",
        json={"prompt": "열린 이슈", "template": "STAT_CARD", "projectScope": [PID],
              "dashboardId": None},
        headers=_auth(client_token("r2")),
    ).json()
    assert body["status"] == "GENERATED" and body["spec"]["template"] == "STAT_CARD"
    assert body["spec"]["query"]["dimensions"] == []


@requires_db
def test_추이_템플릿인데_기간_축이_없으면_붙여_준다(client, client_token, monkeypatch):
    stub = _StubLlm('{"measure": "issue_count", "dimensions": ["nonsense"], "title": "추이"}')
    monkeypatch.setattr(generation, "llm_port", lambda: stub)
    body = client.post(
        "/api/widgets/generate",
        json={"prompt": "이슈 추이", "template": "LINE_CHART", "projectScope": [PID],
              "dashboardId": None},
        headers=_auth(client_token("r2")),
    ).json()
    assert body["status"] == "GENERATED"
    assert body["spec"]["query"]["dimensions"] == ["period_month"]


@requires_db
def test_카탈로그에_없는_지표를_고르면_거절한다(client, client_token, monkeypatch):
    stub = _StubLlm('{"measure": "developer_happiness", "dimensions": []}')
    monkeypatch.setattr(generation, "llm_port", lambda: stub)
    body = client.post(
        "/api/widgets/generate",
        json={"prompt": "개발자 행복도", "template": None, "projectScope": [PID],
              "dashboardId": None},
        headers=_auth(client_token("r2")),
    ).json()
    assert body["status"] == "NOT_EXPRESSIBLE"
    assert body["spec"] is None and body["preview"] is None
    assert body["rejection"]["unmatchedTerms"] == ["developer_happiness"]


@requires_db
def test_모델이_못_고르겠다고_하면_그_이유를_돌려준다(client, client_token, monkeypatch):
    stub = _StubLlm('{"measure": null, "reason": "예산 지표가 없다", "unmatched": ["예산"]}')
    monkeypatch.setattr(generation, "llm_port", lambda: stub)
    body = client.post(
        "/api/widgets/generate",
        json={"prompt": "예산 집행률", "template": None, "projectScope": [PID],
              "dashboardId": None},
        headers=_auth(client_token("r2")),
    ).json()
    assert body["status"] == "NOT_EXPRESSIBLE"
    assert body["rejection"]["reason"] == "예산 지표가 없다"
    assert body["rejection"]["unmatchedTerms"] == ["예산"]
    assert body["rejection"]["suggestedQuestion"] == "예산 집행률"
