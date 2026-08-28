"""GitHub 원본 → 표준 모델 매핑. 우리 저장소의 실제 이슈 모양을 그대로 쓴다."""

from app.standard import mapping

_REQUIREMENT = {
    "number": 1,
    "title": "[SWFR.CON.001] 커넥터는 공통 인터페이스를 구현해야 한다",
    "body": "## 검증\n\n| 항목 | 값 |\n|---|---|\n| 중요도 | 필수 |\n",
    "state": "open",
    "html_url": "https://github.com/o/r/issues/1",
    "labels": [{"name": "유형: 요구사항"}, {"name": "모듈: CON"}],
    "created_at": "2026-08-20T00:00:00Z",
    "updated_at": "2026-08-21T00:00:00Z",
}

_TASK = {
    "number": 42,
    "title": "D1 조사 — 커넥터 읽기 전용 보장 검증 방법",
    "body": "조사한다.",
    "state": "closed",
    "closed_at": "2026-08-25T00:00:00Z",
    "html_url": "https://github.com/o/r/issues/42",
    "labels": [{"name": "유형: 작업"}],
    "created_at": "2026-08-20T00:00:00Z",
    "updated_at": "2026-08-25T00:00:00Z",
}


def test_requirement_label_routes_to_requirement():
    assert mapping.classify_issue(_REQUIREMENT) == "REQUIREMENT"


def test_task_label_routes_to_issue():
    assert mapping.classify_issue(_TASK) == "ISSUE"


def test_code_in_title_routes_even_without_label():
    payload = {**_REQUIREMENT, "labels": []}
    assert mapping.classify_issue(payload) == "REQUIREMENT"


def test_requirement_splits_code_from_title():
    rec = mapping.to_requirement(_REQUIREMENT)
    assert rec["code"] == "SWFR.CON.001"
    assert rec["title"] == "커넥터는 공통 인터페이스를 구현해야 한다"
    assert rec["priority"] == "MUST"
    assert rec["status"] == "DEFINED"


def test_closed_requirement_is_implemented_not_verified():
    """닫힌 이슈는 구현까지다. 검증(VERIFIED)은 시험 결과가 붙을 때 올린다."""
    rec = mapping.to_requirement({**_REQUIREMENT, "state": "closed"})
    assert rec["status"] == "IMPLEMENTED"


def test_issue_key_carries_tool_prefix():
    rec = mapping.to_issue(_TASK)
    assert rec["issue_key"] == "GH-42"
    assert rec["status"] == "CLOSED"
    assert rec["resolved_at"] == "2026-08-25T00:00:00Z"


def test_commit_takes_first_message_line():
    rec = mapping.to_code_change(
        "commit",
        {
            "sha": "abc123",
            "html_url": "https://github.com/o/r/commit/abc123",
            "commit": {
                "message": "feat(rag): 임베딩 색인  [ARC-001]\n\n본문은 제목이 아니다",
                "author": {"name": "jypark", "date": "2026-08-28T01:19:11Z"},
            },
        },
    )
    assert rec["kind"] == "COMMIT"
    assert rec["title"] == "feat(rag): 임베딩 색인  [ARC-001]"
    assert rec["state"] == "CREATED"


def test_merged_pull_request_state():
    rec = mapping.to_code_change(
        "pull_request",
        {
            "title": "docs: 전환 결정",
            "state": "closed",
            "merged_at": "2026-08-28T01:19:11Z",
            "created_at": "2026-08-27T01:19:11Z",
            "head": {"ref": "docs/arc-001"},
            "user": {"login": "jypark-user"},
            "html_url": "https://github.com/o/r/pull/52",
        },
    )
    assert rec["kind"] == "MERGE_REQUEST"
    assert rec["state"] == "MERGED"
    assert rec["ref_name"] == "docs/arc-001"


def test_commit_without_time_is_dropped():
    assert mapping.to_code_change("commit", {"sha": "x", "commit": {}}) is None
