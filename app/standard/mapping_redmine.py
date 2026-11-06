"""Redmine 원본 → 표준 모델 매핑. 순수 함수만 둔다(DB·네트워크 없음).

트래커가 갈림길이다 — 「리스크」 트래커는 risk 로, 나머지(작업·결함·지원)는 issue 로
승격한다. 요구사항은 만들지 않는다 — 요구사항은 명세서(기준선)로만 만든다(ARC-030).

상태·우선순위 이름은 인스턴스마다 다르다. is_closed 플래그를 1차 근거로 쓰고 이름은
보조로 본다. 이름 규칙의 설정화는 SWFR.CON.002 가 mapping_rules_json 으로 뺀다.
"""

from typing import Any

from app.standard.mapping_rules import MappingRules

_DEFAULT_RULES = MappingRules()

_STATUS = {"진행": "IN_PROGRESS", "해결": "RESOLVED"}
_RISK_SEVERITY = {
    "낮음": "LOW", "보통": "MEDIUM", "높음": "HIGH", "긴급": "CRITICAL", "즉시": "CRITICAL",
}


def tracker_name(payload: dict[str, Any]) -> str:
    return ((payload.get("tracker") or {}).get("name") or "").strip()


def is_risk(payload: dict[str, Any], rules: MappingRules = _DEFAULT_RULES) -> bool:
    """어떤 트래커가 리스크인지는 연결별 설정이다(SWFR.CON.002)."""
    return tracker_name(payload) == rules.risk_tracker


def req_id(payload: dict[str, Any], rules: MappingRules = _DEFAULT_RULES) -> str | None:
    """커스텀 필드 REQ ID — 도구를 가로지르는 접착제(작업 규약 §2). 추적관계의 재료다.
    업체가 필드를 뭐라 부르는지는 연결별 설정이다(SWFR.CON.002)."""
    for f in payload.get("custom_fields") or []:
        if f.get("name") == rules.req_id_field and f.get("value"):
            return str(f["value"])
    return None


def _name(entity: Any) -> str:
    return ((entity or {}).get("name") or "").strip()


def _status(payload: dict[str, Any]) -> str:
    st = payload.get("status") or {}
    if st.get("is_closed"):
        return "CLOSED"
    return _STATUS.get(_name(st), "OPEN")


def _url(base_url: str, payload: dict[str, Any]) -> str:
    return f"{(base_url or '').rstrip('/')}/issues/{payload.get('id')}"


def to_issue(payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    status = _status(payload)
    return {
        "issue_key": f"RM-{payload.get('id')}",
        "title": (payload.get("subject") or "").strip()[:500],
        "body": payload.get("description") or "",
        "status": status,
        # 우선순위는 심각도가 아니다. 둘을 잇는 합의된 대응표가 없어 심각도는 비우고(GH-116)
        # 우선순위는 원문 그대로 따로 남긴다
        "severity": None,
        "source_priority": _name(payload.get("priority")) or None,
        "assignee": _name(payload.get("assigned_to")) or None,
        "source_created_at": payload.get("created_on"),
        "source_updated_at": payload.get("updated_on"),
        "resolved_at": payload.get("closed_on") if status in ("RESOLVED", "CLOSED") else None,
        "external_url": _url(base_url, payload),
    }


def to_risk(payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    st = payload.get("status") or {}
    if st.get("is_closed"):
        status = "CLOSED"
    elif _name(st) in ("진행", "해결"):
        status = "MITIGATING"
    else:
        status = "OPEN"
    created = payload.get("created_on") or ""
    return {
        "title": (payload.get("subject") or "").strip()[:500],
        "body": payload.get("description") or "",
        # Redmine 기본 필드에는 발생확률·영향 개념이 없다. 우선순위를 심각도로 읽고
        # 나머지는 중간값으로 둔다 — 없는 것을 지어내지 않는다.
        "probability": "MEDIUM",
        "impact": "MEDIUM",
        "severity": _RISK_SEVERITY.get(_name(payload.get("priority")), "MEDIUM"),
        "mitigation": None,
        "owner": _name(payload.get("assigned_to")) or None,
        "status": status,
        "identified_at": created[:10] or None,
        "closed_at": payload.get("closed_on"),
        "external_url": _url(base_url, payload),
    }
