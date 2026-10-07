"""LLM 모델 캐시와 활성 설정 (ARC-011).

모델 목록은 캐시다. 주소를 새로 고치면 그 주소의 행을 통째로 갈아 끼우되, 사람이 고른
num_ctx·num_predict 와 실측 속도는 같은 이름의 행에서 물려받는다. 목록을 다시 받았다고
설정이 날아가면 안 된다.

활성 설정(llm_setting)은 한 줄이다. 없으면 환경변수 기본값이 그대로 설정이다.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.ai import embedding_guard, ollama_admin
from app.ai.models import (
    EmbeddingIndexModel,
    EmbeddingStatusResponse,
    LlmMeasureResponse,
    LlmModelListResponse,
    LlmModelParamsUpdateRequest,
    LlmModelResponse,
    LlmSettingResponse,
    LlmSettingUpdateRequest,
)
from app.auth.models import AuthPrincipal
from app.common import errors
from app.config import settings
from app.db import fetch_all, fetch_one

DEFAULT_NUM_PREDICT = 16000


@dataclass(frozen=True)
class RuntimeConfig:
    """어댑터가 요청을 만들 때 쓰는 값. num_ctx 가 None 이면 옵션에 넣지 않는다."""

    base_url: str
    model: str
    num_ctx: int | None
    num_predict: int


def runtime_config(cur: Any) -> RuntimeConfig:
    """활성 설정 + 그 모델의 캐시 행. 행이 없으면 환경변수 기본값이다."""
    row = fetch_one(cur, "select base_url, model from llm_setting where id = 1")
    base_url = row["base_url"] if row else settings.ollama_base_url
    model = row["model"] if row else settings.llm_model
    cached = fetch_one(
        cur,
        "select num_ctx, num_predict from llm_model_cache where base_url = %s and name = %s",
        (base_url, model),
    )
    if cached is None:
        return RuntimeConfig(base_url, model, settings.llm_num_ctx, DEFAULT_NUM_PREDICT)
    return RuntimeConfig(base_url, model, cached["num_ctx"], cached["num_predict"])


def _require_admin(principal: AuthPrincipal) -> None:
    if principal.role != "SUPER_ADMIN":
        raise errors.ApiError(403, "FORBIDDEN", "플랫폼 관리자만 AI 모델 설정을 바꿀 수 있습니다.")


def get_setting(cur: Any, principal: AuthPrincipal) -> LlmSettingResponse:
    _require_admin(principal)
    row = fetch_one(cur, "select base_url, model, updated_at from llm_setting where id = 1")
    base_url = row["base_url"] if row else settings.ollama_base_url
    return LlmSettingResponse(
        baseUrl=base_url,
        model=row["model"] if row else settings.llm_model,
        provider=settings.llm_provider,
        requestTimeoutSeconds=settings.llm_timeout,
        updatedAt=_iso(row["updated_at"]) if row else None,
        models=[_to_response(m) for m in list_cached(cur, base_url)],
        source="DB" if row else "ENV",
        usedFor=["질문 분류", "답변 생성", "문서 초안"],
    )


ANSWER = "ANSWER"
EMBEDDING = "EMBEDDING"
UNKNOWN = "UNKNOWN"


def purpose_of(capabilities: list[str] | None) -> str:
    """서버가 알려준 용도로 판단한다. 이름으로 짐작하지 않는다. 모르면 UNKNOWN(확인 필요)."""
    if not capabilities:
        return UNKNOWN
    if "completion" in capabilities:
        return ANSWER
    if "embedding" in capabilities:
        return EMBEDDING
    return UNKNOWN


def list_cached(cur: Any, base_url: str) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        "select * from llm_model_cache where base_url = %s order by name",
        (base_url,),
    )


def refresh_models(cur: Any, principal: AuthPrincipal, base_url: str) -> LlmModelListResponse:
    """GET /api/tags 를 부르고 그 주소의 캐시를 통째로 갈아 끼운다.

    조회 실패는 예외로 올리지 않는다. 사용자가 주소를 타이핑하는 중에 불리므로 한 글자마다
    오류 대화상자가 뜨면 안 된다. 실패하면 캐시는 건드리지 않고 상태 문구만 돌려준다.
    """
    _require_admin(principal)
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        return LlmModelListResponse(baseUrl=base_url, models=[], error="서버 주소를 입력하세요.")
    try:
        discovered = ollama_admin.list_models(base_url)
    except errors.ApiError as exc:
        return LlmModelListResponse(
            baseUrl=base_url, models=[_to_response(m) for m in list_cached(cur, base_url)],
            error=exc.message,
        )
    replace_cache(cur, base_url, discovered)
    return LlmModelListResponse(
        baseUrl=base_url, models=[_to_response(m) for m in list_cached(cur, base_url)]
    )


def replace_cache(
    cur: Any, base_url: str, discovered: list[ollama_admin.DiscoveredModel]
) -> None:
    """그 주소의 행을 갈아 끼운다. 같은 이름이 남아 있으면 설정과 실측은 물려받는다."""
    kept = {
        r["name"]: r
        for r in fetch_all(
            cur,
            """
            select name, tok_per_sec, measured_at, num_ctx, num_predict, verified_at
              from llm_model_cache where base_url = %s
            """,
            (base_url,),
        )
    }
    cur.execute("delete from llm_model_cache where base_url = %s", (base_url,))
    now = datetime.now(UTC)
    for m in discovered:
        old = kept.get(m.name)
        cur.execute(
            """
            insert into llm_model_cache
              (base_url, name, context_length, supports_tools, parameter_size, quantization,
               tok_per_sec, measured_at, num_ctx, num_predict, fetched_at, updated_at,
               capabilities, verified_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                base_url, m.name, m.context_length, m.supports_tools, m.parameter_size,
                m.quantization,
                old["tok_per_sec"] if old else None,
                old["measured_at"] if old else None,
                # 처음 보는 모델은 최대 문맥을 그대로 쓴다. 0 이면 비워 모델 기본값에 맡긴다.
                old["num_ctx"] if old else (m.context_length or None),
                old["num_predict"] if old else DEFAULT_NUM_PREDICT,
                now, now,
                list(m.capabilities) if m.capabilities is not None else None,
                old["verified_at"] if old else None,
            ),
        )


