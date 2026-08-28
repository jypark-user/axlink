"""실제 GitHub 연결 검증 — AXLINK_GH_TOKEN·AXLINK_GH_REPO 가 있을 때만 돈다.

박PM 시나리오의 "본인 저장소를 실제로 붙여본다" 를 그대로 재현한다. 토큰이 없으면 skip.

    AXLINK_GH_TOKEN=ghp_... AXLINK_GH_REPO=owner/repo \
      .venv/Scripts/python -m pytest tests/test_github_live.py -v
"""

import os

import pytest

from app.common.errors import ApiError
from app.integration import github

_TOKEN = os.environ.get("AXLINK_GH_TOKEN")
_REPO = os.environ.get("AXLINK_GH_REPO", "")

live = pytest.mark.skipif(not _TOKEN, reason="AXLINK_GH_TOKEN 이 있어야 실제 GitHub 를 검증한다")


@live
def test_real_repo_reachable():
    name, detected = github.verify("https://api.github.com", _REPO, _TOKEN)
    assert name  # 저장소 full_name
    assert "commit" in detected


def test_invalid_token_maps_to_401():
    """토큰 없이도 도는 검증 — 실제 api.github.com 이 401 을 주는지 본다."""
    with pytest.raises(ApiError) as exc:
        github.verify("https://api.github.com", "octocat/Hello-World", "ghp_definitely_invalid")
    assert exc.value.status == 401
    assert exc.value.code == "TOOL_AUTH"
