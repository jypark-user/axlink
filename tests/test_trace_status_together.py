"""추적 링크 상태 처리의 통합 시험 (SWFR.PIP.003 · ARC-024 · ARC-027 · ARC-028).

GH-146(연결 해석 정정)과 GH-150(미해결 ID)이 같은 함수를 고쳤다.
한 번의 링크 생성에서 세 처리가 같이 맞는지 본다.

- 다른 연결로 잘못 이어졌던 자동 링크 → SUPERSEDED(연결 해석 정정, 대체 링크 있음)
- 사업에 없는 요구사항 ID → 잇지 않고 미해결 기록
- 원천 근거가 사라진 링크만 BROKEN
"""

from app.db import fetch_one, tx
from app.standard import repository, trace_service
from tests.conftest import requires_db
from tests.test_issue_source import PID, _gh_commit, _gh_issue, _issue_of, _Sources


@requires_db
def test_정정_미해결_끊김이_한_번의_링크_생성에서_함께_맞다():
    src = _Sources()
    try:
        with tx() as cur:
            src.connect(cur, "ghA", "GITHUB", "저장소 A", "x/verify-a", "https://api.github.com")
            src.connect(cur, "ghB", "GITHUB", "저장소 B", "x/verify-b", "https://api.github.com")
            src.load(cur, "ghA", [
                ("issue:5", "issue", _gh_issue("x/verify-a", 5, "A 5번", "", ["유형: 작업"])),
                ("issue:6", "issue", _gh_issue("x/verify-a", 6, "A 6번", "", ["유형: 작업"])),
                ("commit:" + "f" * 40, "commit", _gh_commit(
                    "x/verify-a", "f" * 40,
                    "fix(integration): 검증  [SWFR.TST.777]\n\n이유.\n\nRefs: GH-5")),
            ])
            src.load(cur, "ghB", [
                ("issue:5", "issue", _gh_issue("x/verify-b", 5, "B 5번", "", ["유형: 작업"])),
            ])
            src.promote(cur)
            commit = fetch_one(cur, "select id from code_change where tool_connection_id = %s",
                               (src.ids["ghA"],))["id"]
            b5 = _issue_of(cur, src.ids["ghB"], "GH-5")["id"]
            a6 = _issue_of(cur, src.ids["ghA"], "GH-6")["id"]

            def old(to_id, text):
                return fetch_one(
                    cur,
                    """
                    insert into trace_link (project_id, from_type, from_id, to_type, to_id,
                                            link_kind, origin, status, evidence_kind,
                                            evidence_text)
                    values (%s, 'CODE_CHANGE', %s, 'ISSUE', %s, 'IMPLEMENTS', 'AUTO', 'ACTIVE',
                            'TEXT_ISSUE_REF', %s) returning id
                    """,
                    (PID, commit, to_id, text),
                )["id"]

            wrong = old(b5, "Refs: GH-5")     # 수정 전 해석이 만든 다른 연결 링크
            gone = old(a6, "Refs: GH-6")      # 커밋에서 GH-6 이 사라졌다

            result = trace_service.build_project_links(cur, PID)
            cur.execute(
                "select id, status, status_reason, superseded_by from trace_link "
                "where id = any(%s::uuid[])", ([wrong, gone],))
            rows = {r["id"]: r for r in cur.fetchall()}
            refs = [r for r in repository.list_unresolved_refs(cur, PID)
                    if r["code"] == "SWFR.TST.777"]
            new_a = fetch_one(
                cur,
                "select tl.id from trace_link tl join issue i on i.id = tl.to_id "
                "where tl.from_id = %s and tl.status = 'ACTIVE' and i.tool_connection_id = %s",
                (commit, src.ids["ghA"]),
            )

        assert rows[wrong]["status"] == "SUPERSEDED"
        assert rows[wrong]["status_reason"].startswith("연결 해석 정정으로 대체")
        assert rows[wrong]["superseded_by"] == new_a["id"]
        assert rows[gone]["status"] == "BROKEN"
        assert rows[gone]["status_reason"] == "원천 근거가 다시 확인되지 않음"
        assert len(refs) == 1 and refs[0]["source_type"] == "CODE_CHANGE"
        assert result.unknown_codes >= 1 and result.superseded >= 1 and result.broken >= 1
    finally:
        with tx() as cur:
            cur.execute("delete from requirement_unresolved_ref where project_id = %s", (PID,))
            src.cleanup(cur)
