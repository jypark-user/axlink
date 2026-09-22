"""커넥터 포트 계약 (SWFR.CON.001).

상위 계층은 포트만 알아야 한다. 여기서 지키는 것 셋 —
등록소를 거치면 도구별 분기가 없고, 등록 안 된 도구는 조용히 실패하지 않고
501 로 드러나고, 어댑터는 포트가 요구하는 표면을 전부 가진다.
"""

import pytest

from app.common import errors
from app.integration import adapter, port


def test_등록된_도구는_어댑터가_나온다():
    assert port.get_connector("GITHUB").item_kinds == (
        "issue", "pull_request", "commit", "milestone", "tree"
    )
    assert port.get_connector("REDMINE").item_kinds == ("issue", "version", "tracker")


def test_등록_안_된_도구는_501_로_드러난다():
    with pytest.raises(errors.ApiError) as exc:
        port.get_connector("JIRA")
    assert exc.value.status == 501
    assert exc.value.code == "NOT_IMPLEMENTED"


def test_어댑터는_포트_표면을_전부_가진다():
    """새 어댑터를 등록하면 이 시험이 표면 누락을 잡는다."""
    for tool, connector in adapter.CONNECTORS.items():
        assert connector.tool == tool
        assert isinstance(connector.item_kinds, tuple) and connector.item_kinds
        for method in ("verify", "fetch_items", "fetch_file"):
            assert callable(getattr(connector, method)), f"{tool} 에 {method} 가 없다"
