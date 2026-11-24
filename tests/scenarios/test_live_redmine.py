# ruff: noqa: E501
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


# ------------------------------------------------------------------ 11-24 추가

RM_DB = os.environ.get("AXLINK_VERIFY_RM_DB_URL", "")
WBS_PROJECT = os.environ.get("AXLINK_VERIFY_RM_WBS_PROJECT", "axlink-rm-test")


def _rest_enabled(on: bool) -> None:
    """시험용 Redmine 의 「REST 웹 서비스」 설정을 바꾼다. Redmine 은 설정 갱신 시각으로 캐시를 버린다."""
    import psycopg

    with psycopg.connect(RM_DB) as conn:
        conn.execute(
            "update settings set value = %s, updated_on = now() where name = 'rest_api_enabled'",
            ("1" if on else "0",),
        )


def test_UC_010_S02_REST_비활성_실연동(target, live):
    """실제 Redmine 의 REST 웹 서비스를 끄고 연결 확인 → 「REST 웹 서비스 비활성」 안내, 확인 전 상태.
    같은 서버에 틀린 키로 확인하면 인증 실패로 다르게 안내한다. 끝나면 REST 를 다시 켠다 (AC-010-2)."""
    if not RM_DB:
        pytest.skip("AXLINK_VERIFY_RM_DB_URL(시험용 Redmine DB)이 없어 REST 설정을 바꿀 수 없다")
    h = auth(live.tokens[OWNER])
    pid = live.ids["TD-PRJ-1"]
    made = target.post(f"/api/projects/{pid}/connections", json={
        "tool": "REDMINE", "name": "REST 꺼진 실연동", "baseUrl": TARGET_RM_URL,
        "targetResource": WBS_PROJECT, "credential": {"accessToken": KEY},
    }, headers=h)
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    try:
        _rest_enabled(False)
        try:
            res = target.post(f"/api/connections/{cid}/test", headers=h)
        finally:
            _rest_enabled(True)
        assert res.status_code >= 400, res.text
        assert "REST" in res.text, f"REST 비활성을 구분해 안내하지 않는다: {res.text[:300]}"
        listed = target.get(f"/api/projects/{pid}/connections", headers=h).json()
        assert next(c for c in listed if c["id"] == cid)["status"] == "DRAFT"

        wrong = target.post("/api/connections/test", json={
            "tool": "REDMINE", "name": "틀린 키", "baseUrl": TARGET_RM_URL,
            "targetResource": WBS_PROJECT, "credential": {"accessToken": "0" * 40},
        }, headers=h)
        text = wrong.text
        assert "REST" not in text and ("인증" in text or "키" in text or "토큰" in text), text[:300]

        # REST 를 다시 켜면 같은 연결이 확인된다(설정 하나만 바꿨다는 근거)
        ok = target.post(f"/api/connections/{cid}/test", headers=h)
        assert ok.status_code == 200 and ok.json()["reachable"] is True, ok.text
    finally:
        target.delete(f"/api/connections/{cid}", headers=h)


def _xlsx_wbs(rows: list[list]) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Redmine 일감으로 만든 WBS(시험)"])
    ws.append([])
    ws.append(["WBS ID", "작업명", "산출물", "시작일", "종료일", "가중치", "실적"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_UC_030_S12_Redmine_사업_WBS_올리기(target, live):
    """Redmine 만 쓰는 사업(저장소 없음): 상위·하위 일감과 예상 시간이 있는 시험 프로젝트를 붙이면 진척은
    이슈 기반 추정(L3, 일반 일감 진척도 평균)이다. 같은 일감으로 만든 WBS 엑셀(말단 = 예상 시간이 있는
    일감, 가중치 = 예상 시간 비율, 실적 = 진척도)을 일정 화면으로 올리면 L1 이 되고 값이 Redmine 간트의
    예상 시간 가중 진척과 같다 (AC-030-8, AC-041-5)."""
    c1 = auth(live.tokens["TD-ACC-C1"])
    pid = live.ids["TD-PRJ-3"]
    src = live.src.c
    res = src.get("/issues.json", params={"project_id": WBS_PROJECT, "status_id": "*", "limit": 100})
    res.raise_for_status()
    issues = res.json()["issues"]
    assert any(i.get("parent") for i in issues), "시험 프로젝트에 상위·하위 일감이 없다"
    general = [i for i in issues if _name(i["tracker"]) != MAPPING["riskTracker"]]
    want_l3 = sum(i.get("done_ratio") or 0 for i in general) / len(general) / 100
    leaves = sorted((i for i in issues if i.get("estimated_hours")), key=lambda i: i["id"])
    hours = sum(i["estimated_hours"] for i in leaves)
    want_l1 = sum(i["estimated_hours"] * (i.get("done_ratio") or 0) for i in leaves) / hours / 100

    made = target.post(f"/api/projects/{pid}/connections", json={
        "tool": "REDMINE", "name": "Redmine 만 쓰는 사업", "baseUrl": TARGET_RM_URL,
        "targetResource": WBS_PROJECT, "credential": {"accessToken": KEY},
    }, headers=c1)
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    try:
        assert target.post(f"/api/connections/{cid}/test", headers=c1).status_code == 200
        job = target.post(f"/api/connections/{cid}/sync", json={"kind": "BACKFILL"}, headers=c1).json()
        assert job["status"] == "SUCCEEDED", job
        sched = target.get(f"/api/projects/{pid}/wbs", headers=c1).json()
        assert sched["source"] == "REDMINE" and sched["planUpload"] is True, sched["source"]
        prog = target.get(f"/api/projects/{pid}/progress", headers=c1).json()
        assert prog["level"] == "L3", prog["level"]
        assert prog["representative"] == pytest.approx(want_l3, abs=1e-3), (prog["representative"], want_l3)

        rows = []
        total = 0.0
        for n, i in enumerate(leaves, 1):
            w = round(i["estimated_hours"] / hours, 4) if n < len(leaves) else round(1 - total, 4)
            total += w
            rows.append([f"1.{n}", i["subject"], "", i.get("start_date"), i.get("due_date"), w,
                         (i.get("done_ratio") or 0) / 100])
        up = target.post(f"/api/projects/{pid}/wbs/plan",
                         files={"file": ("redmine-WBS.xlsx", _xlsx_wbs(rows), "application/octet-stream")},
                         data={"version": "v1"}, headers=c1)
        assert up.status_code == 201, up.text
        assert up.json()["leafCount"] == len(leaves)
        sched = target.get(f"/api/projects/{pid}/wbs", headers=c1).json()
        assert sched["source"] == "WBS_FILE" and sched["sourceFile"]["path"] == "redmine-WBS.xlsx"
        prog = target.get(f"/api/projects/{pid}/progress", headers=c1).json()
        assert prog["level"] == "L1", prog["level"]
        assert prog["representative"] == pytest.approx(want_l1, abs=2e-3), (prog["representative"], want_l1)
    finally:
        target.delete(f"/api/connections/{cid}", headers=c1)
