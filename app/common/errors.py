"""오류 응답 봉투. 프런트 types/api.ts 의 ErrorResponse 와 필드가 일치해야 한다.

    { code, message, details, path, timestamp }

프런트 lib/api-error.ts 가 code 로 분기하므로 코드 문자열은 계약이다.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_DEFAULT_MESSAGES = {
    "CREDENTIALS_INVALID": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "TOKEN_INVALID": "인증 정보가 유효하지 않습니다.",
    "UNAUTHORIZED": "로그인이 필요합니다.",
    "PROJECT_ACCESS_DENIED": "해당 사업에 접근할 수 없습니다.",
    "NOT_FOUND": "대상을 찾을 수 없습니다.",
    "VALIDATION_FAILED": "요청 값이 올바르지 않습니다.",
    "INTERNAL": "서버 오류가 발생했습니다.",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message or _DEFAULT_MESSAGES.get(code, code)
        self.details = details
        super().__init__(self.message)


def credentials_invalid() -> ApiError:
    return ApiError(401, "CREDENTIALS_INVALID")


def token_invalid() -> ApiError:
    return ApiError(401, "TOKEN_INVALID")


def unauthorized() -> ApiError:
    return ApiError(401, "UNAUTHORIZED")


def project_access_denied() -> ApiError:
    return ApiError(403, "PROJECT_ACCESS_DENIED")


def not_found(what: str, key: Any) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} 을(를) 찾을 수 없습니다: {key}")


def validation_failed(message: str) -> ApiError:
    return ApiError(400, "VALIDATION_FAILED", message)


def _envelope(
    code: str, message: str, details: dict[str, Any] | None, path: str
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details,
        "path": path,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=_envelope(exc.code, exc.message, exc.details, request.url.path),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = [
        {"field": ".".join(str(p) for p in err.get("loc", ())[1:]), "reason": err.get("msg", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content=_envelope(
            "VALIDATION_FAILED",
            _DEFAULT_MESSAGES["VALIDATION_FAILED"],
            {"fields": fields},
            request.url.path,
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_envelope("INTERNAL", _DEFAULT_MESSAGES["INTERNAL"], None, request.url.path),
    )
