"""/api/projects — 프런트 project-list-page.tsx 가 q·page·size 로 부른다.

등록·수정·삭제와 할당·초대도 여기다. 경로가 전부 /projects 아래라 라우터를 하나로 둔다.
"""

from fastapi import APIRouter, Query, Response

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.project import service
from app.project.models import (
    AssignmentCreateRequest,
    AssignmentResponse,
    ProjectCreateRequest,
    ProjectDeleteRequest,
    ProjectDetailResponse,
    ProjectInviteResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=PageResponse[ProjectSummaryResponse])
def list_projects(
    principal: Principal,
    q: str | None = None,
    status: str | None = None,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    sort: str | None = None,
) -> PageResponse[ProjectSummaryResponse]:
    with tx() as cur:
        return service.list_projects(
            cur, principal, status, q, PageQuery(page=page, size=size, sort=sort)
        )


@router.post("", response_model=ProjectDetailResponse, status_code=201)
def create_project(req: ProjectCreateRequest, principal: Principal) -> ProjectDetailResponse:
    with tx() as cur:
        return service.create(cur, principal, req)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: str, principal: Principal) -> ProjectDetailResponse:
    with tx() as cur:
        return service.get_detail(cur, principal, project_id)


@router.patch("/{project_id}", response_model=ProjectDetailResponse)
def update_project(
    project_id: str, req: ProjectUpdateRequest, principal: Principal
) -> ProjectDetailResponse:
    with tx() as cur:
        return service.update(cur, principal, project_id, req)


@router.delete("/{project_id}", status_code=204, response_class=Response)
def delete_project(project_id: str, req: ProjectDeleteRequest, principal: Principal) -> Response:
    with tx() as cur:
        service.delete(cur, principal, project_id, req)
    return Response(status_code=204)


@router.get("/{project_id}/assignments", response_model=list[AssignmentResponse])
def list_assignments(project_id: str, principal: Principal) -> list[AssignmentResponse]:
    with tx() as cur:
        return service.list_assignments(cur, principal, project_id)


@router.post("/{project_id}/assignments", response_model=list[AssignmentResponse], status_code=201)
def add_assignments(
    project_id: str, req: AssignmentCreateRequest, principal: Principal
) -> list[AssignmentResponse]:
    with tx() as cur:
        return service.add_assignments(cur, principal, project_id, req)


@router.delete(
    "/{project_id}/assignments/{assignment_id}", status_code=204, response_class=Response
)
def remove_assignment(project_id: str, assignment_id: str, principal: Principal) -> Response:
    with tx() as cur:
        service.remove_assignment(cur, principal, project_id, assignment_id)
    return Response(status_code=204)


@router.post("/{project_id}/invites", response_model=ProjectInviteResponse, status_code=201)
def create_invite(project_id: str, principal: Principal) -> ProjectInviteResponse:
    with tx() as cur:
        return service.create_invite(cur, principal, project_id)