def measure(cur: Any, principal: AuthPrincipal, base_url: str, model: str) -> LlmMeasureResponse:
    """생성 속도를 실측해 캐시 행에 남긴다. 화면은 이 값을 다시 읽어 보여 주기만 한다."""
    _require_admin(principal)
    base_url = base_url.strip().rstrip("/")
    if _find(cur, base_url, model) is None:
        raise errors.not_found("llm model", model)
    rate = ollama_admin.measure_rate(base_url, model)
    now = datetime.now(UTC)
    cur.execute(
        """
        update llm_model_cache
           set tok_per_sec = %s, measured_at = %s, updated_at = %s
         where base_url = %s and name = %s
        """,
        (rate.tok_per_sec, now, now, base_url, model),
    )
    return LlmMeasureResponse(
        model=model,
        tokPerSec=rate.tok_per_sec,
        evalCount=rate.eval_count,
        evalDurationSeconds=rate.eval_duration_seconds,
        measuredAt=_iso(now),
    )


def update_params(
    cur: Any, principal: AuthPrincipal, base_url: str, model: str, req: LlmModelParamsUpdateRequest
) -> LlmModelResponse:
    _require_admin(principal)
    base_url = base_url.strip().rstrip("/")
    if _find(cur, base_url, model) is None:
        raise errors.not_found("llm model", model)
    cur.execute(
        """
        update llm_model_cache set num_ctx = %s, num_predict = %s, updated_at = now()
         where base_url = %s and name = %s
        """,
        (req.numCtx, req.numPredict, base_url, model),
    )
    return _to_response(_find(cur, base_url, model))


def save_setting(
    cur: Any, principal: AuthPrincipal, req: LlmSettingUpdateRequest
) -> LlmSettingResponse:
    """활성 서버·모델을 정하고, 그 모델의 num_ctx·num_predict 를 같이 저장한다.

    캐시에 없는 모델은 고를 수 없다. 목록은 서버가 준 것만 믿는다.
    """
    _require_admin(principal)
    base_url = req.baseUrl.strip().rstrip("/")
    found = _find(cur, base_url, req.model)
    if found is None:
        raise errors.validation_failed(
            "목록에 없는 모델입니다. 서버 주소를 확인하고 목록을 새로 고치세요."
        )
    if purpose_of(found["capabilities"]) == EMBEDDING:
        raise errors.ApiError(
            400,
            "MODEL_ROLE_MISMATCH",
            f"{req.model} 은(는) 서버가 임베딩 전용으로 알려준 모델이라 "
            "답변 모델로 쓸 수 없습니다. 검색 모델은 아래 검색 모델 영역에서 봅니다.",
        )
    # 저장 전에 실제로 짧게 생성해 본다. 용도를 모르는 모델도 이 확인을 넘어야 저장된다
    try:
        rate = ollama_admin.measure_rate(base_url, req.model)
    except errors.ApiError as exc:
        raise errors.ApiError(
            400,
            "MODEL_CHECK_FAILED",
            f"{req.model} 으로 짧은 생성을 해 보지 못해 저장하지 않았습니다. {exc.message}",
        ) from exc
    now = datetime.now(UTC)
    cur.execute(
        """
        update llm_model_cache
           set tok_per_sec = %s, measured_at = %s, verified_at = %s, updated_at = %s
         where base_url = %s and name = %s
        """,
        (rate.tok_per_sec, now, now, now, base_url, req.model),
    )
    cur.execute(
        """
        update llm_model_cache set num_ctx = %s, num_predict = %s, updated_at = now()
         where base_url = %s and name = %s
        """,
        (req.numCtx, req.numPredict, base_url, req.model),
    )
    cur.execute(
        """
        insert into llm_setting (id, base_url, model, updated_by_user_id, updated_at)
        values (1, %s, %s, %s, now())
        on conflict (id) do update set
          base_url = excluded.base_url, model = excluded.model,
          updated_by_user_id = excluded.updated_by_user_id, updated_at = now()
        """,
        (base_url, req.model, principal.user_id),
    )
    return get_setting(cur, principal)


