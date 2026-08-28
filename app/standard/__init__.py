"""표준화 계층 [3]. 이종 도구의 원본을 표준 데이터 모델로 정규화한다.

SWFR.PIP.002 — 각 항목의 원천 도구·원본 ID·원문 위치를 보존해야 한다.
그래서 모든 표준 레코드는 tool_connection_id + external_id + external_url 을 함께 들고 있다.
"""
