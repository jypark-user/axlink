"""IM-009 공통 시험 자료 투입 (상태 S0 → S0r · S0a · S1 · S1r).

전용 시험 DB(이름이 `_test` 로 끝남)에만 쓴다. 제품의 API(FastAPI TestClient)와 수집·승격 코드를
그대로 불러 자료를 넣는다. 도구 원천은 재생 자료(payloads.py)다. 실연동으로 S0 를 만들 때는
raw 적재 단계만 실제 수집으로 바꾼다.

사용 (pytest 안):
    from tests.fixtures.im009.seed import Seeder
    s = Seeder(client); s.s0(); s.s0r(); s.s0a(); s.s1(); s.s1r()

사람 계정의 비밀번호는 환경 변수 IM009_PASSWORD 로 준다(문서에 적지 않는다). 없으면 시험용
기본값을 쓰고 그 사실을 결과에 남긴다.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.ai.embedding import embedding_port
from app.common import crypto
from app.dashboard import snapshot as snapshot_service
from app.db import tx
from app.integration import repository as integ_repo
from app.standard import service as standard
from app.standard import trace_service
from tests.conftest import seed_issue_requirements
from tests.fixtures.im009 import data as d
from tests.fixtures.im009 import files, payloads

PASSWORD = os.environ.get("IM009_PASSWORD", "im009-Test-Pass!")
ADMIN_USER = os.environ.get("IM009_ADMIN_USER", "r1")
ADMIN_PASS = os.environ.get("IM009_ADMIN_PASS", "admin")
FILES_DIR = Path(os.environ.get("IM009_FILES_DIR", "var/verify/im009-files"))

DESIGN_DOC_PATH = "docs/20-design/설계-민원조회.md"
WBS_PATH = "docs/00-management/WBS.xlsx"
DESIGN_FILE_PATH = "docs/20-design/SW설계서_v0.9.docx"
HEAD_S0 = "9a8b7c6d5e4f30219a8b7c6d5e4f30219a8b7c6d"
HEAD_S1 = "1b2c3d4e5f6a70811b2c3d4e5f6a70811b2c3d4e"


class SeedError(RuntimeError):
    pass


class Seeder:
    """한 번 만들어 상태를 순서대로 올린다. 만든 ID 는 `ids` 에 남는다."""

    def __init__(self, client: Any, files_dir: Path = FILES_DIR) -> None:
        self.c = client
        self.files_dir = files_dir
        self.ids: dict[str, str] = {}  # TD-… → 실제 id
        self.tokens: dict[str, str] = {}  # TD-ACC-… → access token
        self.notes: list[str] = []  # 자료 없음·대체 기록
        self.state = "none"
        self.files = files.make_all(files_dir)
        for tid, why in files.MISSING.items():
            self.notes.append(f"{tid} 자료 없음: {why}")

    # ------------------------------------------------------------ HTTP 도우미

    def _h(self, acc: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[acc]}"}

    def _ok(self, res: Any, *codes: int) -> Any:
        if res.status_code not in (codes or (200, 201, 204)):
            raise SeedError(
                f"{res.request.method} {res.request.url} → {res.status_code} {res.text[:300]}"
            )
        return res.json() if res.status_code != 204 and res.content else None

    def login(self, username: str, password: str) -> str:
        body = self._ok(
            self.c.post("/api/auth/login", json={"username": username, "password": password})
        )
        return body["accessToken"]

    # ------------------------------------------------------------ 1·2 조직·계정·사업

    def _orgs_and_clients(self) -> None:
        self.tokens["TD-ACC-A1"] = self.login(ADMIN_USER, ADMIN_PASS)
        self.notes.append(
            f"TD-ACC-A1 운영자는 기존 관리자 계정 {ADMIN_USER} 으로 대신한다(관리자 생성 API 없음)"
        )
        adm = self._h("TD-ACC-A1")
        for tid in ("TD-ORG-C1", "TD-ORG-C2"):
            org = self._ok(
                self.c.post(
                    "/api/admin/organizations", json={"name": d.ORGS[tid].name}, headers=adm
                )
            )
            self.ids[tid] = org["id"]
        for tid in ("TD-ACC-C1", "TD-ACC-C2"):
            acc = d.ACCOUNTS[tid]
            user = self._ok(
                self.c.post(
                    "/api/admin/users",
                    json={
                        "organizationId": self.ids[acc.org],
                        "username": acc.username,
                        "name": acc.display,
                    },
                    headers=adm,
                )
            )
            self.ids[tid] = user["id"]
            temp = self.login(acc.username, user["temporaryPassword"])
            self._ok(
                self.c.post(
                    "/api/auth/password",
                    json={
                        "currentPassword": user["temporaryPassword"],
                        "newPassword": PASSWORD,
                    },
                    headers={"Authorization": f"Bearer {temp}"},
                )
            )
            self.tokens[tid] = self.login(acc.username, PASSWORD)

    def _projects(self) -> None:
        owner = {
            "TD-PRJ-1": "TD-ACC-C1",
            "TD-PRJ-3": "TD-ACC-C1",
            "TD-PRJ-9": "TD-ACC-C1",
            "TD-PRJ-2": "TD-ACC-C2",
        }
        for tid, p in d.PROJECTS.items():
            body = self._ok(
                self.c.post(
                    "/api/projects",
                    json={
                        "name": p.name,
                        "startDate": p.start.isoformat(),
                        "endDate": p.end.isoformat(),
                        "description": f"IM-009 {tid}",
                        "contractorName": "",
                        "deletePassword": "im009-delete",
                    },
                    headers=self._h(owner[tid]),
                )
            )
            self.ids[tid] = body["id"]
            self.ids[f"{tid}:owner"] = owner[tid]

    def _participant(self, prj: str, org_tid: str, role: str) -> None:
        h = self._h(self.ids[f"{prj}:owner"])
        body: dict[str, Any] = {"role": role}
        if org_tid in self.ids:
            body["organizationId"] = self.ids[org_tid]
        else:
            body["organizationName"] = d.ORGS[org_tid].name
        row = self._ok(
            self.c.post(f"/api/projects/{self.ids[prj]}/participants", json=body, headers=h)
        )
        self.ids[org_tid] = row["organizationId"]

    def _invite_and_join(self, prj: str, org_tid: str, acc_tid: str) -> None:
        h = self._h(self.ids[f"{prj}:owner"])
        inv = self._ok(
            self.c.post(
                f"/api/projects/{self.ids[prj]}/invites",
                json={"organizationId": self.ids[org_tid]},
                headers=h,
            )
        )
        acc = d.ACCOUNTS[acc_tid]
        login = self._ok(
            self.c.post(
                "/api/auth/invitations/accept",
                json={
                    "token": inv["token"],
                    "username": acc.username,
                    "name": acc.display,
                    "password": PASSWORD,
                },
            )
        )
        self.tokens[acc_tid] = login["accessToken"]
        me = self._ok(self.c.get("/api/auth/me", headers=self._h(acc_tid)))
        self.ids[acc_tid] = me["id"] if "id" in me else me.get("userId", "")

    def _contractors(self) -> None:
        self._participant("TD-PRJ-1", "TD-ORG-V1", "REPRESENTATIVE")
        self._participant("TD-PRJ-1", "TD-ORG-V2", "PARTICIPANT")
        self._participant("TD-PRJ-2", "TD-ORG-V3", "REPRESENTATIVE")
        self._participant("TD-PRJ-9", "TD-ORG-V1", "REPRESENTATIVE")
        self._invite_and_join("TD-PRJ-1", "TD-ORG-V1", "TD-ACC-V1")
        self._invite_and_join("TD-PRJ-1", "TD-ORG-V2", "TD-ACC-V2")
        self._invite_and_join("TD-PRJ-2", "TD-ORG-V3", "TD-ACC-V3")
        # V1 을 TD-PRJ-9 에도 배정
        self._ok(
            self.c.post(
                f"/api/projects/{self.ids['TD-PRJ-9']}/assignments",
                json={
                    "contractorOrgId": self.ids["TD-ORG-V1"],
                    "userIds": [self.ids["TD-ACC-V1"]],
                },
                headers=self._h("TD-ACC-C1"),
            )
        )
        # V0 한신입: 초대로 가입시킨 뒤 배정을 지워 「배정 없음」을 만든다
        self._invite_and_join("TD-PRJ-9", "TD-ORG-V1", "TD-ACC-V0")
        rows = self._ok(
            self.c.get(
                f"/api/projects/{self.ids['TD-PRJ-9']}/assignments", headers=self._h("TD-ACC-C1")
            )
        )
        for a in rows:
            if a.get("userId") == self.ids["TD-ACC-V0"]:
                self._ok(
                    self.c.delete(
                        f"/api/projects/{self.ids['TD-PRJ-9']}/assignments/{a['id']}",
                        headers=self._h("TD-ACC-C1"),
                    )
                )

    # ------------------------------------------------------------ 3 연결 · 5 원천 재생

    def _connections(self, cur: Any) -> None:
        now = datetime.now(UTC)
        for tid, con in d.CONNECTIONS.items():
            mapping = {k: v for k, v in con.mapping.items() if k in ("riskTracker", "reqIdField")}
            if "designDocPaths" in con.mapping:
                mapping["designDocPaths"] = ",".join(con.mapping["designDocPaths"])
            row = integ_repo.insert(
                cur,
                self.ids[con.project],
                self.ids[con.owner],
                con.tool,
                tid,
                con.base_url,
                con.target,
                crypto.encrypt("replay-token"),
                "r***",
                mapping or None,
            )
            self.ids[tid] = str(row["id"])
            integ_repo.update_status(cur, self.ids[tid], "ACTIVE", now)
        self.notes.append(
            "TD-CON-1 산출물 파일 경로 설정은 서버 전역(AXLINK_COLLECT_FILES 기본값)에 기댄다"
        )

    def _load(self, cur: Any, con_tid: str, items: list[tuple[str, str, dict]]) -> None:
        cid = self.ids[con_tid]
        job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
        for external_id, kind, payload in items:
            integ_repo.upsert_raw_artifact(cur, cid, external_id, kind, payload, job)
        now = datetime.now(UTC)
        integ_repo.finish_sync_job(cur, job, "SUCCEEDED", {}, now, now)

    def _raw_items(self, state: str) -> dict[str, list[tuple[str, str, dict]]]:
        by_tid = {i.tid: i for i in d.REDMINE_ISSUES_PRJ1}
        ver_num = {m.name: m.number for m in d.MILESTONES if m.connection == "TD-CON-2"}
        con2 = [
            ("issue",)
            + payloads.redmine_issue(i, state, d.CONNECTIONS["TD-CON-2"].base_url, by_tid, ver_num)
            for i in d.REDMINE_ISSUES_PRJ1
        ]
        con2 += [
            ("version",) + payloads.redmine_version(m, d.CONNECTIONS["TD-CON-2"].base_url)
            for m in d.MILESTONES
            if m.connection == "TD-CON-2"
        ]
        con2 += [("tracker", eid, p) for eid, p in payloads.redmine_trackers()]

        repo1 = d.CONNECTIONS["TD-CON-1"].target
        ms1 = {m.name: m for m in d.MILESTONES if m.connection == "TD-CON-1"}
        con1 = [("issue",) + payloads.github_issue(i, repo1, ms1) for i in d.GITHUB_ISSUES_CON1]
        con1 += [("milestone",) + payloads.github_milestone(m, repo1) for m in ms1.values()]
        con1 += [
            ("commit",) + payloads.github_commit(c, repo1)
            for c in d.COMMITS
            if c.connection == "TD-CON-1" and (state == "S1" or c.state == "S0")
        ]
        con1 += [
            ("pull_request",) + payloads.github_pull_request(p, repo1) for p in d.PULL_REQUESTS_CON1
        ]
        wbs_file = self.files["TD-DOC-6-S1" if state == "S1" else "TD-DOC-6"].read_bytes()
        wbs_sha = d.WBS_FILE_COMMIT_S1 if state == "S1" else d.WBS_FILE_COMMIT_S0
        con1.append(("file",) + payloads.github_file(WBS_PATH, wbs_file, wbs_sha, repo1))
        head = HEAD_S1 if state == "S1" else HEAD_S0
        paths = [WBS_PATH, DESIGN_DOC_PATH, "src/auth/login.py"]
        if state == "S1":
            paths.append(DESIGN_FILE_PATH)
        con1.append(("tree",) + payloads.github_tree(paths, head, repo1))
        con1.append(
            ("design_doc",)
            + payloads.github_design_doc(
                DESIGN_DOC_PATH, self.files["TD-DOC-R1"].read_text(encoding="utf-8"), head, repo1
            )
        )

        repo3 = d.CONNECTIONS["TD-CON-3"].target
        con3 = [("issue",) + payloads.github_issue(i, repo3, {}) for i in d.GITHUB_ISSUES_CON3]
        con3 += [
            ("commit",) + payloads.github_commit(c, repo3)
            for c in d.COMMITS
            if c.connection == "TD-CON-3"
        ]

        by_tid2 = {i.tid: i for i in d.REDMINE_ISSUES_PRJ2}
        ver2 = {m.name: m.number for m in d.MILESTONES_PRJ2}
        con4 = [
            ("issue",)
            + payloads.redmine_issue(i, state, d.CONNECTIONS["TD-CON-4"].base_url, by_tid2, ver2)
            for i in d.REDMINE_ISSUES_PRJ2
        ]
        con4 += [
            ("version",) + payloads.redmine_version(m, d.CONNECTIONS["TD-CON-4"].base_url)
            for m in d.MILESTONES_PRJ2
        ]
        return {"TD-CON-1": con1, "TD-CON-2": con2, "TD-CON-3": con3, "TD-CON-4": con4}

    def _promote_all(self, cur: Any) -> None:
        for tid in ("TD-CON-1", "TD-CON-2", "TD-CON-3", "TD-CON-4"):
            cur.execute("select * from tool_connection where id = %s", (self.ids[tid],))
            standard.promote_connection(cur, cur.fetchone(), embedding_port())
        for prj in ("TD-PRJ-1", "TD-PRJ-2"):
            trace_service.build_project_links(cur, self.ids[prj])

    def _legacy_requirements(self, cur: Any, items: list[tuple[str, str, dict]]) -> None:
        """4.1 기존 요구사항 A·B·C: 명세서 확정 전에 이슈에서 만들어진 것."""
        issues = [(eid, p) for kind, eid, p in items if kind == "issue"]
        made = seed_issue_requirements(cur, self.ids["TD-PRJ-1"], self.ids["TD-CON-1"], issues)
        for req in d.REQUIREMENTS.values():
            num = next(i.number for i in d.GITHUB_ISSUES_CON1 if i.tid == req.source_issue)
            self.ids[req.tid] = made[f"issue:{num}"]

    # ------------------------------------------------------------ 문서·산출물

    def _upload(self, acc: str, prj: str, tid: str, wbs_id: str | None = None) -> str:
        path = self.files[tid]
        mime = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "md": "text/markdown",
        }[path.suffix.lstrip(".")]
        with path.open("rb") as f:
            res = self.c.post(
                f"/api/projects/{self.ids[prj]}/documents",
                files={"file": (path.name, f, mime)},
                data={"wbsId": wbs_id} if wbs_id else {},
                headers=self._h(acc),
            )
        body = self._ok(res, 200, 201, 202)
        self.ids[tid] = body["id"]
        return body["id"]

    def _confirm_work_product(
        self,
        acc: str,
        doc_tid: str,
        type_code: str,
        title: str,
        version: str,
        status: str = "SUBMITTED",
    ) -> str:
        body = self._ok(
            self.c.post(
                f"/api/documents/{self.ids[doc_tid]}/draft/confirm",
                json={
                    "type": type_code,
                    "title": title,
                    "version": version,
                    "requirements": [],
                    "workProductStatus": status,
                },
                headers=self._h(acc),
            )
        )
        self.ids[f"{doc_tid}:wp"] = body["workProductId"]
        return body["workProductId"]

    def _materialize_wbs(self) -> None:
        self._ok(
            self.c.get(
                f"/api/projects/{self.ids['TD-PRJ-1']}/progress?at={d.T0.isoformat()}",
                headers=self._h("TD-ACC-C1"),
            )
        )

    def _confirm_31(self) -> None:
        """S0: 3.1 완료 확인됨(요청 → 보고 → 확인완료). 미처리 0 유지."""
        pid = self.ids["TD-PRJ-1"]
        req = self._ok(
            self.c.post(
                f"/api/projects/{pid}/review-requests",
                json={
                    "targetType": "WBS_ITEM",
                    "targetKey": "3.1",
                    "title": "요구사항 정의 완료 확인",
                    "body": "",
                    "purpose": "WBS_COMPLETION",
                    "completionScope": "요구사항정의서 v1 승인으로 3.1 완료",
                },
                headers=self._h("TD-ACC-C1"),
            )
        )
        rid = req["id"]
        self._ok(
            self.c.post(
                f"/api/review-requests/{rid}/report",
                json={
                    "body": "요구사항정의서 v1 제출·승인 완료",
                    "evidence": [
                        {
                            "kind": "WORK_PRODUCT",
                            "ref": "",
                            "note": "",
                            "workProductId": self.ids["TD-DOC-2:wp"],
                        }
                    ],
                },
                headers=self._h("TD-ACC-V1"),
            )
        )
        self._ok(
            self.c.post(
                f"/api/review-requests/{rid}/confirm",
                json={"acknowledgeCompletion": True, "note": "확인"},
                headers=self._h("TD-ACC-C1"),
            )
        )
        self.ids["TD-RR-31"] = rid

    def _snapshots(self, cur: Any, prj: str, start: date, end: date) -> None:
        day = start
        while day <= end:
            snapshot_service.take_unchecked(cur, self.ids[prj], day, None)
            day += timedelta(days=1)

    # ------------------------------------------------------------ 상태

    def s0(self) -> Seeder:
        if self.state != "none":
            raise SeedError("S0 는 빈 상태에서만 만든다")
        self._orgs_and_clients()
        self._projects()
        self._contractors()
        items = self._raw_items("S0")
        with tx() as cur:
            self._connections(cur)
            for tid, rows in items.items():
                self._load(cur, tid, rows)
            self._legacy_requirements(cur, items["TD-CON-1"])
            self._promote_all(cur)
        # A 발주기관 지정 「검증」(T0 전, 사유 「1차 시험 통과 확인」)
        self._ok(
            self.c.put(
                f"/api/projects/{self.ids['TD-PRJ-1']}/requirements/{self.ids['TD-REQ-A']}/status",
                json={"status": "VERIFIED", "reason": "1차 시험 통과 확인"},
                headers=self._h("TD-ACC-C1"),
            )
        )
        self.notes.append("TD-REQ-A 지정 시각은 투입 시각이다(T0 전으로 둘 수단 없음)")
        self._materialize_wbs()
        # 문서: 명세서(처리만), 요구사항정의서(3.1 산출물 v1 승인), 회의록
        self._upload("TD-ACC-V1", "TD-PRJ-1", "TD-DOC-1")
        self._upload("TD-ACC-V1", "TD-PRJ-1", "TD-DOC-2", wbs_id="3.1")
        self._confirm_work_product(
            "TD-ACC-V1", "TD-DOC-2", "REQUIREMENTS_SPEC", "요구사항정의서", "v1"
        )
        self._ok(
            self.c.post(
                f"/api/projects/{self.ids['TD-PRJ-1']}/work-products/{self.ids['TD-DOC-2:wp']}/approve",
                headers=self._h("TD-ACC-C1"),
            )
        )
        self._upload("TD-ACC-V1", "TD-PRJ-1", "TD-DOC-5")
        # 시험 사업 자료
        for tid in ("TD-DOC-8", "TD-DOC-9", "TD-DOC-14"):
            self._upload("TD-ACC-V1", "TD-PRJ-9", tid)
        self._confirm_31()
        with tx() as cur:
            self._snapshots(cur, "TD-PRJ-1", d.PROJECTS["TD-PRJ-1"].start, d.T0 - timedelta(days=1))
        self.state = "S0"
        return self

    def s0r(self) -> Seeder:
        """S0 + 확인 요청 TD-RR-1 (7.6)."""
        pid = self.ids["TD-PRJ-1"]
        rr = d.REVIEW_REQUEST_TD_RR_1
        req = self._ok(
            self.c.post(
                f"/api/projects/{pid}/review-requests",
                json={
                    "targetType": rr["target"][0],
                    "targetKey": rr["target"][1],
                    "title": rr["title"],
                    "body": "",
                    "purpose": "GENERAL",
                },
                headers=self._h("TD-ACC-C1"),
            )
        )
        self.ids["TD-RR-1"] = req["id"]
        self.state = "S0r"
        return self

    def s0a(self) -> Seeder:
        """+ TD-DOC-3 업로드·SW설계서 v1 제출본(3.2 연결). 실적·이슈·커밋은 그대로."""
        self._upload("TD-ACC-V1", "TD-PRJ-1", "TD-DOC-3", wbs_id="3.2")
        self._confirm_work_product("TD-ACC-V1", "TD-DOC-3", "SOFTWARE_DESIGN", "SW설계서", "v1")
        self.state = "S0a"
        return self

    def s1(self) -> Seeder:
        """원천 변경(WBS 3.2 85%, R4 해결, TD-CMT-2·설계서 파일) → 수집 → 09-15~09-26 스냅샷."""
        items = self._raw_items("S1")
        with tx() as cur:
            for tid in ("TD-CON-1", "TD-CON-2"):
                self._load(cur, tid, items[tid])
            self._promote_all(cur)
            self._snapshots(cur, "TD-PRJ-1", d.T0, d.T1)
        self.state = "S1"
        return self

    def s1r(self) -> Seeder:
        """+ TD-RR-1 조치 보고."""
        rr = d.REVIEW_REQUEST_TD_RR_1
        self._ok(
            self.c.post(
                f"/api/review-requests/{self.ids['TD-RR-1']}/report",
                json={
                    "body": rr["report"],
                    "evidence": [
                        {
                            "kind": "WORK_PRODUCT",
                            "ref": "",
                            "note": "",
                            "workProductId": self.ids["TD-DOC-3:wp"],
                        }
                    ],
                },
                headers=self._h("TD-ACC-V1"),
            )
        )
        self.state = "S1r"
        return self

    # ------------------------------------------------------------ 정리

    def cleanup(self) -> None:
        """만든 사업·계정·조직을 지운다. 사업 삭제가 하위 행을 끌고 간다."""
        with tx() as cur:
            for tid in d.PROJECTS:
                if tid in self.ids:
                    cur.execute("delete from project where id = %s", (self.ids[tid],))
            cur.execute("delete from app_user where username like 'td-%%'")
            cur.execute(
                "delete from organization where name = any(%s) and not exists "
                "(select 1 from app_user u where u.organization_id = organization.id)",
                ([o.name for o in d.ORGS.values()],),
            )


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_id() -> str:
    return str(uuid.uuid4())
