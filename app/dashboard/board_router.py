"""/api/dashboards · /api/widgets. 프런트 features/dashboard·widgets 가 부르는 경로 그대로다."""

from fastapi import APIRouter, Response, status

from app.auth.deps import Principal
from app.dashboard import board_service as service
from app.dashboard import generation, template_samples, widget_template
from app.dashboard.models import (
    DashboardDetailResponse,
    DashboardLayoutUpdateRequest,
    DashboardSummaryResponse,
    WidgetCreateRequest,
    WidgetDataRequest,
    WidgetGenerateRequest,
    WidgetGenerateResponse,
    WidgetPreviewRequest,
    WidgetResponse,
    WidgetTemplateExample,
    WidgetTemplateListResponse,
    WidgetTemplateResponse,
    WidgetUpdateRequest,
)
from app.db import tx
from app.semantic.models import WidgetDataResponse

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboards", response_model=list[DashboardSummaryResponse])
def list_dashboards(
    principal: Principal, projectId: str | None = None  # noqa: N803 (프런트 쿼리 이름)
) -> list[DashboardSummaryResponse]:
    with tx() as cur:
        return service.list_dashboards(cur, principal, projectId)


@router.get("/dashboards/{dashboard_id}", response_model=DashboardDetailResponse)
def get_dashboard(dashboard_id: str, principal: Principal) -> DashboardDetailResponse:
    with tx() as cur:
        return service.get_dashboard(cur, principal, dashboard_id)


@router.put("/dashboards/{dashboard_id}/layout", response_model=DashboardDetailResponse)
def replace_layout(
    dashboard_id: str, req: DashboardLayoutUpdateRequest, principal: Principal
) -> DashboardDetailResponse:
    with tx() as cur:
        return service.replace_layout(cur, principal, dashboard_id, req.layout)


@router.post(
    "/dashboards/{dashboard_id}/widgets",
    response_model=WidgetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_widget(
    dashboard_id: str, req: WidgetCreateRequest, principal: Principal
) -> WidgetResponse:
    with tx() as cur:
        return service.create_widget(cur, principal, dashboard_id, req)


@router.patch("/widgets/{widget_id}", response_model=WidgetResponse)
def update_widget(widget_id: str, req: WidgetUpdateRequest, principal: Principal) -> WidgetResponse:
    with tx() as cur:
        return service.update_widget(cur, principal, widget_id, req)


@router.delete("/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_widget(widget_id: str, principal: Principal) -> Response:
    with tx() as cur:
        service.delete_widget(cur, principal, widget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/widgets/{widget_id}/data", response_model=WidgetDataResponse)
def widget_data(
    widget_id: str, principal: Principal, req: WidgetDataRequest | None = None
) -> WidgetDataResponse:
    """위젯 값. 전부 시맨틱 레이어의 집계 결과다(절대 규칙 1)."""
    with tx() as cur:
        return service.widget_data(cur, principal, widget_id, req)


@router.post("/widgets/preview", response_model=WidgetDataResponse)
def preview(req: WidgetPreviewRequest, principal: Principal) -> WidgetDataResponse:
    with tx() as cur:
        return service.preview(cur, principal, req.spec)


@router.post("/widgets/generate", response_model=WidgetGenerateResponse)
def generate(req: WidgetGenerateRequest, principal: Principal) -> WidgetGenerateResponse:
    """자연어 → 위젯 명세. LLM 은 지표·차원·템플릿을 고르기만 하고 값은 만들지 않는다."""
    with tx() as cur:
        return generation.generate(cur, principal, req)


@router.get("/widget-templates", response_model=WidgetTemplateListResponse)
def widget_templates(principal: Principal) -> WidgetTemplateListResponse:
    """인포 템플릿 23종의 입력 계약 (ARC-012). 값이 아니라 정의라 DB 를 읽지 않는다."""
    del principal  # 로그인만 확인한다. 정의는 비밀이 아니다
    return WidgetTemplateListResponse(
        templates=[
            WidgetTemplateResponse(
                key=t.key, label=t.label, family=t.family, purpose=t.purpose, screen=t.screen,
                when=t.when, measureTypes=list(t.measure_types), dimsMin=t.dims_min,
                dimsMax=t.dims_max, timeAxis=t.time_axis, categoryMax=t.category_max,
                usesTotal=t.uses_total, usesTarget=t.uses_target, usesPrevious=t.uses_previous,
                options=list(t.options), rowCap=t.row_cap, chat=t.chat, note=t.note,
                example=WidgetTemplateExample(
                    measure=t.example_measure, dimensions=list(t.example_dimensions),
                    title=t.example_title,
                ),
                prompts=list(widget_template.prompt_examples(t.key)),
                sample=template_samples.sample_for(t),
            )
            for t in widget_template.CATALOG
        ]
    )
