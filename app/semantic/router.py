"""/api/semantic/catalog. 위젯 편집 화면과 생성 프롬프트가 같은 카탈로그를 본다."""

from fastapi import APIRouter

from app.auth.deps import Principal
from app.db import tx
from app.semantic import service
from app.semantic.models import SemanticCatalogResponse

router = APIRouter(prefix="/api/semantic", tags=["semantic"])


@router.get("/catalog", response_model=SemanticCatalogResponse)
def catalog(principal: Principal) -> SemanticCatalogResponse:
    with tx() as cur:
        return service.catalog_response(cur)
