"""실연동(GitHub) 시나리오: 실제 GitHub 저장소 두 곳을 원천으로 수집한다 (IM-009 TD-CON-1·3).

재생 서버(tests/fixtures/im009/replay*.py)를 쓰지 않는다. 시험자료는
`tests/fixtures/im009/live_github.py` 가 시험 저장소에 만들어 둔 S0 이고, 대응표는
`tests/fixtures/im009/live/github-map.json` 이다. 사용법은 `tests/fixtures/im009/live/README.md`.

돌리는 조건: AXLINK_LIVE=1, 시험용 DB(*_test), 읽기 전용 토큰 AXLINK_VERIFY_GH_TOKEN.
UC-011-S03 은 원천에 S1 커밋을 push 하므로 이 PC 의 gh CLI 로그인이 더 있어야 한다.

재생 시험과 다른 점
- 생성·닫힌 시각(이슈·PR·마일스톤)은 GitHub 이 정한다. IM-009 의 날짜(예 TD-MS-5 닫힌 날
  2026-06-03) 대신 원천 API 가 준 값과 원시본·표준 모델 값이 같은지 본다. 커밋 시각은 저장소에
  IM-009 값으로 넣었으므로 그 값과 비교한다.
- 건수는 고정 기대값이 아니라 원천 API 의 건수와 비교한다. 실제 저장소는 파일을 커밋으로만 넣을 수
  있어 받침 커밋(초기 구성·PR head)이 있고, S1 을 돌릴 때마다 S1·복원 커밋이 쌓인다.
- 원천 무기록은 수집·확인 요청·조치 보고 전후의 원천 스냅숏(이슈·PR·커밋·마일스톤·라벨·브랜치·
  파일 목록과 갱신 시각)을 비교한다. 프로세스 안 실행이면 어댑터가 GitHub 에 보낸 요청이 모두
  GET 인지도 본다.

모듈 안 시나리오는 파일 순서대로 하나의 상태 위에서 돈다. 하나만 골라 돌려도 되게 앞 단계
(연결·첫 수집)는 필요할 때 만든다.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import settings
from app.db import fetch_all, fetch_one, tx
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import live_github as lg
from tests.fixtures.im009.seed import Seeder
from tests.scenarios.conftest import TARGET_URL, auth

pytestmark = [pytest.mark.db, pytest.mark.live, pytest.mark.live_tool]

TOKEN = lg.read_token()
ADAPTERS = Path(__file__).resolve().parents[2] / "app" / "integration" / "adapter"
OWNER = {"TD-CON-1": "TD-ACC-V1", "TD-CON-3": "TD-ACC-V2"}
GH_KINDS = ("issue", "pull_request", "commit", "milestone", "tree")


class LiveWorld(Seeder):
    """IM-009 1·2절(조직·계정·사업·참여 업체)은 투입 스크립트 그대로, 연결과 수집은 실제 GitHub."""

    def __init__(self, client: Any, gh_map: dict) -> None:
        super().__init__(client)
        self.map = gh_map
        self.src = lg.Source(TOKEN)
        self.calls: list[tuple[str, str]] = []  # 어댑터가 GitHub 에 보낸 (메서드, 경로?질의)
        self.jobs: dict[str, dict] = {}
        self.baseline: dict[str, dict] = {}  # 첫 수집 전 원천 스냅숏

    def base(self) -> None:
        self._orgs_and_clients()
        self._projects()
        self._contractors()
        self.state = "base"

    def repo(self, con: str) -> str:
        return lg.REPOS[con]

    def h(self, acc: str) -> dict[str, str]:
        return auth(self.tokens[acc])

    def create_connection(self, con: str) -> dict:
        body = {
            "tool": "GITHUB",
            "name": con,
            "baseUrl": lg.API,
            "targetResource": self.repo(con),
            "credential": {"accessToken": TOKEN},
            "mappingRules": lg.MAPPING_CON1 if con == "TD-CON-1" else None,
        }
        res = self.c.post(
            f"/api/projects/{self.ids['TD-PRJ-1']}/connections",
            json=body,
            headers=self.h(OWNER[con]),
        )
        assert res.status_code == 201, f"{con} 등록 {res.status_code} {res.text[:200]}"
        self.ids[con] = res.json()["id"]
        return res.json()

    def ensure_connections(self) -> None:
        for con in OWNER:
            if con in self.ids:
                continue
            self.create_connection(con)
            cid = self.ids[con]
            self._ok(self.c.post(f"/api/connections/{cid}/test", headers=self.h(OWNER[con])))
            self._ok(
                self.c.patch(
                    f"/api/connections/{self.ids[con]}/status",
                    json={"status": "ACTIVE"},
                    headers=self.h(OWNER[con]),
                )
            )

    def sync(self, con: str, *, full: bool = False) -> dict:
        res = self.c.post(
            f"/api/connections/{self.ids[con]}/sync",
            json={"kind": "BACKFILL"} if full else None,
            headers=self.h(OWNER[con]),
        )
        assert res.status_code == 202, f"{con} 수집 {res.status_code} {res.text[:300]}"
        return res.json()

    def ensure_synced(self) -> None:
        self.ensure_connections()
        if self.jobs:
            return
        for con in OWNER:
            self.baseline.setdefault(con, self.src.snapshot(self.repo(con)))
        for con in OWNER:
            self.jobs[con] = self.sync(con, full=True)
        # 수집한 계획서로 WBS 행을 만든다(원격 서버는 화면을 열 때 만든다)
        pid = self.ids["TD-PRJ-1"]
        self._ok(self.c.get(f"/api/projects/{pid}/wbs", headers=self.h("TD-ACC-C1")))

    def snapshots(self) -> dict[str, dict]:
        return {con: self.src.snapshot(self.repo(con)) for con in OWNER}

    def raw(self, con: str) -> dict[str, dict]:
        with tx() as cur:
            rows = fetch_all(
                cur,
                "select external_id, object_kind, payload_jsonb, sync_job_id::text as job "
                "from raw_artifact where tool_connection_id = %s",
                (self.ids[con],),
            )
        return {r["external_id"]: r for r in rows}


@pytest.fixture(scope="module")
def gh_map() -> dict:
    if not TOKEN:
        pytest.skip(f"{lg.TOKEN_ENV} 가 없다(읽기 전용 토큰). README 참고")
    m = lg.load_map()
    if m is None:
        pytest.skip("대응표가 없거나 저장소가 다르다. live_github seed 를 먼저 돌린다")
    return m


@pytest.fixture(scope="module")
def live(target, gh_map):
    src = lg.Source(TOKEN)
    try:
        paths = src.tree_paths(lg.REPOS["TD-CON-1"])
    finally:
        src.close()
    if lg.DESIGN_FILE_PATH in paths:
        # 앞 실행이 S1 에서 멈췄다. S0 로 되돌린 뒤 시작한다(gh 쓰기 필요)
        if not lg.gh_available():
            pytest.fail("시험 저장소가 S1 상태다. gh 로그인 뒤 live_github restore 를 먼저 돌린다")
        lg.restore_s0()
    w = LiveWorld(target, gh_map)
    with pytest.MonkeyPatch.context() as mp:
        if not TARGET_URL:
            # 커밋·PR 변경 파일 수집(AC-011-11).
            # 원격 서버는 AXLINK_COLLECT_CHANGE_FILES=true 로 띄운다
            mp.setattr(settings, "collect_change_files", True)
            orig = httpx.Client.send

            def send(client, request, *a, **kw):
                if request.url.host == "api.github.com" and getattr(client, "_axlink_src", 0) == 0:
                    w.calls.append((request.method, request.url.raw_path.decode()))
                return orig(client, request, *a, **kw)

            mp.setattr(httpx.Client, "send", send)
        w.src._c._axlink_src = 1  # 시험의 원천 읽기는 어댑터 호출 기록에서 뺀다
        try:
            w.base()
            yield w
        finally:
            w.src.close()
            w.cleanup()


@pytest.fixture(autouse=True)
def _live_tool_evidence(record_property):
    """실제 GitHub 를 원천으로 돈 실행이다. 검증 기록(record-junit)이 증거 종류로 읽는다."""
    record_property("proves", "live-tool")


def _adapter_writes() -> list[tuple[str, str]]:
    """어댑터 정적 검사: 쓰기 메서드 호출 없음 (CC-01). test_group_f 의 UC-050-S05 와 같은 규칙."""
    offenders = []
    for path in ADAPTERS.glob("*_connector.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\.(post|put|patch|delete)\(", text):
            offenders.append((path.name, m.group(0)))
        if re.search(r"method\s*=\s*['\"](POST|PUT|PATCH|DELETE)", text):
            offenders.append((path.name, "method="))
    return offenders


def _non_get(calls: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [c for c in calls if c[0] != "GET"]


def _diff(before: dict[str, dict], after: dict[str, dict]) -> list[str]:
    out = []
    for con, snap in before.items():
        for key, value in snap.items():
            if after[con][key] != value:
                out.append(f"{con}.{key}")
    return out


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ------------------------------------------------------------------ UC-010


def test_UC_010_S01_GitHub_등록_확인_활성(target, live, screen):
    """TD-CON-1·3 등록 → 확인(저장소 이름·항목 종류) → 활성. 자격증명 응답은 끝 4자만 (AC-010-1·2·6).

    화면 단계(원격 + 브라우저): TD-CON-1 은 V1 이 연동 화면에서 등록·연결 테스트·활성화한다. 화면이
    고를 수 없는 매핑 규칙(IM-009 TD-CON-1 연결 설정)은 등록 뒤 API 로 넣는다. TD-CON-3 은 API 로."""  # noqa: E501
    for con in OWNER:
        sc = screen(OWNER[con]) if screen and con == "TD-CON-1" else None
        made = _ui_register(sc, live, con) if sc else live.create_connection(con)
        leaked = TOKEN in str(made)
        assert not leaked, f"{con} 등록 응답에 토큰 원문이 있다"
        masked = made["credentialMasked"] or ""
        same = masked == "****" + TOKEN[-4:]
        assert same, f"{con} 자격증명 힌트가 끝 4자 형식이 아니다(길이 {len(masked)})"
        assert made["status"] == "DRAFT", made["status"]
        if sc:
            _ui_card_action(sc, con, "연결 테스트", "연결 테스트에 성공했습니다.", "검증")

        res = target.post(f"/api/connections/{live.ids[con]}/test", headers=live.h(OWNER[con]))
        assert res.status_code == 200, res.text[:300]
        probe = res.json()
        assert probe["reachable"] is True
        assert probe["resourceName"].lower() == live.repo(con).lower(), probe["resourceName"]
        assert set(GH_KINDS) <= set(probe["detectedItemTypes"]), probe
        assert probe["deniedItemTypes"] == [], f"읽기 권한이 빠진 항목: {probe['deniedItemTypes']}"

        if sc:
            _ui_card_action(sc, con, "활성화", "상태를 변경했습니다.", "진행")
            rows = target.get(
                f"/api/projects/{live.ids['TD-PRJ-1']}/connections", headers=live.h(OWNER[con])
            ).json()
            status = next(c["status"] for c in rows if c["id"] == live.ids[con])
            assert status == "ACTIVE", status
            sc.done()
            continue
        res = target.patch(
            f"/api/connections/{live.ids[con]}/status",
            json={"status": "ACTIVE"},
            headers=live.h(OWNER[con]),
        )
        assert res.status_code == 200 and res.json()["status"] == "ACTIVE", res.text[:200]
    assert _non_get(live.calls) == [], _non_get(live.calls)


# 연결 테스트 결과의 항목 이름 (connection-form-dialog.tsx ITEM_LABELS)
ITEM_WORDS = {
    "issue": "이슈",
    "pull_request": "풀 리퀘스트(PR)",
    "commit": "커밋",
    "milestone": "마일스톤",
    "tree": "저장소 파일 목록",
}


def _secret_masked(box: Any) -> bool:
    """입력칸이 값을 가리는가(password 형식). 화면 사진은 이것을 확인한 뒤에만 찍는다."""
    return box.get_attribute("type") == "password"


def _ui_register(sc: Any, live: LiveWorld, con: str) -> dict:
    """화면: 연동 등록 창에서 권한 안내를 보고, 값을 넣어 연결 테스트(저장소 이름·읽을 수 있는
    항목), 등록한다. 카드에 상태 「초안」과 인증 끝 4자. 등록된 연결(API 목록의 행)을 돌려준다.

    토큰은 password 입력칸에만 넣는다. 화면 사진은 칸이 가려진 것을 확인한 뒤에만 찍고, 실패 메시지
    에는 토큰이 섞일 수 있는 예외 문구를 싣지 않는다."""
    from playwright.sync_api import expect

    pid = live.ids["TD-PRJ-1"]
    sc.open(f"/p/{pid}/connections").see("연동")
    sc.page.get_by_role("button", name="연동 등록").click()
    dlg = sc.page.get_by_role("dialog")
    expect(dlg).to_contain_text("연동 등록")
    # 권한 안내(AC-010-6): 읽기 전용, 쓰지 않는다
    expect(dlg).to_contain_text("읽기 전용으로 연결합니다")
    expect(dlg).to_contain_text("아무것도 쓰지 않습니다")
    expect(dlg.locator("#connTool")).to_contain_text("GitHub")
    expect(dlg.locator("#connBaseUrl")).to_have_value(lg.API)
    dlg.locator("#connName").fill(con)
    dlg.locator("#connResource").fill(live.repo(con))
    box = dlg.locator("#connToken")
    assert _secret_masked(box), "토큰 입력칸이 password 형식이 아니다"
    try:
        box.fill(TOKEN)
    except Exception:  # noqa: BLE001  예외 문구에 입력값이 실릴 수 있어 버린다
        raise AssertionError("토큰 입력칸에 값을 넣지 못했다") from None
    assert _secret_masked(box), "토큰 입력칸이 값을 넣은 뒤 가려지지 않는다"

    dlg.get_by_role("button", name="연결 테스트").click()
    expect(dlg).to_contain_text("연결 성공", timeout=60000)
    result = dlg.inner_text()
    leaked = TOKEN in result
    assert not leaked, "연결 테스트 결과에 토큰 원문이 있다"
    assert live.repo(con).lower() in result.lower(), "연결 테스트 결과에 저장소 이름이 없다"
    words = [ITEM_WORDS[k] for k in GH_KINDS if ITEM_WORDS[k] not in result]
    assert not words, f"연결 테스트 결과에 없는 항목 종류: {words}"
    assert "권한 없음" not in result, "읽기 권한이 빠진 항목이 있다고 나온다"
    assert _secret_masked(box)
    sc.shot("연결_테스트")  # 토큰 칸은 password 형식이라 점으로 가려진다

    dlg.get_by_role("button", name="등록", exact=True).click()
    expect(dlg).to_be_hidden(timeout=30000)
    sc.see("연결을 등록했습니다.", selector="body")
    rows = live.c.get(f"/api/projects/{pid}/connections", headers=live.h(OWNER[con])).json()
    made = next(c for c in rows if c["name"] == con)
    live.ids[con] = made["id"]
    card = _ui_connection_card(sc, con)
    expect(card).to_contain_text("초안")
    expect(card).to_contain_text(f"인증 {made['credentialMasked']}")
    expect(card).to_contain_text(live.repo(con))
    leaked = TOKEN in sc.text("body")
    assert not leaked, "연동 화면에 토큰 원문이 보인다"
    if con == "TD-CON-1":
        # 연결 설정(UC-012)의 매핑 규칙. 화면 등록 창에는 이 칸이 없다
        live._ok(
            live.c.patch(
                f"/api/connections/{made['id']}/mapping",
                json={"mappingRules": lg.MAPPING_CON1},
                headers=live.h(OWNER[con]),
            )
        )
    return made


def _ui_connection_card(sc: Any, con: str) -> Any:
    title = sc.page.locator("[data-slot=card-title]", has_text=con)
    return sc.page.locator("[data-slot=card]").filter(has=title).first


def _ui_card_action(sc: Any, con: str, button: str, toast: str, status: str) -> None:
    """연결 카드의 단추(연결 테스트·활성화)를 누르고 알림과 상태 딱지를 본다."""
    from playwright.sync_api import expect

    card = _ui_connection_card(sc, con)
    card.get_by_role("button", name=button, exact=True).click()
    sc.see(toast, selector="body", timeout=60000)
    expect(card.locator("[data-slot=card-title]")).to_contain_text(status, timeout=15000)
    sc.shot(button.replace(" ", "_"))


def test_UC_010_S03_자격증명_비노출(target, live):
    """연결 조회·목록(소유 업체·발주기관·다른 업체)에 원문 없음, DB 는 암호문 (AC-010-1)."""
    live.ensure_connections()
    pid = live.ids["TD-PRJ-1"]
    for acc in ("TD-ACC-V1", "TD-ACC-V2", "TD-ACC-C1"):
        res = target.get(f"/api/projects/{pid}/connections", headers=live.h(acc))
        assert res.status_code == 200, res.text[:200]
        leaked = TOKEN in res.text
        assert not leaked, f"{acc} 의 연결 목록에 토큰 원문이 있다"
        for c in res.json():
            assert c["credentialMasked"] is None or len(c["credentialMasked"]) <= 8
    with tx() as cur:
        rows = fetch_all(
            cur, "select auth_encrypted from tool_connection where project_id = %s", (pid,)
        )
    stored_plain = any(TOKEN in (r["auth_encrypted"] or "") for r in rows)
    assert rows and not stored_plain, "DB 에 토큰 원문이 있다"


# ------------------------------------------------------------------ UC-011 첫 수집


def test_UC_011_S01_GitHub_첫_수집(target, live):
    """두 연결 전체 수집 → 이력 성공, 원천 건수 = 수집 신규 건수 = 표준 모델 건수 (AC-011-2·3)."""
    live.ensure_connections()
    live.ensure_synced()
    problems: list[str] = []
    for con in OWNER:
        job = live.jobs[con]
        assert job["status"] == "SUCCEEDED", job
        assert job["kind"] == "BACKFILL", job["kind"]
        snap = live.baseline[con]
        raw = live.raw(con)
        by_kind: dict[str, int] = {}
        for r in raw.values():
            by_kind[r["object_kind"]] = by_kind.get(r["object_kind"], 0) + 1
        want = {
            "issue": len(snap["issues"]),
            "pull_request": len(snap["pulls"]),
            "commit": len(snap["commits"]),
            "milestone": len(snap["milestones"]),
            "tree": 1,
        }
        if con == "TD-CON-1":
            want |= {"file": 1, "design_doc": 1}
        got = {k: by_kind.get(k, 0) for k in want}
        if got != want or set(by_kind) - set(want):
            problems.append(f"{con} 원시본 {by_kind} (원천 {want})")
        stats = job["stats"]
        fetched = sum(v for k, v in want.items() if k != "design_doc")
        if stats["changed"] != fetched or stats["fetched"] != fetched:
            problems.append(
                f"{con} 신규 {stats['changed']}·받음 {stats['fetched']} (원천 {fetched})"
            )
        with tx() as cur:
            std = fetch_one(
                cur,
                """
                select (select count(*) from issue where tool_connection_id = %(c)s) as issue,
                       (select count(*) from code_change where tool_connection_id = %(c)s
                           and kind = 'COMMIT') as commit,
                       (select count(*) from code_change where tool_connection_id = %(c)s
                           and kind = 'MERGE_REQUEST') as pull_request,
                       (select count(*) from milestone
                         where tool_connection_id = %(c)s) as milestone
                """,
                {"c": live.ids[con]},
            )
        std_want = {k: want[k] for k in ("issue", "commit", "pull_request", "milestone")}
        if dict(std) != std_want:
            problems.append(f"{con} 표준 모델 {dict(std)} (원천 {std_want})")
    # 수집 이력: 두 연결 모두 「성공」
    jobs = target.get(
        f"/api/sync-jobs?projectId={live.ids['TD-PRJ-1']}&size=50", headers=live.h("TD-ACC-C1")
    ).json()["content"]
    for con in OWNER:
        mine = [j for j in jobs if j["connectionId"] == live.ids[con]]
        if not mine or mine[0]["status"] != "SUCCEEDED":
            problems.append(f"{con} 이력 {[(j['kind'], j['status']) for j in mine]}")
    # S0 계획서가 수집돼 진척률 30.0% (IM-009 7.1)
    prog = target.get(
        f"/api/projects/{live.ids['TD-PRJ-1']}/progress", headers=live.h("TD-ACC-C1")
    ).json()
    if prog.get("representative") is None or round(prog["representative"], 4) != 0.3:
        problems.append(f"진척률 {prog.get('representative')} (기대 0.3) level={prog.get('level')}")
    assert not problems, problems
    assert _non_get(live.calls) == [], _non_get(live.calls)


def test_UC_011_S11_GitHub_종류별_필드(target, live):
    """TD-CMT-1 메시지·변경 파일, TD-PR-1 본문·병합·연결 이슈 G4, G1 라벨·마일스톤 M-a,
    TD-MS-5 기한·닫힌 날이 원시본·표준 모델에 원천과 같게 있다 (AC-011-11)."""
    live.ensure_synced()
    con, cid = "TD-CON-1", live.ids["TD-CON-1"]
    repo = live.repo(con)
    m = live.map[con]
    raw = live.raw(con)
    problems: list[str] = []

    # 커밋 TD-CMT-1
    sha1 = m["commits"]["TD-CMT-1"]
    src_c = live.src.get(f"/repos/{repo}/commits/{sha1}")
    raw_c = raw[f"commit:{sha1}"]["payload_jsonb"]
    cmt1 = next(c for c in d.COMMITS if c.tid == "TD-CMT-1")
    if raw_c["commit"]["message"] != src_c["commit"]["message"] or not src_c["commit"][
        "message"
    ].startswith(cmt1.message):
        problems.append(f"TD-CMT-1 메시지 원시본 {raw_c['commit']['message']!r}")
    src_files = [f["filename"] for f in src_c["files"]]
    raw_files = raw_c.get("files")
    raw_names = [f if isinstance(f, str) else f.get("filename") for f in raw_files or []]
    if src_files != list(cmt1.files) or raw_names != src_files:
        problems.append(f"TD-CMT-1 변경 파일 원천 {src_files} 원시본 {raw_files}")
    with tx() as cur:
        std_c = fetch_one(
            cur,
            "select * from code_change where tool_connection_id = %s and ref_name = %s",
            (cid, sha1),
        )
    if std_c is None or std_c["title"] != cmt1.message:
        problems.append(f"TD-CMT-1 표준 모델 {std_c and std_c['title']}")
    elif _dt(std_c["occurred_at"]) != _dt(cmt1.authored) or std_c["external_url"] != src_c[
        "html_url"
    ]:
        problems.append(f"TD-CMT-1 시각·주소 {std_c['occurred_at']} {std_c['external_url']}")

    # PR TD-PR-1 (#6): 본문·병합·연결 이슈 G4
    pr_no = m["pulls"]["TD-PR-1"]
    src_p = live.src.get(f"/repos/{repo}/pulls/{pr_no}")
    raw_p = raw[f"pull_request:{pr_no}"]["payload_jsonb"]
    if raw_p["body"] != src_p["body"] or src_p["body"] != "Closes #4":
        problems.append(f"TD-PR-1 본문 원천 {src_p['body']!r} 원시본 {raw_p['body']!r}")
    if not src_p["merged_at"] or raw_p.get("merged_at") != src_p["merged_at"]:
        problems.append(f"TD-PR-1 병합 원천 {src_p['merged_at']} 원시본 {raw_p.get('merged_at')}")
    with tx() as cur:
        std_p = fetch_one(
            cur,
            "select * from code_change where tool_connection_id = %s and external_id = %s",
            (cid, f"pull_request:{pr_no}"),
        )
        link = fetch_one(
            cur,
            """
            select i.external_id, i.tool_connection_id::text as con
              from trace_link l
              join code_change c on c.id = l.from_id
              join issue i on i.id = l.to_id
             where l.project_id = %s and c.id = %s and l.to_type = 'ISSUE'
            """,
            (live.ids["TD-PRJ-1"], std_p["id"] if std_p else None),
        )
    if std_p is None or std_p["state"] != "MERGED":
        problems.append(f"TD-PR-1 표준 모델 상태 {std_p and std_p['state']}")
    if link is None or (link["external_id"], link["con"]) != (
        f"issue:{m['issues']['TD-ISS-G4']}",
        cid,
    ):
        problems.append(f"TD-PR-1 → G4 연결 {link}")

    # 이슈 G1 (#1): 라벨·마일스톤
    g1 = m["issues"]["TD-ISS-G1"]
    src_i = live.src.get(f"/repos/{repo}/issues/{g1}")
    raw_i = raw[f"issue:{g1}"]["payload_jsonb"]
    src_labels = [lb["name"] for lb in src_i["labels"]]
    if src_labels != [lg.REQ_LABEL] or [lb["name"] for lb in raw_i["labels"]] != src_labels:
        problems.append(f"G1 라벨 원천 {src_labels} 원시본 {raw_i['labels']}")
    if (src_i["milestone"] or {}).get("title") != "M-a" or (raw_i.get("milestone") or {}).get(
        "title"
    ) != "M-a":
        problems.append(f"G1 마일스톤 원천 {src_i['milestone']} 원시본 {raw_i.get('milestone')}")
    with tx() as cur:
        std_i = fetch_one(
            cur,
            """
            select i.*, m.title as milestone_title
              from issue i left join milestone m on m.id = i.milestone_id
             where i.tool_connection_id = %s and i.external_id = %s
            """,
            (cid, f"issue:{g1}"),
        )
    if std_i is None:
        problems.append("G1 이 표준 모델 이슈에 없다")
    else:
        if std_i["milestone_title"] != "M-a" or std_i["status"] != "CLOSED":
            problems.append(
                f"G1 표준 모델 마일스톤 {std_i['milestone_title']} 상태 {std_i['status']}"
            )
        if _dt(std_i["resolved_at"]) != _dt(src_i["closed_at"]):
            problems.append(f"G1 닫힌 시각 {std_i['resolved_at']} (원천 {src_i['closed_at']})")

    # 마일스톤 TD-MS-5 (M-a #1): 기한·닫힌 날
    ms_no = m["milestones"]["TD-MS-5"]
    src_m = live.src.get(f"/repos/{repo}/milestones/{ms_no}")
    raw_m = raw[f"milestone:{ms_no}"]["payload_jsonb"]
    if raw_m["due_on"] != src_m["due_on"] or raw_m["closed_at"] != src_m["closed_at"]:
        problems.append(f"TD-MS-5 원시본 {raw_m['due_on']} {raw_m['closed_at']}")
    with tx() as cur:
        std_m = fetch_one(
            cur,
            "select * from milestone where tool_connection_id = %s and number = %s",
            (cid, ms_no),
        )
    ms5 = next(x for x in d.MILESTONES if x.tid == "TD-MS-5")
    if std_m is None:
        problems.append("TD-MS-5 가 표준 모델에 없다")
    else:
        due = ms5.due.isoformat()
        if str(std_m["due_on"]) != due or src_m["due_on"][:10] != due:
            problems.append(f"TD-MS-5 기한 {std_m['due_on']} 원천 {src_m['due_on']}")
        if std_m["state"] != "CLOSED" or _dt(std_m["closed_at"]) != _dt(src_m["closed_at"]):
            problems.append(
                f"TD-MS-5 닫힘 {std_m['state']} {std_m['closed_at']} 원천 {src_m['closed_at']}"
            )
    assert not problems, problems


def test_UC_022_S04_같은_번호_다른_연결(target, live):
    """TD-CMT-4(GH-4, TD-CON-1) → G4, TD-CMT-W1(GH-4, TD-CON-3) → W4. 서로 바뀌지 않음 (AC-022-5)."""  # noqa: E501
    live.ensure_synced()
    with tx() as cur:
        rows = fetch_all(
            cur,
            """
            select c.ref_name, c.tool_connection_id::text as from_con,
                   i.external_id as to_ext, i.tool_connection_id::text as to_con
              from trace_link l
              join code_change c on c.id = l.from_id
              join issue i on i.id = l.to_id
             where l.project_id = %s and l.to_type = 'ISSUE' and c.kind = 'COMMIT'
            """,
            (live.ids["TD-PRJ-1"],),
        )
    con1, con3 = live.ids["TD-CON-1"], live.ids["TD-CON-3"]
    pairs = {(r["ref_name"], r["from_con"], r["to_ext"], r["to_con"]) for r in rows}
    cmt4 = live.map["TD-CON-1"]["commits"]["TD-CMT-4"]
    w1 = live.map["TD-CON-3"]["commits"]["TD-CMT-W1"]
    g4 = f"issue:{live.map['TD-CON-1']['issues']['TD-ISS-G4']}"
    w4 = f"issue:{live.map['TD-CON-3']['issues']['TD-ISS-W4']}"
    assert (cmt4, con1, g4, con1) in pairs, pairs
    assert (w1, con3, w4, con3) in pairs, pairs
    assert (cmt4, con1, w4, con3) not in pairs and (w1, con3, g4, con1) not in pairs, pairs


# ------------------------------------------------------------------ UC-011 증분 · 원천 무기록


def test_UC_011_S02_변경_없는_증분(target, live):
    """원천이 그대로일 때 지금 수집 → 증분(마지막 시각 이후), 신규·갱신 0 (AC-011-1·2)."""
    live.ensure_synced()
    before = len(live.calls)
    for con in OWNER:
        job = live.sync(con)
        assert job["status"] == "SUCCEEDED", job
        assert job["kind"] == "POLL", job["kind"]
        assert job["stats"]["changed"] == 0, f"{con} 변경 없는데 신규·갱신 {job['stats']}"
        assert job["stats"]["skippedUnchanged"] == job["stats"]["fetched"], job["stats"]
    if not TARGET_URL:
        mine = live.calls[before:]
        issue_calls = [p for _, p in mine if re.search(r"/issues\?", p)]
        commit_calls = [p for _, p in mine if re.search(r"/commits\?", p)]
        assert issue_calls and all("since=" in p for p in issue_calls), issue_calls
        assert commit_calls and all("since=" in p for p in commit_calls), commit_calls
        assert _non_get(mine) == [], _non_get(mine)


def test_UC_010_S06_읽기_전용_어댑터(target, live):
    """정적 검사 + 수집(전체·증분) 전후 원천 비교: 쓰기 호출 없음, 원천 변화 없음 (AC-010-3, CC-01)."""  # noqa: E501
    live.ensure_synced()
    live.sync("TD-CON-1")  # 이 시험만 골라 돌려도 증분 한 번은 거친다
    assert _adapter_writes() == [], _adapter_writes()
    changed = _diff(live.baseline, live.snapshots())
    assert changed == [], f"수집 뒤 원천이 바뀌었다: {changed}"
    if not TARGET_URL:
        assert live.calls, "어댑터 호출이 기록되지 않았다"
        assert _non_get(live.calls) == [], _non_get(live.calls)


def test_UC_050_S05_원천_무기록(target, live):
    """확인 요청(3.2) 등록 전후 GitHub 원천 비교, 어댑터 정적 검사 → 변화 없음 (AC-050-4, CC-01)."""
    live.ensure_synced()
    before = live.snapshots()
    calls = len(live.calls)
    rr = d.REVIEW_REQUEST_TD_RR_1
    res = target.post(
        f"/api/projects/{live.ids['TD-PRJ-1']}/review-requests",
        json={
            "targetType": rr["target"][0],
            "targetKey": rr["target"][1],
            "title": rr["title"],
            "body": "",
            "purpose": "GENERAL",
        },
        headers=live.h("TD-ACC-C1"),
    )
    assert res.status_code == 201, res.text[:300]
    live.ids["TD-RR-1"] = res.json()["id"]
    assert _adapter_writes() == [], _adapter_writes()
    changed = _diff(before, live.snapshots())
    assert changed == [], f"확인 요청 뒤 원천이 바뀌었다: {changed}"
    assert _non_get(live.calls[calls:]) == [], _non_get(live.calls[calls:])


def test_UC_051_S05_원천_무기록(target, live):
    """조치 보고 전후 GitHub 원천 비교 → 변화 없음 (AC-051-5)."""
    if "TD-RR-1" not in live.ids:
        test_UC_050_S05_원천_무기록(target, live)
    before = live.snapshots()
    calls = len(live.calls)
    res = target.post(
        f"/api/review-requests/{live.ids['TD-RR-1']}/report",
        json={"body": d.REVIEW_REQUEST_TD_RR_1["report"], "evidence": []},
        headers=live.h("TD-ACC-V1"),
    )
    assert res.status_code == 200, res.text[:300]
    changed = _diff(before, live.snapshots())
    assert changed == [], f"조치 보고 뒤 원천이 바뀌었다: {changed}"
    assert _non_get(live.calls[calls:]) == [], _non_get(live.calls[calls:])


# ------------------------------------------------------------------ UC-011 S1 증분 (원천을 바꾼다)


def test_UC_011_S03_조치_뒤_증분(target, live):
    """S1 커밋(TD-CMT-2 설계서 파일, WBS 3.2 85%)을 push → 지금 수집 → 신규 커밋 2·파일 갱신,
    WBS 현행 교체, 진척 39.0% (AC-011-1·2, IM-009 7.1). 끝에 원천을 S0 내용으로 되돌린다."""
    if not lg.gh_available():
        pytest.skip("S1 push 에 gh CLI 로그인이 필요하다")
    live.ensure_synced()
    con, repo = "TD-CON-1", live.repo("TD-CON-1")
    before = live.raw(con)
    s1 = lg.to_s1()
    try:
        job = live.sync(con)
        assert job["status"] == "SUCCEEDED", job
        assert job["kind"] == "POLL", job["kind"]
        after = live.raw(con)
        problems: list[str] = []
        new_ids = set(after) - set(before)
        want_new = {f"commit:{s1['TD-CMT-2']}", f"commit:{s1['TD-WBS-S1']}"}
        if new_ids != want_new:
            problems.append(f"신규 원시본 {sorted(new_ids)} (기대 {sorted(want_new)})")
        touched = {k for k, r in after.items() if r["job"] == job["id"]}
        if not {f"file:{lg.WBS_PATH}", "tree:HEAD"} <= touched:
            problems.append(f"이번 회차에 갱신된 원시본 {sorted(touched)}")
        if job["stats"]["changed"] != 4:
            problems.append(f"신규·갱신 {job['stats']['changed']} (기대 4: 커밋 2·파일 1·목록 1)")
        if len([r for r in after.values() if r["object_kind"] == "commit"]) != len(
            live.src.commits(repo)
        ):
            problems.append("수집한 커밋 수가 원천과 다르다")
        src_file = live.src.get(f"/repos/{repo}/contents/{lg.WBS_PATH}")
        raw_file = after[f"file:{lg.WBS_PATH}"]["payload_jsonb"]
        if raw_file["sha"] != src_file["sha"] or src_file["sha"] != s1["wbs_blob"]:
            problems.append(f"WBS 파일 원시본 sha {raw_file['sha']} 원천 {src_file['sha']}")
        tree = after["tree:HEAD"]["payload_jsonb"]
        if lg.DESIGN_FILE_PATH not in tree["paths"] or tree["commit"] != s1["head"]:
            problems.append(f"파일 목록에 설계서가 없거나 HEAD 가 다르다({tree['commit']})")
        raw_c2 = after.get(f"commit:{s1['TD-CMT-2']}", {}).get("payload_jsonb") or {}
        names = [f if isinstance(f, str) else f.get("filename") for f in raw_c2.get("files") or []]
        if not TARGET_URL and names != [lg.DESIGN_FILE_PATH]:
            problems.append(f"TD-CMT-2 변경 파일 {names}")
        with tx() as cur:
            wp = fetch_one(
                cur,
                """
                select version from work_product
                 where project_id = %s and type = 'PROJECT_PLAN' and source_revision = %s
                """,
                (live.ids["TD-PRJ-1"], s1["wbs_blob"]),
            )
        if wp is None:
            problems.append("S1 계획서가 산출물(사업수행계획서)로 올라가지 않았다")
        h = live.h("TD-ACC-C1")
        pid = live.ids["TD-PRJ-1"]
        wbs = target.get(f"/api/projects/{pid}/wbs", headers=h).json()
        w32 = next((i for i in wbs["items"] if i["wbsId"] == "3.2"), None)
        if w32 is None or w32["progress"] != 85:
            problems.append(f"WBS 3.2 실적 {w32 and w32['progress']} (기대 85)")
        prog = target.get(f"/api/projects/{pid}/progress", headers=h).json()
        if prog.get("representative") is None or round(prog["representative"], 4) != 0.39:
            problems.append(f"진척률 {prog.get('representative')} (기대 0.39)")
        assert not problems, problems
        assert _non_get(live.calls) == [], _non_get(live.calls)
    finally:
        lg.restore_s0()
