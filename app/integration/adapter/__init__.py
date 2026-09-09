"""어댑터 등록소. 새 도구 연동은 어댑터 구현체 추가 + 여기 한 줄이다 (SWFR.CON.001)."""

from app.integration.adapter.github_connector import GitHubConnector
from app.integration.adapter.redmine_connector import RedmineConnector
from app.integration.port import ToolConnector

CONNECTORS: dict[str, ToolConnector] = {
    GitHubConnector.tool: GitHubConnector(),
    RedmineConnector.tool: RedmineConnector(),
}
