"""IM-009 공통 시험 자료의 상수 (docs/30-test/IM-009-공통시험자료.md 1~5절).

도구 원시 응답(GitHub·Redmine REST)과 무관한 **도메인 값**만 둔다. 원시 응답 꼴로 바꾸는 일은
`payloads.py` 가 한다. 값을 바꾸면 7절 기대값이 깨지므로, 바꾸려면 IM-009 를 먼저 고친다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

T0 = date(2026, 9, 15)  # 기준일(Asia/Seoul). 공유 PC 시계를 바꾸지 않고 주입한다
T1 = date(2026, 9, 26)  # S1 시점 (T0+11)


# 1. 조직과 계정 --------------------------------------------------------------


@dataclass(frozen=True)
class Org:
    tid: str
    name: str
    kind: str  # CLIENT | CONTRACTOR | PLATFORM


ORGS = {
    "TD-ORG-C1": Org("TD-ORG-C1", "가람시 정보화원", "CLIENT"),
    "TD-ORG-C2": Org("TD-ORG-C2", "나래군청", "CLIENT"),
    "TD-ORG-V1": Org("TD-ORG-V1", "다온소프트", "CONTRACTOR"),
    "TD-ORG-V2": Org("TD-ORG-V2", "라온시스템", "CONTRACTOR"),
    "TD-ORG-V3": Org("TD-ORG-V3", "마루아이티", "CONTRACTOR"),
    "TD-ORG-P": Org("TD-ORG-P", "플랫폼 운영", "PLATFORM"),
}


@dataclass(frozen=True)
class Account:
    tid: str
    username: str
    display: str
    role: str  # CLIENT | CONTRACTOR | SUPER_ADMIN
    org: str
    projects: tuple[str, ...]


ACCOUNTS = {
    "TD-ACC-C1": Account(
        "TD-ACC-C1",
        "td-c1",
        "김주무관",
        "CLIENT",
        "TD-ORG-C1",
        ("TD-PRJ-1", "TD-PRJ-3", "TD-PRJ-9"),
    ),
    "TD-ACC-C2": Account("TD-ACC-C2", "td-c2", "이담당", "CLIENT", "TD-ORG-C2", ("TD-PRJ-2",)),
    "TD-ACC-V1": Account(
        "TD-ACC-V1", "td-v1", "박피엠", "CONTRACTOR", "TD-ORG-V1", ("TD-PRJ-1", "TD-PRJ-9")
    ),
    "TD-ACC-V2": Account("TD-ACC-V2", "td-v2", "최과장", "CONTRACTOR", "TD-ORG-V2", ("TD-PRJ-1",)),
    "TD-ACC-V3": Account("TD-ACC-V3", "td-v3", "정부장", "CONTRACTOR", "TD-ORG-V3", ("TD-PRJ-2",)),
    "TD-ACC-V0": Account("TD-ACC-V0", "td-v0", "한신입", "CONTRACTOR", "TD-ORG-V1", ()),
    "TD-ACC-A1": Account("TD-ACC-A1", "td-a1", "운영자", "SUPER_ADMIN", "TD-ORG-P", ()),
}


# 2. 사업 ----------------------------------------------------------------------


@dataclass(frozen=True)
class Project:
    tid: str
    name: str
    client: str
    lead: str | None
    participants: tuple[str, ...]
    start: date
    end: date


PROJECTS = {
    "TD-PRJ-1": Project(
        "TD-PRJ-1",
        "시민포털 고도화",
        "TD-ORG-C1",
        "TD-ORG-V1",
        ("TD-ORG-V2",),
        date(2026, 3, 2),
        date(2026, 11, 30),
    ),
    "TD-PRJ-2": Project(
        "TD-PRJ-2",
        "군정 데이터 연계",
        "TD-ORG-C2",
        "TD-ORG-V3",
        (),
        date(2026, 5, 1),
        date(2026, 12, 31),
    ),
    "TD-PRJ-3": Project(
        "TD-PRJ-3",
        "민원 챗봇 사전검토",
        "TD-ORG-C1",
        None,
        (),
        date(2026, 9, 1),
        date(2026, 12, 31),
    ),
    "TD-PRJ-9": Project(
        "TD-PRJ-9",
        "[시험] 거절·실패",
        "TD-ORG-C1",
        "TD-ORG-V1",
        (),
        date(2026, 9, 1),
        date(2026, 12, 31),
    ),
}


# 3. 도구 연결 -----------------------------------------------------------------


@dataclass(frozen=True)
class Connection:
    tid: str
    project: str
    tool: str  # GITHUB | REDMINE
    base_url: str
    target: str
    owner: str
    mapping: dict = field(default_factory=dict)


CONNECTIONS = {
    "TD-CON-1": Connection(
        "TD-CON-1",
        "TD-PRJ-1",
        "GITHUB",
        "https://api.github.com",
        "daon/citizen-portal",
        "TD-ORG-V1",
        {
            "designDocPaths": ["docs/20-design/*.md"],
            "collectFiles": {"docs/00-management/WBS.xlsx": "PROJECT_PLAN"},
        },
    ),
    "TD-CON-2": Connection(
        "TD-CON-2",
        "TD-PRJ-1",
        "REDMINE",
        "https://redmine.example.test",
        "citizen-portal",
        "TD-ORG-V1",
        {"riskTracker": "리스크", "reqIdField": "요구사항 ID"},
    ),
    "TD-CON-3": Connection(
        "TD-CON-3",
        "TD-PRJ-1",
        "GITHUB",
        "https://api.github.com",
        "raon/citizen-portal-web",
        "TD-ORG-V2",
    ),
    "TD-CON-4": Connection(
        "TD-CON-4",
        "TD-PRJ-2",
        "REDMINE",
        "https://redmine.example.test",
        "narae-link",
        "TD-ORG-V3",
    ),
}


# 4.1 기존 요구사항 (명세서 확정 전, 이슈 출처) -------------------------------------


@dataclass(frozen=True)
class Requirement:
    tid: str
    code: str
    title: str
    priority: str
    source_issue: str
    decided: tuple[str, str] | None = None  # (상태, 사유)


REQUIREMENTS = {
    "TD-REQ-A": Requirement(
        "TD-REQ-A",
        "UR.PORT.001",
        "통합 로그인",
        "필수",
        "TD-ISS-G1",
        ("VERIFIED", "1차 시험 통과 확인"),
    ),
    "TD-REQ-B": Requirement("TD-REQ-B", "UR.PORT.002", "민원 신청 조회", "필수", "TD-ISS-G2"),
    "TD-REQ-C": Requirement("TD-REQ-C", "UR.PORT.003", "접속 통계", "선택", "TD-ISS-G3"),
}


# 5.3 이슈 ---------------------------------------------------------------------


@dataclass(frozen=True)
class RedmineIssue:
    tid: str
    number: int
    tracker: str
    subject: str
    status_s0: str
    status_s1: str
    priority: str
    req_id: str | None
    version: str | None
    relation: tuple[str, str] | None = None  # (대상 이슈 tid, 관계 종류)
    start: date | None = None
    due: date | None = None
    done_ratio: int | None = None
    assignee: str = "박피엠"


REDMINE_ISSUES_PRJ1 = [
    RedmineIssue(
        "TD-ISS-R1",
        201,
        "일감",
        "로그인 API 구현",
        "종료",
        "종료",
        "보통",
        "UR.PORT.001",
        "1차",
        start=date(2026, 3, 10),
        due=date(2026, 4, 10),
        done_ratio=100,
    ),
    RedmineIssue(
        "TD-ISS-R2",
        202,
        "일감",
        "세션 저장소 교체",
        "종료",
        "종료",
        "보통",
        "UR.PORT.001",
        "1차",
        relation=("TD-ISS-R1", "follows"),
        start=date(2026, 4, 1),
        due=date(2026, 4, 25),
        done_ratio=100,
    ),
    RedmineIssue(
        "TD-ISS-R3",
        203,
        "일감",
        "민원 조회 화면",
        "종료",
        "종료",
        "높음",
        "UR.PORT.002",
        "2차",
        start=date(2026, 5, 1),
        due=date(2026, 6, 30),
        done_ratio=100,
    ),
    RedmineIssue(
        "TD-ISS-R4",
        204,
        "일감",
        "외부 연계 규격 협의",
        "진행중",
        "해결",
        "높음",
        None,
        "2차",
        relation=("TD-ISS-R3", "precedes"),
        start=date(2026, 6, 1),
        due=date(2026, 7, 31),
        done_ratio=60,
    ),
    RedmineIssue(
        "TD-ISS-R5",
        205,
        "일감",
        "접속 통계 배치",
        "진행중",
        "진행중",
        "낮음",
        "UR.PORT.003",
        "3차",
        start=date(2026, 8, 1),
        due=date(2026, 10, 31),
        done_ratio=20,
    ),
    RedmineIssue(
        "TD-ISS-R6",
        206,
        "일감",
        "코드 정리",
        "종료",
        "종료",
        "낮음",
        None,
        "2차",
        start=date(2026, 7, 1),
        due=date(2026, 7, 15),
        done_ratio=100,
    ),
    RedmineIssue(
        "TD-ISS-R7", 207, "리스크", "외부 기관 일정 미확정", "진행중", "진행중", "긴급", None, None
    ),
    RedmineIssue("TD-ISS-R8", 208, "리스크", "서버 반입 지연", "종료", "종료", "보통", None, None),
    RedmineIssue(
        "TD-ISS-R9",
        209,
        "결함",
        "로그인 오류 메시지 깨짐",
        "종료",
        "종료",
        "높음",
        "UR.PORT.001",
        None,
    ),
    RedmineIssue(
        "TD-ISS-R10",
        210,
        "결함",
        "조회 결과 정렬 오류",
        "진행중",
        "진행중",
        "보통",
        "UR.PORT.002",
        None,
    ),
]

# 5.5 TD-PRJ-2 (L3 자료)
REDMINE_ISSUES_PRJ2 = [
    RedmineIssue(
        "TD-ISS-N1",
        301,
        "일감",
        "연계 규격 정의",
        "종료",
        "종료",
        "보통",
        None,
        "V-A",
        start=date(2026, 5, 1),
        due=date(2026, 6, 30),
        done_ratio=100,
        assignee="정부장",
    ),
    RedmineIssue(
        "TD-ISS-N2",
        302,
        "일감",
        "연계 모듈 설계",
        "종료",
        "종료",
        "보통",
        None,
        "V-A",
        start=date(2026, 6, 1),
        due=date(2026, 7, 15),
        done_ratio=100,
        assignee="정부장",
    ),
    RedmineIssue(
        "TD-ISS-N3",
        303,
        "일감",
        "테스트 데이터 준비",
        "진행중",
        "진행중",
        "보통",
        None,
        "V-A",
        start=date(2026, 7, 1),
        due=date(2026, 7, 31),
        done_ratio=50,
        assignee="정부장",
    ),
    RedmineIssue(
        "TD-ISS-N4",
        304,
        "일감",
        "연계 모듈 구현",
        "진행중",
        "진행중",
        "보통",
        None,
        "V-B",
        start=date(2026, 8, 1),
        due=date(2026, 10, 15),
        done_ratio=30,
        assignee="정부장",
    ),
    RedmineIssue(
        "TD-ISS-N5",
        305,
        "일감",
        "운영 이관",
        "신규",
        "신규",
        "보통",
        None,
        "V-B",
        start=date(2026, 10, 1),
        due=date(2026, 10, 31),
        done_ratio=0,
        assignee="정부장",
    ),
    RedmineIssue(
        "TD-ISS-N6",
        306,
        "일감",
        "보안 점검",
        "신규",
        "신규",
        "보통",
        None,
        "V-B",
        assignee="정부장",
    ),
    RedmineIssue(
        "TD-ISS-N7",
        307,
        "일감",
        "착수 회의",
        "종료",
        "종료",
        "보통",
        None,
        None,
        start=date(2026, 5, 1),
        due=date(2026, 5, 2),
        done_ratio=100,
        assignee="정부장",
    ),
]


@dataclass(frozen=True)
class GithubIssue:
    tid: str
    number: int
    title: str
    labels: tuple[str, ...]
    closed: bool
    milestone: str | None
    body: str = ""


GITHUB_ISSUES_CON1 = [
    GithubIssue(
        "TD-ISS-G1",
        1,
        "[UR.PORT.001] 통합 로그인",
        ("유형: 요구사항",),
        True,
        "M-a",
        "| 중요도 | 필수 |",
    ),
    GithubIssue(
        "TD-ISS-G2",
        2,
        "[UR.PORT.002] 민원 신청 조회",
        ("유형: 요구사항",),
        False,
        "M-b",
        "| 중요도 | 필수 |",
    ),
    GithubIssue(
        "TD-ISS-G3",
        3,
        "[UR.PORT.003] 접속 통계",
        ("유형: 요구사항",),
        False,
        None,
        "| 중요도 | 선택 |",
    ),
    GithubIssue("TD-ISS-G4", 4, "로그인 버튼 정렬", (), True, "M-a", "외부 연계 협의 RM-204 참고"),
    GithubIssue("TD-ISS-G5", 5, "빌드 스크립트 정리", (), True, "M-a"),
]
GITHUB_ISSUES_CON3 = [
    GithubIssue("TD-ISS-W3", 3, "웹 번들 축소", (), False, None),
]


@dataclass(frozen=True)
class Commit:
    tid: str
    connection: str
    sha: str
    message: str
    files: tuple[str, ...]
    authored: str  # ISO UTC
    state: str  # S0 | S1


COMMITS = [
    Commit(
        "TD-CMT-1",
        "TD-CON-1",
        "a1f0c0de0001a1f0c0de0001a1f0c0de0001a1f0",
        "feat(auth): 통합 로그인 구현 [UR.PORT.001]",
        ("src/auth/login.py",),
        "2026-04-05T09:00:00Z",
        "S0",
    ),
    Commit(
        "TD-CMT-2",
        "TD-CON-1",
        "b2e1d0c20002b2e1d0c20002b2e1d0c20002b2e1",
        "docs: 설계서 초안 추가",
        ("docs/20-design/SW설계서_v0.9.docx",),
        "2026-09-20T09:00:00Z",
        "S1",
    ),
    Commit(
        "TD-CMT-3",
        "TD-CON-1",
        "c3d2e1f30003c3d2e1f30003c3d2e1f30003c3d2",
        "fix: 버튼 정렬 GH-4",
        ("src/ui/button.css",),
        "2026-05-20T09:00:00Z",
        "S0",
    ),
    Commit(
        "TD-CMT-4",
        "TD-CON-1",
        "d4c3b2a40004d4c3b2a40004d4c3b2a40004d4c3",
        "fix: 통계 배치 GH-3",
        ("src/stats/batch.py",),
        "2026-08-10T09:00:00Z",
        "S0",
    ),
    Commit(
        "TD-CMT-W1",
        "TD-CON-3",
        "e5d4c3b50005e5d4c3b50005e5d4c3b50005e5d4",
        "chore: 번들 축소 GH-3",
        ("web/bundle.js",),
        "2026-08-12T09:00:00Z",
        "S0",
    ),
]
# 저장소 수집 파일. 사업수행계획서 제출본의 버전은 이 파일을 담은 커밋 해시다
WBS_FILE_COMMIT_S0 = "f6e5d4c60006f6e5d4c60006f6e5d4c60006f6e5"
WBS_FILE_COMMIT_S1 = "0706e5d70007a706e5d70007a706e5d70007a706"


@dataclass(frozen=True)
class PullRequest:
    tid: str
    number: int
    title: str
    body: str
    merged: bool
    closes: tuple[int, ...]  # 도구가 만든 연결(구조적)
    files: tuple[str, ...]


PULL_REQUESTS_CON1 = [
    PullRequest("TD-PR-1", 6, "버튼 정렬 수정", "Closes #4", True, (4,), ("src/ui/button.css",)),
    PullRequest("TD-PR-2", 7, "조회 화면 개선", "RM-203 참고", True, (), ("src/portal/list.py",)),
    PullRequest(
        "TD-PR-3", 8, "[UR.PORT.001] 로그인 리팩터링", "", True, (), ("src/auth/login.py",)
    ),
]


# 5.4 마일스톤 -----------------------------------------------------------------


@dataclass(frozen=True)
class Milestone:
    tid: str
    connection: str
    name: str
    due: date | None
    closed: bool
    closed_on: date | None
    number: int


MILESTONES = [
    Milestone("TD-MS-1", "TD-CON-2", "1차", date(2026, 4, 30), True, date(2026, 4, 28), 11),
    Milestone("TD-MS-2", "TD-CON-2", "2차", date(2026, 8, 31), False, None, 12),
    Milestone("TD-MS-3", "TD-CON-2", "3차", date(2026, 11, 30), False, None, 13),
    Milestone("TD-MS-4", "TD-CON-2", "상시", None, False, None, 14),
    Milestone("TD-MS-5", "TD-CON-1", "M-a", date(2026, 5, 31), True, date(2026, 6, 3), 1),
    Milestone("TD-MS-6", "TD-CON-1", "M-b", date(2026, 10, 31), False, None, 2),
]
MILESTONES_PRJ2 = [
    Milestone("TD-MS-VA", "TD-CON-4", "V-A", date(2026, 7, 31), False, None, 21),
    Milestone("TD-MS-VB", "TD-CON-4", "V-B", date(2026, 10, 31), False, None, 22),
]


# 7.6 확인 요청 ---------------------------------------------------------------

REVIEW_REQUEST_TD_RR_1 = {
    "target": ("WBS_ITEM", "3.2"),
    "title": "설계서 제출 일정과 외부 연계 규격 협의 현황을 회신 바랍니다",
    "report": "설계서 초안 제출. 규격 협의 8/25 완료.",
}


# 7.3 기대값(S0) — 투입 뒤 자가 점검에 쓴다 ------------------------------------

EXPECTED_S0 = {
    "issues_total": 16,
    "general_issues": 9,
    "general_closed": 6,
    "risks": 2,
    "defects": 2,
    "commits": 2,
    "pull_requests": 3,
    "milestones": 6,
    "requirements": 3,
    "submissions": 2,
    "progress_pct": 30.0,
    "plan_pct_t0": 66.9,
}
