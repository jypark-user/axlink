"""/api — 커넥터 등록·테스트. 프런트 connections-page.tsx 가 부르는 경로 그대로다.

경로가 /projects/{id}/connections 와 /connections/{id} 두 갈래라 라우터를 하나로 둔다.
"""

from fastapi import APIRouter, Query, Response

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.integration import service
from app.integration.models import (
    SyncJobResponse,
    ToolConnectionCreateRequest,
    ToolConnectionResponse,
    ToolConnectionStatusUpdateRequest,
    ToolConnectionTestRequest,
    ToolConnectionTestResponse,
)

router = APIRouter(prefix="/api", tags=["connections"])


@router.get("/projects/{project_id}/connections", response_model=list[ToolConnectionResponse])
def list_connections(project_id: str, principal: Principal) -> list[ToolConnectionResponse]:
    with tx() as cur:
        return service.list_for_project(cur, principal, project_id)


@router.post(
    "/projects/{project_id}/connections", response_model=ToolConnectionResponse, status_code=201
)
def create_connection(
    project_id: str, req: ToolConnectionCreateRequest, principal: Principal
) -> ToolConnectionResponse:
    with tx() as cur:
        return service.create(cur, principal, project_id, req)


@router.post("/connections/test", response_model=ToolConnectionTestResponse)
def test_unsaved(
    req: ToolConnectionTestRequest, principal: Principal
) -> ToolConnectionTestResponse:
    with tx() as cur:
        return service.test_unsaved(
            cur, principal, req.tool, req.baseUrl, req.targetResource, req.credential.accessToken
        )


@router.post("/connections/{connection_id}/test", response_model=ToolConnectionTestResponse)
def test_saved(connection_id: str, principal: Principal) -> ToolConnectionTestResponse:
    with tx() as cur:
        return service.test_saved(cur, principal, connection_id)


@router.patch("/connections/{connection_id}/status", response_model=ToolConnectionResponse)
def update_status(
    connection_id: str, req: ToolConnectionStatusUpdateRequest, principal: Principal
) -> ToolConnectionResponse:
    with tx() as cur:
        return service.change_status(cur, principal, connection_id, req.status)


@router.delete("/connections/{connection_id}", status_code=204, response_class=Response)
def delete_connection(connection_id: str, principal: Principal) -> Response:
    with tx() as cur:
        service.delete(cur, principal, connection_id)
    return Response(status_code=204)


@router.post("/connections/{connection_id}/sync", response_model=SyncJobResponse, status_code=202)
def trigger_sync(connection_id: str, principal: Principal) -> SyncJobResponse:
    with tx() as cur:
        return service.trigger_sync(cur, principal, connection_id)


@router.get("/sync-jobs", response_model=PageResponse[SyncJobResponse])
def list_sync_jobs(
    principal: Principal,
    projectId: str,  # noqa: N803 — 프런트 쿼리 파라미터명
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> PageResponse[SyncJobResponse]:
    with tx() as cur:
        return service.list_jobs(cur, principal, projectId, PageQuery(page=page, size=size))
