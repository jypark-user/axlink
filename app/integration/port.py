"""커넥터 포트. 상위 계층(등록·수집)은 이 계약만 알고 도구를 모른다 (SWFR.CON.001).

새 도구는 어댑터 구현 + 등록소 한 줄 + tool_type CHECK 마이그레이션 한 줄로 붙는다.
자격증명은 복호화된 비밀 문자열 하나로 넘기고 해석은 어댑터 책임이다 — GitHub 는
Bearer 토큰, Redmine 은 API 키, Jira 라면 Basic 쌍. 도구마다 달라 상위가 알 이유가 없다.
"""

from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.common import errors


@dataclass
class ProbeResult:
    """연결 테스트 결과. 항목종류별 가독 여부까지 밝힌다 — 수집 때 조용히 실패하지 않게."""

    name: str
    readable: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


@dataclass
class PageResult:
    """항목종류 하나를 읽다가 회차 상한(max_pages)에 걸렸을 때 어댑터가 돌려주는 값.

    resume_since: 갱신 오름차순 목록. 다음 회차가 이 시각부터(같은 시각 포함) 다시 읽는다.
    gap: (since, until). 최신부터 오는 목록이 상한에 걸려 이 구간의 오래된 쪽을 못 읽었다.
         다음 회차가 이 구간을 따로 읽는다.
    둘 다 없으면 이어 읽을 자리를 모른다. 다음 회차는 같은 범위를 처음부터 다시 읽는다.
    """

    truncated: bool = True
    resume_since: datetime | None = None
    gap: tuple[datetime, datetime] | None = None


class ToolConnector(Protocol):
    """읽기 전용 커넥터 계약 (QUR.CON.001 — 원천에 아무것도 쓰지 않는다)."""

    tool: str  # tool_connection.tool 값 그대로
    item_kinds: tuple[str, ...]  # 수집 항목종류. 도구 어휘 그대로 raw_artifact 에 적힌다

    def verify(self, base_url: str, target: str, secret: str) -> ProbeResult:
        """대상에 닿는지 + 항목종류별로 실제 읽히는지 확인한다."""
        ...

    def fetch_items(
        self,
        base_url: str,
        target: str,
        secret: str,
        kind: str,
        per_page: int,
        max_pages: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Generator[tuple[str, dict[str, Any]], None, "PageResult | None"]:
        """(외부 ID, 원본 payload) 를 낸다. 원본은 가공하지 않고 그대로 적재한다.

        since 가 있으면 그 시각 이후 갱신분만 낸다(SWFR.CON.005). until 은 그 시각까지만
        (이어 읽을 구간을 다시 읽을 때). 도구가 필터를 지원하지 않는 항목종류는 전량을 내도
        된다 — 내용해시 적재가 걸러 준다.

        다 읽고 끝나면 None 을 돌려준다(generator 의 return). max_pages 에 걸려 멈추면
        PageResult(truncated=True) 와 다음 회차가 이어 읽을 자리를 돌려준다(점검 DATA-01).
        """
        ...

    def fetch_file(
        self,
        base_url: str,
        target: str,
        secret: str,
        path: str,
        ref: str | None = None,
    ) -> dict[str, Any] | None:
        """저장소 파일 수집(WBS 가 이 경로로 온다). 파일 개념이 없는 도구는 None."""
        ...


def get_connector(tool: str) -> ToolConnector:
    # 어댑터가 이 모듈을 import 하므로 등록소는 호출 시점에 읽는다.
    from app.integration import adapter

    connector = adapter.CONNECTORS.get(tool)
    if connector is None:
        raise errors.ApiError(501, "NOT_IMPLEMENTED", f"{tool} 연결은 아직 준비 중입니다.")
    return connector
