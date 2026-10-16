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
    InviteCreateRequest,
    ParticipantCreateRequest,
    ParticipantResponse,
    ParticipantUpdateRequest,
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
def create_invite(
    project_id: str, principal: Principal, req: InviteCreateRequest | None = None
) -> ProjectInviteResponse:
    """초대 링크. 참여 업체를 지정하면 가입자는 그 업체로만 들어간다(GH-138)."""
    with tx() as cur:
        return service.create_invite(cur, principal, project_id, req)


@router.get("/{project_id}/participants", response_model=list[ParticipantResponse])
def list_participants(project_id: str, principal: Principal) -> list[ParticipantResponse]:
    """참여 업체. 사업에 접근할 수 있으면 누구나 본다."""
    with tx() as cur:
        return service.list_participants(cur, principal, project_id)


@router.post(
    "/{project_id}/participants", response_model=list[ParticipantResponse], status_code=201
)
def add_participant(
    project_id: str, req: ParticipantCreateRequest, principal: Principal
) -> list[ParticipantResponse]:
    """참여 업체 추가. 발주기관·관리자만."""
    with tx() as cur:
        return service.add_participant(cur, principal, project_id, req)


@router.patch(
    "/{project_id}/participants/{participant_id}", response_model=list[ParticipantResponse]
)
def update_participant(
    project_id: str, participant_id: str, req: ParticipantUpdateRequest, principal: Principal
) -> list[ParticipantResponse]:
    with tx() as cur:
        return service.update_participant(cur, principal, project_id, participant_id, req)


@router.delete(
    "/{project_id}/participants/{participant_id}", response_model=list[ParticipantResponse]
)
def remove_participant(
    project_id: str, participant_id: str, principal: Principal
) -> list[ParticipantResponse]:
    """참여 종료. 지우지 않고 종료로 남기고, 그 업체 사용자 할당을 해제한다."""
    with tx() as cur:
        return service.remove_participant(cur, principal, project_id, participant_id)
