"""/api/projects/{id}/requirement-baseline — 요구사항 기준선 (GH-139, ARC-028).

용역사: 명세서 등록(POST) → 항목 정리 → 제출. 발주기관: 반려 또는 확정.
"""

from fastapi import APIRouter, Response

from app.auth.deps import Principal
from app.db import tx
from app.standard import baseline
from app.standard.models import (
    BaselineConfirmRequest,
    BaselineCreateRequest,
    BaselineItemRequest,
    BaselineResponse,
    BaselineReturnRequest,
    BaselineStateResponse,
    UnresolvedRefResponse,
)

router = APIRouter(prefix="/api/projects", tags=["requirement-baseline"])
_BASE = "/{project_id}/requirement-baseline"


@router.get(_BASE, response_model=BaselineStateResponse)
def state(project_id: str, principal: Principal) -> BaselineStateResponse:
    """기준선 상태. 미등록이면 state=NONE 이다. 요구사항 화면 머리가 이것을 읽는다."""
    with tx() as cur:
        return baseline.state(cur, principal, project_id)


@router.post(_BASE, response_model=BaselineResponse, status_code=201)
def create(project_id: str, body: BaselineCreateRequest, principal: Principal) -> BaselineResponse:
    """올려 둔 명세서 문서에서 항목을 뽑아 작성 중 기준선을 만든다."""
    with tx() as cur:
        return baseline.create(cur, principal, project_id, body.documentId)


@router.get(_BASE + "/{baseline_id}", response_model=BaselineResponse)
def detail(project_id: str, baseline_id: str, principal: Principal) -> BaselineResponse:
    with tx() as cur:
        return baseline.detail(cur, principal, project_id, baseline_id)


@router.delete(_BASE + "/{baseline_id}", status_code=204)
def discard(project_id: str, baseline_id: str, principal: Principal) -> Response:
    with tx() as cur:
        baseline.discard(cur, principal, project_id, baseline_id)
    return Response(status_code=204)


@router.post(_BASE + "/{baseline_id}/items", response_model=BaselineResponse)
def add_item(
    project_id: str, baseline_id: str, body: BaselineItemRequest, principal: Principal
) -> BaselineResponse:
    with tx() as cur:
        return baseline.add_item(cur, principal, project_id, baseline_id, body)


@router.put(_BASE + "/{baseline_id}/items/{item_id}", response_model=BaselineResponse)
def update_item(
    project_id: str,
    baseline_id: str,
    item_id: str,
    body: BaselineItemRequest,
    principal: Principal,
) -> BaselineResponse:
    with tx() as cur:
        return baseline.update_item(cur, principal, project_id, baseline_id, item_id, body)


@router.delete(_BASE + "/{baseline_id}/items/{item_id}", response_model=BaselineResponse)
def delete_item(
    project_id: str, baseline_id: str, item_id: str, principal: Principal
) -> BaselineResponse:
    with tx() as cur:
        return baseline.delete_item(cur, principal, project_id, baseline_id, item_id)


@router.post(_BASE + "/{baseline_id}/submit", response_model=BaselineResponse)
def submit(project_id: str, baseline_id: str, principal: Principal) -> BaselineResponse:
    with tx() as cur:
        return baseline.submit(cur, principal, project_id, baseline_id)


@router.post(_BASE + "/{baseline_id}/return", response_model=BaselineResponse)
def return_to_author(
    project_id: str, baseline_id: str, body: BaselineReturnRequest, principal: Principal
) -> BaselineResponse:
    with tx() as cur:
        return baseline.return_to_author(cur, principal, project_id, baseline_id, body.reason)


@router.post(_BASE + "/{baseline_id}/confirm", response_model=BaselineResponse)
def confirm(
    project_id: str, baseline_id: str, body: BaselineConfirmRequest, principal: Principal
) -> BaselineResponse:
    """확정은 요청 하나가 트랜잭션 하나다. 중간에 실패하면 아무것도 바뀌지 않는다."""
    with tx() as cur:
        return baseline.confirm(cur, principal, project_id, baseline_id, body.applySpecCodes)


@router.get(
    "/{project_id}/requirements/unresolved-refs", response_model=list[UnresolvedRefResponse]
)
def unresolved_refs(project_id: str, principal: Principal) -> list[UnresolvedRefResponse]:
    """사업에 없는 요구사항 코드를 가리킨 커밋·이슈. 잇지 않고 보이기만 한다."""
    with tx() as cur:
        return baseline.unresolved_refs(cur, principal, project_id)
