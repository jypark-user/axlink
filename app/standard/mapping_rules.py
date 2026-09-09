"""연결별 매핑 규칙 (SWFR.CON.002 — 코드 수정 없이 설정으로).

업체마다 다른 것은 판별 이름들이다 — 어떤 라벨이 요구사항인지, 어떤 트래커가
리스크인지, REQ ID 커스텀 필드를 뭐라 부르는지. 그것만 설정으로 빼고 나머지
매핑 논리는 코드에 남긴다. 논리까지 설정으로 빼면 설정이 곧 코드가 된다.

저장처는 tool_connection.mapping_rules_json. 비어 있으면 기본값이고, 기본값은
지금까지의 하드코딩과 동일하다 — 설정 도입이 기존 연결의 동작을 바꾸지 않는다.
"""

from dataclasses import dataclass
from typing import Any

from app.common import errors

_KNOWN = {"requirementLabel", "riskTracker", "reqIdField"}


@dataclass(frozen=True)
class MappingRules:
    requirement_label: str = "유형: 요구사항"  # GitHub — 이 라벨이 붙은 이슈가 요구사항
    risk_tracker: str = "리스크"               # Redmine — 이 트래커가 risk 로 승격
    req_id_field: str = "REQ ID"               # Redmine — 도구 횡단 접착 커스텀 필드

    @classmethod
    def from_json(cls, raw: Any) -> "MappingRules":
        """저장된 JSON 을 읽는다. 모르는 키는 오타다 — 조용히 무시하면 설정이
        안 먹는 채로 돌아가고, 그게 제일 찾기 어려운 버그가 된다."""
        if not raw:
            return cls()
        if not isinstance(raw, dict):
            raise errors.validation_failed("mappingRules 는 객체여야 합니다.")
        unknown = set(raw) - _KNOWN
        if unknown:
            allowed = ", ".join(sorted(_KNOWN))
            raise errors.validation_failed(
                f"모르는 매핑 규칙: {', '.join(sorted(unknown))} (허용: {allowed})"
            )
        cleaned = {k: v for k, v in raw.items() if isinstance(v, str) and v.strip()}
        if len(cleaned) != len(raw):
            raise errors.validation_failed("매핑 규칙 값은 비어 있지 않은 문자열이어야 합니다.")
        return cls(
            requirement_label=cleaned.get("requirementLabel", cls.requirement_label),
            risk_tracker=cleaned.get("riskTracker", cls.risk_tracker),
            req_id_field=cleaned.get("reqIdField", cls.req_id_field),
        )

    def to_json(self) -> dict[str, str]:
        return {
            "requirementLabel": self.requirement_label,
            "riskTracker": self.risk_tracker,
            "reqIdField": self.req_id_field,
        }