def _find(cur: Any, base_url: str, model: str) -> dict[str, Any] | None:
    return fetch_one(
        cur,
        "select * from llm_model_cache where base_url = %s and name = %s",
        (base_url, model),
    )


def _to_response(row: dict[str, Any]) -> LlmModelResponse:
    return LlmModelResponse(
        name=row["name"],
        baseUrl=row["base_url"],
        contextLength=row["context_length"],
        supportsTools=row["supports_tools"],
        parameterSize=row["parameter_size"],
        quantization=row["quantization"],
        tokPerSec=float(row["tok_per_sec"]) if row["tok_per_sec"] is not None else None,
        measuredAt=_iso(row["measured_at"]),
        numCtx=row["num_ctx"],
        numPredict=row["num_predict"],
        fetchedAt=_iso(row["fetched_at"]) or "",
        capabilities=list(row["capabilities"]) if row.get("capabilities") is not None else None,
        purpose=purpose_of(row.get("capabilities")),
        verifiedAt=_iso(row.get("verified_at")),
    )


# ---------------------------------------------------------------- 검색 모델 (ARC-022)

EMBEDDING_CHANGE_BLOCKED = (
    "검색 모델은 환경변수(AXLINK_EMBEDDING_MODEL·AXLINK_OLLAMA_BASE_URL)로 정하고 여기서 바꾸지 "
    "않습니다. 바꾸면 기존 색인과 다른 모델의 벡터가 섞이는데, 안전하게 다시 색인하는 기능이 아직 "
    "없습니다."
)


def embedding_status(cur: Any, principal: AuthPrincipal) -> EmbeddingStatusResponse:
    _require_admin(principal)
    from app.ai.embedding import embedding_port
    from app.rag import repository as rag_repo

    base_url = settings.ollama_base_url.rstrip("/")
    # 색인에 실제로 적히는 이름. 가짜 공급자면 fake 다
    model = embedding_port().model_name()
    has_model: bool | None = None
    caps: list[str] | None = None
    if settings.embedding_provider != "fake":
        try:
            listed = {m.name: m for m in ollama_admin.list_models(base_url)}
            hit = listed.get(model) or listed.get(f"{model}:latest")
            has_model = hit is not None
            caps = list(hit.capabilities) if hit and hit.capabilities is not None else None
        except errors.ApiError:
            has_model = None
    index = embedding_guard.index_models(cur)
    reason = embedding_guard.mismatch(cur, _index_name(model, index))
    return EmbeddingStatusResponse(
        provider=settings.embedding_provider,
        baseUrl=base_url,
        model=model,
        dimension=settings.embedding_dimension,
        columnDimension=rag_repo.column_dimension(cur),
        source="ENV",
        serverHasModel=has_model,
        serverCapabilities=caps,
        indexModels=[EmbeddingIndexModel(model=r["model"], chunks=int(r["chunks"])) for r in index],
        consistent=reason is None,
        message=reason,
        changeBlockedReason=EMBEDDING_CHANGE_BLOCKED,
    )


def _index_name(model: str, index: list[dict[str, Any]]) -> str:
    """색인에 남은 이름과 같은 모델을 가리키면 그 이름을 쓴다(bge-m3 와 bge-m3:latest)."""
    names = {r["model"] for r in index}
    if model in names:
        return model
    if f"{model}:latest" in names:
        return f"{model}:latest"
    return model


def reject_embedding_change(principal: AuthPrincipal) -> None:
    _require_admin(principal)
    raise errors.ApiError(409, "EMBEDDING_CHANGE_BLOCKED", EMBEDDING_CHANGE_BLOCKED)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
