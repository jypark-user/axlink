"""인포 템플릿 카탈로그 (ARC-012 · SWFR.WEB.001).

템플릿은 입력 계약이다. 23종이 DB CHECK(V18)·프런트와 같은 목록인지, 계약이 고른 것을
바로잡는지, 예시 명세가 실제 카탈로그에서 돌아가는지를 본다.
"""

import re
from pathlib import Path

import pytest

from app.dashboard import generation, widget_template
from app.dashboard.widget_template import CATALOG, fits, prompt_guide
from tests.conftest import requires_db

_ROOT = Path(__file__).resolve().parent.parent
_ADMIN = "r1"


def _v18_templates() -> set[str]:
    sql = (_ROOT / "db" / "migration" / "V18__infographic_catalog.sql").read_text("utf-8")
    block = sql.split("ck_widget__template check (template in (", 1)[1].split("))", 1)[0]
    return set(re.findall(r"'([A-Z_]+)'", block))


def test_카탈로그는_DB_CHECK_와_같은_23종이다():
    assert len(CATALOG) == 23
    assert set(widget_template.TEMPLATES) == _v18_templates()


def test_프런트_렌더러_등록과_같은_목록이다():
    src = (_ROOT / "frontend/src/features/widgets/renderer-registry.ts").read_text("utf-8")
    registered = set(re.findall(r"^\s+([A-Z_]+): [A-Za-z]+Widget,", src, re.MULTILINE))
    assert registered == set(widget_template.TEMPLATES)


def test_예시는_자기_계약에_맞는다():
    """관리자 화면이 예시로 그리는 명세다. 계약을 어기면 화면이 빈다."""
    time_keys = {"period_day", "period_week", "period_month"}
    for t in CATALOG:
        assert fits(t.key, t.measure_types[0], list(t.example_dimensions), time_keys) is None, t.key


def test_계약은_차원_수와_시간축을_본다():
    time = {"period_month"}
    assert fits("LINE_CHART", "COUNT", ["period_month"], time) is None
    assert "기간 차원" in fits("LINE_CHART", "COUNT", ["issue_status"], time)
    assert "1개 이상" not in (fits("HEATMAP", "COUNT", ["issue_status"], time) or "")
    assert "2개 이상" in fits("HEATMAP", "COUNT", ["issue_status"], time)
    assert fits("HEATMAP", "COUNT", ["issue_status"], time, strict=False) is None
    assert "까지" in fits("STAT_CARD", "COUNT", ["a", "b"], time, strict=False)
    assert "기간 차원을 쓰지" in fits("PIE_CHART", "COUNT", ["period_month"], time)
    assert "지표만" in fits("RADAR_CHART", "COUNT", ["contractor_org"], time)
    assert "알 수 없는" in fits("NOPE", "COUNT", [], time)


def test_프롬프트_안내는_언제_고르는지를_같이_준다():
    guide = prompt_guide()
    assert "STAT_CARD" in guide and "GANTT_SUMMARY" not in guide
    chat = prompt_guide(chat_only=True)
    assert "STAT_CARD" not in chat and "LINE_CHART" in chat
    # 관리자 화면과 같은 문장을 쓰고, 그 문장이 판단 근거라고 첫 줄에 못 박는다
    assert widget_template.get("BAR_CHART").when in guide
    assert guide.startswith("템플릿은 각 줄의 「언제 고르는가」를 근거로 고른다")
    assert "차원 1~2개 · 기간 차원 필수" in guide  # LINE_CHART 의 계약 요약


def test_예시_값은_계약의_모양을_따른다():
    """쇼케이스가 그리는 값이다. 차원 수·전체값·목표값이 계약과 어긋나면 빈 그림이 된다."""
    from app.dashboard import template_samples

    for t in CATALOG:
        d = template_samples.sample_for(t)
        assert d.rows, t.key
        assert d.dimensions == list(t.example_dimensions), t.key
        assert (d.total is not None) == t.uses_total, t.key
        assert (d.target is not None) == t.uses_target, t.key
        assert (d.previousTotal is not None) == t.uses_previous, t.key
        if t.key == "GANTT_SUMMARY":
            assert {c.key for c in d.columns} >= {"planned", "actual"}
        else:
            expected = [f"d{i}" for i in range(len(d.dimensions))] + ["value"]
            assert [c.key for c in d.columns] == expected, t.key
        # 같은 입력이면 같은 값. 그림이 열 때마다 달라지면 쇼케이스가 아니다
        assert d.model_dump() == template_samples.sample_for(t).model_dump()


def test_시스템_프롬프트가_카탈로그_안내를_담는다():
    from tests.test_widget_generation import _catalog

    prompt = generation.system_prompt(_catalog())
    assert "언제 고르는가" in prompt
    assert widget_template.get("LINE_CHART").when in prompt


@requires_db
def test_API_는_23종의_계약을_돌려준다(client, client_token):
    res = client.get(
        "/api/widget-templates", headers={"Authorization": f"Bearer {client_token(_ADMIN)}"}
    )
    assert res.status_code == 200, res.text
    items = res.json()["templates"]
    assert len(items) == 23
    line = next(i for i in items if i["key"] == "LINE_CHART")
    assert line["timeAxis"] == "REQUIRED" and line["dimsMin"] == 1
    assert line["example"]["dimensions"] == ["period_month"]
    assert len(line["sample"]["rows"]) > 0 and line["sample"]["columns"][0]["type"] == "date"


@requires_db
@pytest.mark.parametrize("template", [t.key for t in CATALOG if t.key != "GANTT_SUMMARY"])
def test_예시_명세는_시맨틱_카탈로그에서_돈다(client, client_token, template):
    """예시가 카탈로그에 없는 지표·차원을 가리키면 관리자 화면 미리보기가 깨진다."""
    t = widget_template.get(template)
    headers = {"Authorization": f"Bearer {client_token(_ADMIN)}"}
    res = client.post(
        "/api/widgets/preview",
        json={
            "spec": {
                "template": t.key,
                "title": t.example_title,
                "query": {
                    "measure": t.example_measure,
                    "dimensions": list(t.example_dimensions),
                    "filters": [],
                    "projectScope": [],
                    "limit": None,
                },
                "options": None,
            }
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["measure"] == t.example_measure


@requires_db
def test_계약을_어긴_명세는_저장_전에_막힌다(client, client_token):
    headers = {"Authorization": f"Bearer {client_token(_ADMIN)}"}
    res = client.post(
        "/api/widgets/preview",
        json={
            "spec": {
                "template": "LINE_CHART",
                "title": "기간 없는 추이",
                "query": {
                    "measure": "issue_count",
                    "dimensions": ["issue_status"],
                    "filters": [],
                    "projectScope": [],
                    "limit": None,
                },
                "options": None,
            }
        },
        headers=headers,
    )
    assert res.status_code == 400
    assert "기간 차원" in res.json()["message"]
