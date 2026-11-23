"""WBS 항목 확인 요청의 스냅샷 (SWFR.WEB.004).

등록 시점의 "산출물 제출 여부"를 남겨야 한다. 여기서 남기는 것은 파일·문서 대조 결과이고
제출·검토·승인을 확인한 사실이 아니다. 스냅샷을 뜨는 일이 판정 저장이나 활동 기록을 남기면 안 된다.
"""

import pytest

from app.db import fetch_one, tx
from app.review import snapshot
from tests.conftest import requires_db
from tests.test_wbs_schedule_api import no_plan, plan_file  # noqa: F401 — 픽스처 재사용

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def clean_requests():
    yield
    with tx() as cur:
        cur.execute("delete from review_request where project_id = %s", (PID,))


def _counts() -> tuple[int, int]:
    with tx() as cur:
        events = fetch_one(
            cur, "select count(*) as n from activity_event where project_id = %s", (PID,)
        )["n"]
        judged = fetch_one(
            cur,
            "select count(*) as n from wbs_item where project_id = %s and judged_at is not null",
            (PID,),
        )["n"]
    return int(events), int(judged)


@requires_db
def test_WBS_요청_스냅샷에_산출물_대조와_근거_기준이_남는다(
    client, client_token, plan_file, clean_requests  # noqa: F811
):
    token = client_token("r2")
    # 항목 행을 먼저 만들어 둔다(현행 WBS 를 한 번 읽으면 생긴다)
    with tx() as cur:
        from app.dashboard import service as dashboard_service

        dashboard_service.current_wbs_rows(cur, PID)
    before = _counts()

    res = client.post(
        f"/api/projects/{PID}/review-requests",
        json={"targetType": "WBS_ITEM", "targetKey": "1.1", "title": "착수보고 완료 확인"},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    detail = client.get(f"/api/review-requests/{rid}", headers=_auth(token)).json()
    snap = detail["snapshot"]

    assert snap["actual"] == pytest.approx(1.0)
    assert snap["deliverable"] == "착수보고서.md"
    # 시험 사업에는 그 파일도 문서도 없다. 대조 결과는 지연(종료일 경과)이다
    assert snap["file_check"] == "OVERDUE"
    # 판정은 WBS 자동 예상 산출물 항목으로 한다(V73)
    assert snap["file_rule"] == "DESIGNATED" and snap["file_ref"] == "예상 산출물 1건 중 0건 제출"
    # 산출물 항목에 닿지 못했다. 정식 제출·승인은 모름으로 남긴다(파일 대조로 대신하지 않음)
    assert snap["submission"] == "UNKNOWN" and snap["approval"] == "UNKNOWN"
    assert snap["task_key"] and snap["scope_hash"] and snap["weight"] == pytest.approx(0.2)
    assert "repo_revision" in snap  # 저장소를 수집하지 않았으면 None 이다

    # 확인 요청 등록 활동 한 줄만 늘었다. 스냅샷이 판정을 저장하거나 활동을 남기지 않았다
    events, judged = _counts()
    assert events == before[0] + 1
    assert judged == before[1]


def test_새_필드는_사람_말_라벨이_있다():
    for key in ("file_check", "file_rule", "file_ref", "repo_revision", "submission",
                "approval", "product_version", "plan_version"):
        assert key in snapshot.FIELD_LABELS
    assert snapshot.FIELD_LABELS["file_check"] == "파일 대조"
    assert snapshot.FIELD_LABELS["submission"] == "정식 제출"
