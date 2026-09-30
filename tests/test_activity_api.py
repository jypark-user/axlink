"""활동 기록과 알림. 확인 요청·문서 업로드가 기록되고 상대 역할에게만 알림으로 간다."""

from app.db import tx
from tests.conftest import requires_db
from tests.test_documents import _upload, _xlsx_bytes

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _clear():
    with tx() as cur:
        cur.execute("delete from activity_event where project_id = %s", (PID,))
        cur.execute("delete from notification_seen")
        cur.execute("delete from review_request where project_id = %s", (PID,))
        cur.execute(
            "delete from doc_chunk where project_id = %s and source_type = 'DOCUMENT_UPLOAD'",
            (PID,),
        )
        cur.execute("delete from document_upload where project_id = %s", (PID,))


def _notifications(client, token: str) -> dict:
    return client.get("/api/notifications", headers=_auth(token)).json()


@requires_db
def test_확인_요청은_용역사에게_조치_보고는_발주기관에게_알린다(client, client_token):
    _clear()
    client_tok, contractor_tok = client_token("r2"), client_token("r3")

    created = client.post(
        f"/api/projects/{PID}/review-requests",
        json={
            "targetType": "METRIC", "targetKey": "REPRESENTATIVE",
            "title": "진척률 확인", "body": "근거를 보여 주세요",
        },
        headers=_auth(client_tok),
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    # 용역사에게 미읽음 1, 발주기관(자기 행동)에게는 0
    mine = _notifications(client, contractor_tok)
    assert mine["unread"] == 1 and mine["items"][0]["kind"] == "REVIEW_REQUESTED"
    assert mine["items"][0]["targetKey"] == request_id
    assert "진척률 확인" in mine["items"][0]["summary"]
    assert _notifications(client, client_tok)["unread"] == 0

    # 용역사가 열어 보면 미읽음이 사라진다
    seen = client.post("/api/notifications/seen", json={}, headers=_auth(contractor_tok))
    assert seen.status_code == 200
    assert _notifications(client, contractor_tok)["unread"] == 0

    # 조치 보고는 발주기관에게
    reported = client.post(
        f"/api/review-requests/{request_id}/report", json={"body": "근거 붙였습니다"},
        headers=_auth(contractor_tok),
    )
    assert reported.status_code == 200, reported.text
    theirs = _notifications(client, client_tok)
    assert theirs["unread"] == 1 and theirs["items"][0]["kind"] == "REVIEW_REPORTED"

    # 활동 탭은 역할과 무관하게 둘 다 본다
    activity = client.get(f"/api/projects/{PID}/activity", headers=_auth(contractor_tok)).json()
    assert [e["kind"] for e in activity["content"]] == ["REVIEW_REPORTED", "REVIEW_REQUESTED"]


@requires_db
def test_기록만_하는_활동은_알림_수에_안_들어간다(client, client_token):
    from app.activity import service as activity

    _clear()
    with tx() as cur:
        activity.record(
            cur, project_id=PID, kind=activity.SNAPSHOT_TAKEN, audience=activity.LOG,
            summary="일별 스냅샷 기록 2026-09-28: 진척 73.9%", actor_label="스케줄러",
        )
    for who in ("r2", "r3"):
        got = _notifications(client, client_token(who))
        assert got["unread"] == 0 and all(i["kind"] != "SNAPSHOT_TAKEN" for i in got["items"])
    # 활동 탭에는 있다
    tab = client.get(f"/api/projects/{PID}/activity", headers=_auth(client_token("r3"))).json()
    assert [e["kind"] for e in tab["content"]] == ["SNAPSHOT_TAKEN"]
    _clear()


@requires_db
def test_용역사가_문서를_올리면_발주기관이_알림을_받는다(client, client_token):
    _clear()
    contractor_tok = client_token("r3")
    res = _upload(client, contractor_tok, "설계서 초안.xlsx", _xlsx_bytes("알림확인"))
    assert res.status_code == 201, res.text

    got = _notifications(client, client_token("r2"))
    assert got["unread"] == 1
    assert got["items"][0]["kind"] == "DOCUMENT_UPLOADED"
    assert got["items"][0]["targetKey"] == res.json()["id"]
    assert "설계서 초안.xlsx" in got["items"][0]["summary"]
    # 올린 용역사 본인에게는 안 간다
    assert _notifications(client, contractor_tok)["unread"] == 0
    _clear()
