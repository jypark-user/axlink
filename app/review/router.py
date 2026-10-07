"""/api — 확인 요청·조치 보고. 프런트 features/review-requests 가 부르는 경로 그대로다.

경로가 /projects/{id}/review-requests 와 /review-requests/{id} 두 갈래라 라우터를 하나로 둔다.
"""

from fastapi import APIRouter, Query

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.review import service
from app.review.models import (
    CompletionWithdrawRequest,
    ReviewBodyRequest,
    ReviewConfirmRequest,
    ReviewRequestCreateRequest,
    ReviewRequestDetailResponse,
    ReviewRequestResponse,
    ReviewTargetOption,
)

router = APIRouter(prefix="/api", tags=["review-requests"])


@router.get("/projects/{project_id}/review-targets", response_model=list[ReviewTargetOption])
def list_targets(project_id: str, principal: Principal, type: str) -> list[ReviewTargetOption]:  # noqa: A002 — 프런트 쿼리 파라미터명
    with tx() as cur:
        return service.list_targets(cur, principal, project_id, type)


@router.get(
    "/projects/{project_id}/review-requests", response_model=PageResponse[ReviewRequestResponse]
)
def list_requests(
    project_id: str,
    principal: Principal,
    status: str | None = None,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResponse[ReviewRequestResponse]:
    with tx() as cur:
        return service.list_requests(
            cur, principal, project_id, status, PageQuery(page=page, size=size)
        )


@router.post(
    "/projects/{project_id}/review-requests", response_model=ReviewRequestResponse, status_code=201
)
def create_request(
    project_id: str, req: ReviewRequestCreateRequest, principal: Principal
) -> ReviewRequestResponse:
    with tx() as cur:
        return service.create(cur, principal, project_id, req)


@router.get("/review-requests/{request_id}", response_model=ReviewRequestDetailResponse)
def get_request(request_id: str, principal: Principal) -> ReviewRequestDetailResponse:
    with tx() as cur:
        return service.get_detail(cur, principal, request_id)


@router.post("/review-requests/{request_id}/report", response_model=ReviewRequestDetailResponse)
def report(
    request_id: str, req: ReviewBodyRequest, principal: Principal
) -> ReviewRequestDetailResponse:
    with tx() as cur:
        return service.report(cur, principal, request_id, req)


@router.post("/review-requests/{request_id}/confirm", response_model=ReviewRequestDetailResponse)
def confirm(
    request_id: str, principal: Principal, req: ReviewConfirmRequest | None = None
) -> ReviewRequestDetailResponse:
    """확인완료. 작업 완료 확인 요청이면 같은 트랜잭션에서 완료 확인 기록을 남긴다."""
    with tx() as cur:
        return service.confirm(cur, principal, request_id, req or ReviewConfirmRequest())


@router.post(
    "/review-requests/{request_id}/withdraw-completion",
    response_model=ReviewRequestDetailResponse,
)
def withdraw_completion(
    request_id: str, req: CompletionWithdrawRequest, principal: Principal
) -> ReviewRequestDetailResponse:
    """완료 확인 철회. 기록을 지우지 않고 철회 한 줄을 더한다."""
    with tx() as cur:
        return service.withdraw_completion(cur, principal, request_id, req)


@router.post("/review-requests/{request_id}/rerequest", response_model=ReviewRequestDetailResponse)
def rerequest(
    request_id: str, req: ReviewBodyRequest, principal: Principal
) -> ReviewRequestDetailResponse:
    with tx() as cur:
        return service.rerequest(cur, principal, request_id, req)
