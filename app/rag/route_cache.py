"""라우팅 캐시 (ARC-014). 같은 질문의 판정을 모델에 다시 묻지 않는다.

한 답변에서 모델을 두 번 부른다. 먼저 판정(어떤 지표·차원·템플릿·목록인가), 그다음 본문이다.
판정은 값이 아니라 "무엇을 셀지" 라서 데이터가 바뀌어도 그대로 유효하다. 그래서 판정만
캐시한다. 값은 매번 시맨틱 레이어와 표준 모델에서 새로 뽑는다(절대 규칙 1).

키는 정규화한 질문과 카탈로그 버전이다. 문장의 유사도로 맞추지 않는다. 조건 하나가 다른
질문("열린 이슈" 와 "닫힌 이슈")에 같은 판정이 나가는 길이기 때문이다. 정확히 같은
문자열만 맞춘다.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from app.ai.port import LlmPort
from app.config import settings
from app.dashboard import generation
from app.db import fetch_one
from app.rag import routing
from app.semantic.catalog import Catalog

_TRAILING = re.compile(r"[\s\.\?\!。？！]+$")


def normalize(question: str) -> str:
    """공백을 하나로, 앞뒤 공백과 끝 문장 부호를 뗀다. 그 밖에는 손대지 않는다."""
    return _TRAILING.sub("", " ".join(question.split())).strip()


def catalog_version(catalog: Catalog) -> str:
    """판정은 시스템 프롬프트에 달려 있다. 그 문장 전체의 해시가 버전이다. 지표·차원·템플릿
    안내 중 무엇이 바뀌어도 버전이 바뀐다."""
    return hashlib.sha256(routing.system_prompt(catalog).encode("utf-8")).hexdigest()


def key_of(question: str, version: str) -> str:
    return hashlib.sha256(f"{version}\x1f{normalize(question)}".encode()).hexdigest()


@dataclass
class Routed:
    decision: routing.RouteDecision
    cached: bool
    # 아직 저장하지 않은 새 판정. 답을 만든 뒤 remember() 로 넣는다
    key: str | None = None
    version: str | None = None
    choice: dict[str, Any] | None = None
    model: str = ""


def decide(cur: Any, catalog: Catalog, llm: LlmPort, question: str) -> Routed:
    """캐시에 있으면 그 판정을 다시 검증해 쓰고, 없으면 모델에 묻는다.

    새 판정은 여기서 저장하지 않는다. 답을 실제로 만들었을 때만 remember() 가 넣는다.
    문서 경로로 보냈는데 근거가 없어 답을 못 만든 판정은 틀렸을 가능성이 높다("가장 급한
    작업" 을 문서 검색으로 보낸 경우). 그것을 저장하면 같은 질문이 계속 막힌다.

    저장은 모델의 JSON 원본이다. 읽을 때 from_choice 가 카탈로그로 다시 검증하므로 지표가
    폐기되면 그 판정은 문서 경로로 내려간다. 읽을 수 없는 답(파싱 실패)은 저장하지 않는다.
    """
    if not settings.rag_route_cache:
        return Routed(routing.decide(catalog, llm, question), cached=False)

    version = catalog_version(catalog)
    key = key_of(question, version)
    row = fetch_one(cur, "select choice_json from route_cache where key_hash = %s", (key,))
    if row is not None:
        cur.execute(
            "update route_cache set hit_count = hit_count + 1, last_hit_at = now() "
            "where key_hash = %s",
            (key,),
        )
        return Routed(routing.from_choice(catalog, row["choice_json"]), cached=True)

    result = llm.complete(
        routing.system_prompt(catalog), question, json_schema=routing.CHOICE_SCHEMA
    )
    choice = generation.parse_choice(result.text)
    return Routed(
        routing.from_choice(catalog, choice),
        cached=False,
        key=key,
        version=version,
        choice=choice,
        model=result.model,
    )


def remember(cur: Any, question: str, routed: Routed) -> bool:
    """답을 만든 판정을 저장한다. 캐시에서 온 것이거나 읽을 수 없던 답이면 아무것도 안 한다."""
    if routed.cached or routed.choice is None or routed.key is None or routed.version is None:
        return False
    cur.execute(
        """
        insert into route_cache (key_hash, question, catalog_version, choice_json, model)
        values (%s, %s, %s, %s, %s)
        on conflict (key_hash) do nothing
        """,
        (routed.key, normalize(question), routed.version, Jsonb(routed.choice), routed.model),
    )
    return True


def clear(cur: Any) -> int:
    """관리자가 비운다. 카탈로그 버전이 바뀌면 자연히 안 맞지만, 프롬프트만 손봤을 때도
    버전이 바뀌므로 대개 손댈 일이 없다."""
    cur.execute("delete from route_cache")
    return cur.rowcount
