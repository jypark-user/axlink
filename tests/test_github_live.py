"""실제 GitHub 연결 검증 — AXLINK_GH_TOKEN·AXLINK_GH_REPO 가 있을 때만 돈다.

박PM 시나리오의 "본인 저장소를 실제로 붙여본다" 를 그대로 재현한다. 토큰이 없으면 skip.

    AXLINK_GH_TOKEN=ghp_... AXLINK_GH_REPO=owner/repo \
      .venv/Scripts/python -m pytest tests/test_github_live.py -v
"""

import os

import pytest

from app.common.errors import ApiError
from app.integration.adapter import github_connector as github

_TOKEN = os.environ.get("AXLINK_GH_TOKEN")
_REPO = os.environ.get("AXLINK_GH_REPO", "")

# 실모델·실원천을 부른다. AXLINK_LIVE=1 일 때만 돈다(conftest).
pytestmark = pytest.mark.live

live = pytest.mark.skipif(not _TOKEN, reason="AXLINK_GH_TOKEN 이 있어야 실제 GitHub 를 검증한다")


@live
def test_real_repo_reachable():
    probe = github.verify("https://api.github.com", _REPO, _TOKEN)
    assert probe.name  # 저장소 full_name
    assert "commit" in probe.readable or "commit" in probe.denied


@live
def test_real_fetch_commits():
    """실제 저장소에서 커밋 한 페이지를 가져온다 — 전체수집의 핵심 경로."""
    got = list(github.fetch_items("https://api.github.com", _REPO, _TOKEN, "commit", 5, 1))
    assert got, "커밋이 하나는 있어야 한다"
    external_id, payload = got[0]
    assert external_id.startswith("commit:")
    assert "sha" in payload


def test_invalid_token_maps_to_401():
    """토큰 없이도 도는 검증 — 실제 api.github.com 이 401 을 주는지 본다."""
    with pytest.raises(ApiError) as exc:
        github.verify("https://api.github.com", "octocat/Hello-World", "ghp_definitely_invalid")
    assert exc.value.status == 401
    assert exc.value.code == "TOOL_AUTH"
