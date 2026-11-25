"""답변 방식 설정 (ARC-034). 플랫폼 전체에 한 줄이다. 행이 없으면 지표 기반이다.

바꾸는 것은 플랫폼 관리자만, 지금 방식은 질의 화면이 알 수 있게 누구나 읽는다.
"""

from datetime import UTC, datetime
from typing import Any

from app.ai.models import AnswerModeResponse, AnswerModeUpdateRequest
from app.auth.models import AuthPrincipal
from app.common import errors
from app.db import fetch_one
from app.rag import judge


def current(cur: Any) -> str:
    row = fetch_one(cur, "select mode from answer_setting where id = 1")
    mode = row["mode"] if row else judge.STRUCTURED
    return mode if mode in judge.MODES else judge.STRUCTURED


def get(cur: Any) -> AnswerModeResponse:
    row = fetch_one(cur, "select mode, updated_at from answer_setting where id = 1")
    mode = row["mode"] if row and row["mode"] in judge.MODES else judge.STRUCTURED
    updated = row["updated_at"].astimezone(UTC).isoformat() if row else None
    return AnswerModeResponse(mode=mode, label=judge.LABELS[mode], updatedAt=updated)


def save(cur: Any, principal: AuthPrincipal, req: AnswerModeUpdateRequest) -> AnswerModeResponse:
    if principal.role != "SUPER_ADMIN":
        raise errors.ApiError(403, "FORBIDDEN", "플랫폼 관리자만 답변 방식을 바꿀 수 있습니다.")
    cur.execute(
        """
        insert into answer_setting (id, mode, updated_by_user_id, updated_at)
        values (1, %s, %s, %s)
        on conflict (id) do update set mode = excluded.mode,
          updated_by_user_id = excluded.updated_by_user_id, updated_at = excluded.updated_at
        """,
        (req.mode, principal.user_id, datetime.now(UTC)),
    )
    return get(cur)
