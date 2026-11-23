"""실연동(Redmine) 시나리오: 실제 Redmine 프로젝트를 원천으로 수집한다 (AC-011-12).

재생 서버를 쓰지 않는다. 원천은 시험용 Redmine(axlink-rm)의 프로젝트 하나다. IM-009 TD-CON-2 와
같은 자료를 넣지 못했으므로(트래커·커스텀 필드는 관리자 화면에서만 만든다) 고정 기대값 대신
**원천 API 가 준 값과 원시본·표준 모델 값이 같은지** 본다. test_live_github.py 와 같은 원칙이다.
IM-009 기대값(R4 트래커·버전, R7 리스크 등)과의 대조는 재생 시험 UC-011-S12 가 맡는다.

돌리는 조건: AXLINK_LIVE_REDMINE=1, 시험용 DB(*_test), 수집 계정 API 키 AXLINK_VERIFY_RM_KEY.
- AXLINK_VERIFY_RM_URL: 시험 프로세스가 원천을 읽는 주소(기본 http://127.0.0.1:3000)
- AXLINK_VERIFY_RM_TARGET_URL: 대상 서버가 원천을 부르는 주소(기본 위와 같다). 운영 모드 서버는
  http 원천을 루프백만 받으므로 대상 컨테이너 안 127.0.0.1:3000 에 중계를 둔다
- AXLINK_VERIFY_RM_PROJECT: 원천 프로젝트 식별자(기본 axlink-verify-b)

보는 것: 프로젝트의 일감 전부(리스크 트래커 포함)·버전·트래커가 원시본으로 수집되고, 일감의 트래커·
우선순위·버전·이슈관계·커스텀 필드·생성·갱신·닫힌 시각이 원천과 같게 보존되며, 표준 모델(이슈·
리스크·마일스톤·추적 링크)에 원천 값대로 올라간다.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.db import fetch_all, tx
from tests.fixtures.im009.seed import Seeder
from tests.scenarios.conftest import auth

pytestmark = [pytest.mark.db, pytest.mark.live, pytest.mark.live_tool]

KEY = os.environ.get("AXLINK_VERIFY_RM_KEY", "")
SOURCE_URL = os.environ.get("AXLINK_VERIFY_RM_URL", "http://127.0.0.1:3000").rstrip("/")
TARGET_RM_URL = os.environ.get("AXLINK_VERIFY_RM_TARGET_URL", SOURCE_URL).rstrip("/")
PROJECT = os.environ.get("AXLINK_VERIFY_RM_PROJECT", "axlink-verify-b")
LIVE = os.environ.get("AXLINK_LIVE_REDMINE") == "1"
OWNER = "TD-ACC-V1"
MAPPING = {"riskTracker": "리스크", "reqIdField": "REQ ID", "defectTracker": "결함"}
# 원시본에 원천 그대로 남아야 하는 일감 필드
KEPT = (
    "tracker", "status", "priority", "fixed_version", "custom_fields", "relations",
    "subject", "created_on", "updated_on", "closed_on",
)


class Source:
    """시험이 원천을 직접 읽는다. 대상 서버의 어댑터와 따로 부른다."""

    def __init__(self) -> None:
        self.c = httpx.Client(
            base_url=SOURCE_URL, headers={"X-Redmine-API-Key": KEY}, timeout=30
        )

    def close(self) -> None:
        self.c.close()

    def issues(self) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            res = self.c.get(
                "/issues.json",
                params={
                    "project_id": PROJECT, "status_id": "*", "include": "relations",
                    "limit": 100, "offset": offset, "sort": "id:asc",
                },
            )
            res.raise_for_status()
            body = res.json()
            out += body["issues"]
            offset += len(body["issues"])
            if not body["issues"] or offset >= body["total_count"]:
                return out

    def versions(self) -> list[dict]:
        res = self.c.get(f"/projects/{PROJECT}/versions.json")
        res.raise_for_status()
        return res.json()["versions"]


class LiveRedmine(Seeder):
    """IM-009 1·2절(조직·계정·사업·참여 업체)은 투입 스크립트 그대로, 연결과 수집은 실제 Redmine."""

    def base(self) -> None:
        self._orgs_and_clients()
        self._projects()
        self._contractors()
        self.state = "base"

    def connect_and_sync(self) -> dict:
        h = auth(self.tokens[OWNER])
        made = self._ok(
            self.c.post(
                f"/api/projects/{self.ids['TD-PRJ-1']}/connections",
                json={
                    "tool": "REDMINE",
                    "name": "실연동 Redmine",
                    "baseUrl": TARGET_RM_URL,
                    "targetResource": PROJECT,
                    "credential": {"accessToken": KEY},
                    "mappingRules": MAPPING,
                },
                headers=h,
            ),
            200,
            201,
        )
        cid = self.ids["RM-LIVE"] = str(made["id"])
        self._ok(self.c.post(f"/api/connections/{cid}/test", headers=h))
        self._ok(
            self.c.patch(f"/api/connections/{cid}/status", json={"status": "ACTIVE"}, headers=h)
        )
        res = self.c.post(f"/api/connections/{cid}/sync", json={"kind": "BACKFILL"}, headers=h)
        assert res.status_code == 202, f"수집 {res.status_code} {res.text[:300]}"
        return res.json()


@pytest.fixture(scope="module")
def live(target):
    if not LIVE:
        pytest.skip("Redmine 실연동 시험은 AXLINK_LIVE_REDMINE=1 일 때만 돈다")
    if not KEY:
        pytest.skip("AXLINK_VERIFY_RM_KEY(수집 계정 API 키)가 없다")
    w = LiveRedmine(target)
    src = Source()
    try:
        w.base()
        w.src = src
        yield w
    finally:
        src.close()
        w.cleanup()


@pytest.fixture(autouse=True)
def _live_tool_evidence(record_property):
    """실제 Redmine 을 원천으로 돈 실행이다. 검증 기록(record-junit)이 증거 종류로 읽는다."""
    record_property("proves", "live-tool")


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _name(entity: Any) -> str | None:
    return (entity or {}).get("name") if isinstance(entity, dict) else None


def test_UC_011_S12_Redmine_종류별_필드(target, live):
    """실제 Redmine 프로젝트의 일감·버전·트래커·이슈관계·커스텀 필드가 수집되고, 보존 필드와
    표준 모델 값이 원천과 같다 (AC-011-12)."""
    issues = live.src.issues()
    versions = live.src.versions()
    assert issues and versions, "원천 프로젝트에 일감·버전이 없다"
    trackers = {_name(i["tracker"]) for i in issues}
    assert MAPPING["riskTracker"] in trackers, f"원천에 리스크 트래커 일감이 없다: {trackers}"
    assert any(i.get("relations") for i in issues), "원천에 이슈관계가 없다"
    assert any(
        f.get("name") == MAPPING["reqIdField"] and f.get("value")
        for i in issues for f in i.get("custom_fields") or []
    ), "원천에 커스텀 필드 REQ ID 값이 없다"

    job = live.connect_and_sync()
    assert job["status"] == "SUCCEEDED", job
    cid, pid = live.ids["RM-LIVE"], live.ids["TD-PRJ-1"]
    with tx() as cur:
        raw = {
            r["external_id"]: r
            for r in fetch_all(
                cur,
                "select external_id, object_kind, payload_jsonb from raw_artifact "
                "where tool_connection_id = %s",
                (cid,),
            )
        }
        std_issues = {
            r["external_id"]: r
            for r in fetch_all(cur, "select * from issue where tool_connection_id = %s", (cid,))
        }
        std_risks = {
            r["external_id"]: r
            for r in fetch_all(cur, "select * from risk where tool_connection_id = %s", (cid,))
        }
        std_ms = {
            r["number"]: r
            for r in fetch_all(
                cur, "select * from milestone where tool_connection_id = %s", (cid,)
            )
        }
        links = fetch_all(
            cur,
            """
            select a.external_id as a, b.external_id as b, l.link_kind
              from trace_link l
              join issue a on a.id = l.from_id
              join issue b on b.id = l.to_id
             where l.project_id = %s and l.from_type = 'ISSUE' and l.to_type = 'ISSUE'
               and a.tool_connection_id = %s
            """,
            (pid, cid),
        )
    problems: list[str] = []

    # 원시본: 종류마다 원천 건수 그대로, 일감은 보존 필드가 원천과 같다
    kinds: dict[str, int] = {}
    for r in raw.values():
        kinds[r["object_kind"]] = kinds.get(r["object_kind"], 0) + 1
    if kinds.get("issue") != len(issues):
        problems.append(f"일감 원시본 {kinds.get('issue')}건, 원천 {len(issues)}건")
    if kinds.get("version") != len(versions):
        problems.append(f"버전 원시본 {kinds.get('version')}건, 원천 {len(versions)}건")
    if not kinds.get("tracker"):
        problems.append(f"트래커 원시본이 없다: {kinds}")
    for i in issues:
        got = (raw.get(str(i["id"])) or {}).get("payload_jsonb")
        if got is None:
            problems.append(f"일감 {i['id']} 원시본 없음")
            continue
        for field in KEPT:
            if got.get(field) != i.get(field):
                problems.append(
                    f"일감 {i['id']} {field}: 원시본 {got.get(field)!r} 원천 {i.get(field)!r}"
                )

    # 표준 모델: 리스크 트래커는 risk, 나머지는 issue(결함 트래커는 DEFECT)
    for i in issues:
        key, tracker = str(i["id"]), _name(i["tracker"])
        if tracker == MAPPING["riskTracker"]:
            r = std_risks.get(key)
            if r is None or r["title"] != i["subject"].strip():
                problems.append(f"리스크 {key} 표준 모델 {r and r['title']}")
            continue
        s = std_issues.get(key)
        if s is None:
            problems.append(f"일감 {key} 이 표준 모델 이슈에 없다")
            continue
        want_kind = "DEFECT" if tracker == MAPPING["defectTracker"] else "GENERAL"
        closed = (i.get("status") or {}).get("is_closed")
        checks = {
            "issue_key": f"RM-{key}",
            "title": i["subject"].strip(),
            "source_priority": _name(i.get("priority")),
            "issue_kind": want_kind,
            "external_url": f"{TARGET_RM_URL}/issues/{key}",
        }
        for col, want in checks.items():
            if s[col] != want:
                problems.append(f"일감 {key} {col}: 표준 {s[col]!r} 원천 {want!r}")
        if bool(closed) != (s["status"] == "CLOSED"):
            problems.append(f"일감 {key} 상태 표준 {s['status']} 원천 닫힘={closed}")
        if _dt(s["source_updated_at"]) != _dt(i["updated_on"]):
            problems.append(f"일감 {key} 갱신 시각 {s['source_updated_at']} 원천 {i['updated_on']}")
        if closed and _dt(s["resolved_at"]) != _dt(i.get("closed_on")):
            problems.append(f"일감 {key} 닫힌 시각 {s['resolved_at']} 원천 {i.get('closed_on')}")

    # 버전 → 마일스톤: 기한·상태
    for v in versions:
        m = std_ms.get(v["id"])
        if m is None:
            problems.append(f"버전 {v['name']} 이 표준 모델 마일스톤에 없다")
            continue
        if m["title"] != v["name"].strip() or str(m["due_on"] or "") != (v.get("due_date") or ""):
            problems.append(
                f"버전 {v['name']} 표준 {m['title']} {m['due_on']} 원천 {v.get('due_date')}"
            )
        if (m["state"] == "CLOSED") != (v.get("status") == "closed"):
            problems.append(f"버전 {v['name']} 상태 표준 {m['state']} 원천 {v.get('status')}")

    # 이슈관계 → 일감 사이 추적 링크(양쪽이 이슈로 올라간 관계만)
    pairs = {frozenset((x["a"], x["b"])) for x in links}
    for i in issues:
        for rel in i.get("relations") or []:
            a, b = str(rel["issue_id"]), str(rel["issue_to_id"])
            if a != str(i["id"]) or a not in std_issues or b not in std_issues:
                continue
            if frozenset((a, b)) not in pairs:
                problems.append(f"이슈관계 {a} {rel['relation_type']} {b} 가 추적 링크에 없다")

    assert not problems, problems
