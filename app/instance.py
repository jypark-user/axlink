"""이 실행 환경의 이름표. 로그인 전에도 보인다.

같은 코드가 발주기관 공개 환경(5173)과 내부 개발·검증 환경(5174)에서 돈다. 개발 환경은 공개 데이터의
사본을 쓰므로 화면만 보고 둘을 헷갈리면 안 된다. AXLINK_INSTANCE_LABEL 이 있으면 화면 맨 위
띠로 보인다.
공개 환경에서는 비워 둔다.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api", tags=["instance"])


class InstanceResponse(BaseModel):
    label: str | None


@router.get("/instance", response_model=InstanceResponse)
def instance() -> InstanceResponse:
    return InstanceResponse(label=settings.instance_label or None)
