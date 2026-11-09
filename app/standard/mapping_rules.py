"""연결별 매핑 규칙 (SWFR.CON.002 — 코드 수정 없이 설정으로).

업체마다 다른 것은 판별 이름들이다. 어떤 트래커가 리스크인지, REQ ID 커스텀 필드를
뭐라 부르는지, 설계 문서가 저장소 어디에 있는지. 그것만 설정으로 빼고 나머지
매핑 논리는 코드에 남긴다. 논리까지 설정으로 빼면 설정이 곧 코드가 된다.

저장처는 tool_connection.mapping_rules_json. 비어 있으면 기본값이고, 기본값은
지금까지의 하드코딩과 동일하다 — 설정 도입이 기존 연결의 동작을 바꾸지 않는다.
"""

from dataclasses import dataclass
from typing import Any

from app.common import errors
from app.config import settings
from app.standard.work_product_type import DISPLAY_NAMES

_KNOWN = {"riskTracker", "reqIdField", "designDocPaths", "collectFiles"}
# 이슈로 요구사항을 만들 때 쓰던 키(ARC-030 전). 예전 설정에 남아 있어 받기만 하고 쓰지 않는다
_RETIRED = {"requirementLabel"}


@dataclass(frozen=True)
class MappingRules:
    risk_tracker: str = "리스크"               # Redmine — 이 트래커가 risk 로 승격
    req_id_field: str = "REQ ID"               # Redmine — 도구 횡단 접착 커스텀 필드
    # 저장소 설계 문서 경로 패턴(쉼표로 나눔, ARC-024). 기본은 비어 있다. 다른 업체 저장소가
    # 우리와 같은 경로를 쓴다고 가정하지 않는다. 비어 있으면 설계 문서를 수집하지 않는다
    design_doc_paths: str = ""
    # 함께 수집할 저장소 파일과 산출물 유형(「경로=유형」, 쉼표로 나눔). WBS 위치는 업체마다
    # 다르다. 비어 있으면 서버 기본값(AXLINK_COLLECT_FILES)을 쓴다(DEF-V012)
    collect_files: str = ""

    @classmethod
    def from_json(cls, raw: Any) -> "MappingRules":
        """저장된 JSON 을 읽는다. 모르는 키는 오타다 — 조용히 무시하면 설정이
        안 먹는 채로 돌아가고, 그게 제일 찾기 어려운 버그가 된다."""
        if not raw:
            return cls()
        if not isinstance(raw, dict):
            raise errors.validation_failed("mappingRules 는 객체여야 합니다.")
        if isinstance(raw.get("rules"), list):
            # 파일럿 형식({"version":1,"rules":[]}) — V1 컬럼 기본값으로 남아 있던 행이다.
            # 규칙을 쓴 적 없다는 뜻이므로 기본값으로 읽는다(V22 가 정규화하지만 안전판).
            return cls()
        raw = {k: v for k, v in raw.items() if k not in _RETIRED}
        unknown = set(raw) - _KNOWN
        if unknown:
            allowed = ", ".join(sorted(_KNOWN))
            raise errors.validation_failed(
                f"모르는 매핑 규칙: {', '.join(sorted(unknown))} (허용: {allowed})"
            )
        cleaned = {k: v for k, v in raw.items() if isinstance(v, str) and v.strip()}
        if len(cleaned) != len(raw):
            raise errors.validation_failed("매핑 규칙 값은 비어 있지 않은 문자열이어야 합니다.")
        if "collectFiles" in cleaned:
            _parse_file_map(cleaned["collectFiles"])  # 형식·유형이 틀리면 저장 전에 거절한다
        return cls(
            risk_tracker=cleaned.get("riskTracker", cls.risk_tracker),
            req_id_field=cleaned.get("reqIdField", cls.req_id_field),
            design_doc_paths=cleaned.get("designDocPaths", cls.design_doc_paths),
            collect_files=cleaned.get("collectFiles", cls.collect_files),
        )

    @property
    def design_globs(self) -> list[str]:
        return [p.strip() for p in self.design_doc_paths.split(",") if p.strip()]

    @property
    def file_map(self) -> dict[str, str]:
        """{저장소 경로: 산출물 유형}. 연결에 없으면 서버 기본값이다."""
        if self.collect_files:
            return _parse_file_map(self.collect_files)
        return settings.collect_file_map

    def to_json(self) -> dict[str, str]:
        return {
            "riskTracker": self.risk_tracker,
            "reqIdField": self.req_id_field,
            # 비어 있으면 적지 않는다. 빈 문자열은 from_json 이 오타로 거른다
            **({"designDocPaths": self.design_doc_paths} if self.design_doc_paths else {}),
            **({"collectFiles": self.collect_files} if self.collect_files else {}),
        }


def _parse_file_map(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        path, sep, kind = item.partition("=")
        path, kind = path.strip().strip("/"), kind.strip()
        if not sep or not path or not kind:
            raise errors.validation_failed(
                f"collectFiles 는 「경로=유형」을 쉼표로 이은 값이어야 합니다: {item.strip()}"
            )
        if kind not in DISPLAY_NAMES:
            raise errors.validation_failed(
                f"collectFiles 의 산출물 유형을 모릅니다: {kind} (예: PROJECT_PLAN)"
            )
        out[path] = kind
    if not out:
        raise errors.validation_failed("collectFiles 에 경로가 없습니다.")
    return out
