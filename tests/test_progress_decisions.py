"""진척·지표 결정(2026-11-12). DEC-20 작업 단위 격차 경고 문턱, DEC-01 일정 준수율 집계."""

from datetime import date

from app.dashboard import deliverable, repository
from app.dashboard.models import LinkedIssue
from app.dashboard.service import gap_warning
from app.db import tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _issue(status: str) -> LinkedIssue:
    return LinkedIssue(key="RM-204", title="외부 연계 협의", status=status, url=None)


def test_below_80_no_warning_even_if_missing() -> None:
    """실적 40%·20% 는 미제출이어도 경고하지 않는다(ARC-016 4절, DEC-20 (b))."""
    assert gap_warning(0.4, deliverable.OVERDUE, [_issue("IN_PROGRESS")]) is None
    assert gap_warning(0.79, deliverable.MISSING, []) is None


def test_80_or_more_with_missing_deliverable_or_open_issue() -> None:
    assert gap_warning(0.8, deliverable.MISSING, []) == "실적 80% 신고, 산출물 미제출"
    assert (
        gap_warning(0.85, deliverable.SUBMITTED, [_issue("IN_PROGRESS")])
        == "실적 85% 신고, 열린 연결 이슈 RM-204"
    )
    assert (
        gap_warning(1.0, deliverable.OVERDUE, [_issue("OPEN")])
        == "실적 100% 신고, 산출물 미제출 · 열린 연결 이슈 RM-204"
    )


def test_80_or_more_but_submitted_and_issue_closed() -> None:
    assert gap_warning(0.85, deliverable.SUBMITTED, [_issue("RESOLVED")]) is None
    assert gap_warning(None, deliverable.MISSING, []) is None  # 실적을 모르면 경고하지 않는다
    assert gap_warning(1.0, deliverable.NONE, []) is None  # 산출물 열이 없는 작업


# ---------------------------------------------------------------- DEC-01 일정 준수율 (DB)

@requires_db
def test_schedule_compliance_same_set_and_last_close() -> None:
    """분자·분모 같은 집합. 기한 없음·기한 전 제외, 다시 열렸다 늦게 닫힌 것은 미달성."""
    rows = [
        # (이름, 기한, 상태, 닫힌 시각 UTC)
        ("T-1", "2026-04-30", "CLOSED", "2026-04-28T01:00:00Z"),  # 기한 안
        ("T-2", "2026-08-31", "OPEN", None),                        # 기한 경과 미달성
        ("T-3", "2026-11-30", "OPEN", None),                        # 기한 전
        ("T-4", None, "OPEN", None),                                # 기한 없음
        ("T-5", "2026-05-31", "CLOSED", "2026-06-03T01:00:00Z"),  # 늦게 닫힘
        # 기한 날 밤 23시(KST) 에 닫음 = UTC 14시. 사업 날짜로 기한 안이다
        ("T-6", "2026-06-30", "CLOSED", "2026-06-30T14:00:00Z"),
    ]
    with tx() as cur:
        before = repository.schedule_compliance(cur, [PID], date(2026, 9, 15)).get(PID, (0, 0))
        early_at = date(2026, 4, 15)
        early_before = repository.schedule_compliance(cur, [PID], early_at).get(PID, (0, 0))
        for name, due, state, closed in rows:
            cur.execute(
                "insert into milestone (project_id, external_id, title, due_on, state, closed_at) "
                "values (%s, %s, %s, %s, %s, %s)",
                (PID, f"dec01:{name}", name, due, state, closed),
            )
        try:
            got = repository.schedule_compliance(cur, [PID], date(2026, 9, 15))[PID]
            assert (got[0] - before[0], got[1] - before[1]) == (2, 4)  # T-1·T-6 / T-1·2·5·6
            # 기준일을 모든 기한 전으로 돌리면 새 마일스톤은 평가 대상이 아니다
            early = repository.schedule_compliance(cur, [PID], date(2026, 4, 15)).get(PID, (0, 0))
            assert early == early_before
        finally:
            cur.execute("delete from milestone where external_id like 'dec01:%%'")
