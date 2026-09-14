"""대시보드·위젯 서비스 (SWFR.WEB.001).

위젯은 코드가 아니라 데이터다. 여기서 하는 일은 명세를 카탈로그로 검증해 저장하고,
레이아웃을 서버에 두고, 데이터는 시맨틱 레이어에 넘기는 것뿐이다.
"""

from typing import Any

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.dashboard import board_repository as repo
from app.dashboard.models import (
    DashboardDetailResponse,
    DashboardLayout,
    DashboardSummaryResponse,
    GridItem,
    WidgetCreateRequest,
    WidgetDataRequest,
    WidgetResponse,
    WidgetUpdateRequest,
)
from app.semantic import builder
from app.semantic import catalog as catalog_module
from app.semantic import service as semantic
from app.semantic.models import WidgetDataResponse, WidgetSpec

DEFAULT_DASHBOARD_NAME = "사업 현황"


def role_forbidden() -> errors.ApiError:
    return errors.ApiError(403, "ROLE_FORBIDDEN", "이 대시보드를 고칠 권한이 없습니다.")


# ---------------------------------------------------------------- 대시보드


def list_dashboards(
    cur: Any, principal: AuthPrincipal, project_id: str | None
) -> list[DashboardSummaryResponse]:
    allowed = _allowed(cur, principal)
    if project_id is not None:
        if project_id not in allowed:
            raise errors.project_access_denied()
        _ensure_default(cur, principal, project_id)
    rows = repo.list_dashboards(cur, principal.user_id, project_id, allowed)
    return [
        DashboardSummaryResponse(
            id=str(r["id"]),
            name=r["name"],
            projectId=_opt(r["project_id"]),
            projectName=r["project_name"],
            isDefault=r["is_default"],
            widgetCount=int(r["widget_count"]),
            editable=_editable(r, principal, allowed),
            updatedAt=r["updated_at"].isoformat(),
        )
        for r in rows
    ]


def get_dashboard(cur: Any, principal: AuthPrincipal, dashboard_id: str) -> DashboardDetailResponse:
    row = _load(cur, principal, dashboard_id)
    return _detail(cur, row, principal)


def replace_layout(
    cur: Any, principal: AuthPrincipal, dashboard_id: str, layout: DashboardLayout
) -> DashboardDetailResponse:
    row = _load(cur, principal, dashboard_id)
    _require_editable(row, principal, _allowed(cur, principal))
    widget_ids = {str(w["id"]) for w in repo.list_widgets(cur, dashboard_id)}
    for item in layout.lg:
        if item.i not in widget_ids:
            raise errors.validation_failed(f"레이아웃이 존재하지 않는 위젯을 참조합니다: {item.i}")
    repo.update_layout(cur, dashboard_id, _layout_json(layout))
    return _detail(cur, repo.find_dashboard(cur, dashboard_id), principal)


# ---------------------------------------------------------------- 위젯


def create_widget(
    cur: Any, principal: AuthPrincipal, dashboard_id: str, req: WidgetCreateRequest
) -> WidgetResponse:
    row = _load(cur, principal, dashboard_id)
    allowed = _allowed(cur, principal)
    _require_editable(row, principal, allowed)
    spec = _validated_spec(cur, req.spec, allowed)
    widget_id = repo.create_widget(
        cur, dashboard_id, spec.template, spec.title, spec.model_dump(), principal.user_id
    )
    if req.gridItem is not None:
        _append_layout_item(cur, row, req.gridItem, widget_id)
    return _widget(repo.find_widget(cur, widget_id))


def update_widget(
    cur: Any, principal: AuthPrincipal, widget_id: str, req: WidgetUpdateRequest
) -> WidgetResponse:
    widget = repo.find_widget(cur, widget_id)
    if widget is None:
        raise errors.not_found("widget", widget_id)
    row = _load(cur, principal, str(widget["dashboard_id"]))
    allowed = _allowed(cur, principal)
    _require_editable(row, principal, allowed)
    spec = _validated_spec(cur, req.spec, allowed)
    repo.update_widget(cur, widget_id, spec.template, spec.title, spec.model_dump())
    return _widget(repo.find_widget(cur, widget_id))


def delete_widget(cur: Any, principal: AuthPrincipal, widget_id: str) -> None:
    widget = repo.find_widget(cur, widget_id)
    if widget is None:
        raise errors.not_found("widget", widget_id)
    row = _load(cur, principal, str(widget["dashboard_id"]))
    _require_editable(row, principal, _allowed(cur, principal))
    repo.soft_delete_widget(cur, widget_id)
    # 지운 위젯의 자리도 뺀다. 남기면 빈 구멍이 생기고 다음 저장 때 다시 굳는다.
    layout = _layout(row)
    repo.update_layout(
        cur,
        str(row["id"]),
        _layout_json(
            DashboardLayout(
                lg=[g for g in layout.lg if g.i != widget_id],
                md=[g for g in layout.md if g.i != widget_id],
                sm=[g for g in layout.sm if g.i != widget_id],
            )
        ),
    )


def widget_data(
    cur: Any, principal: AuthPrincipal, widget_id: str, req: WidgetDataRequest | None
) -> WidgetDataResponse:
    widget = repo.find_widget(cur, widget_id)
    if widget is None:
        raise errors.not_found("widget", widget_id)
    _load(cur, principal, str(widget["dashboard_id"]))  # 열람 권한
    spec = WidgetSpec.model_validate(widget["spec_json"])
    return semantic.run(
        cur,
        principal,
        spec,
        None if req is None else req.projectScopeOverride,
        None if req is None else req.periodOverride,
    )


def preview(cur: Any, principal: AuthPrincipal, spec: WidgetSpec) -> WidgetDataResponse:
    return semantic.run(cur, principal, spec)


# ---------------------------------------------------------------- 내부


def _allowed(cur: Any, principal: AuthPrincipal) -> list[str]:
    return auth_repo.allowed_project_ids(cur, principal.role, principal.org_id, principal.user_id)


def _load(cur: Any, principal: AuthPrincipal, dashboard_id: str) -> dict[str, Any]:
    """열람 가능한 대시보드 행. 사업 대시보드는 사업 접근으로, 개인 대시보드는 소유로 판단한다."""
    row = repo.find_dashboard(cur, dashboard_id)
    if row is None:
        raise errors.not_found("dashboard", dashboard_id)
    if str(row["owner_user_id"]) == principal.user_id:
        return row
    if row["project_id"] is None or str(row["project_id"]) not in _allowed(cur, principal):
        raise errors.project_access_denied()
    return row


def _editable(row: dict[str, Any], principal: AuthPrincipal, allowed: list[str]) -> bool:
    """사업 기본 대시보드는 그 사업의 발주기관 담당자와 관리자가 함께 고친다.
    개인 대시보드는 만든 사람만. 용역사는 보기만 한다(QUR.WEB.001 의 역방향 보호)."""
    if str(row["owner_user_id"]) == principal.user_id:
        return True
    if not row["is_default"] or row["project_id"] is None:
        return False
    return principal.role in ("CLIENT", "SUPER_ADMIN") and str(row["project_id"]) in allowed


def _require_editable(row: dict[str, Any], principal: AuthPrincipal, allowed: list[str]) -> None:
    if not _editable(row, principal, allowed):
        raise role_forbidden()


def _ensure_default(cur: Any, principal: AuthPrincipal, project_id: str) -> None:
    """사업에 기본 대시보드가 없으면 하나 만든다. 시드 사업 말고는 만들어 주는 경로가 없어서
    화면이 빈 채로 멈춘다. 발주기관 담당자·관리자가 처음 열 때 생긴다."""
    if principal.role not in ("CLIENT", "SUPER_ADMIN"):
        return
    if repo.list_dashboards(cur, principal.user_id, project_id, [project_id]):
        return
    repo.create_dashboard(cur, project_id, principal.user_id, DEFAULT_DASHBOARD_NAME, True)


def _validated_spec(cur: Any, spec: WidgetSpec, allowed: list[str]) -> WidgetSpec:
    """저장 전에 카탈로그로 검증한다. 없는 지표를 담은 위젯이 저장되면 볼 때마다 깨진다."""
    validated = builder.validate(catalog_module.load(cur), spec, allowed)
    return spec.model_copy(update={"title": validated.title})


def _append_layout_item(cur: Any, row: dict[str, Any], item: GridItem, widget_id: str) -> None:
    layout = _layout(row)
    placed = item.model_copy(update={"i": widget_id})
    repo.update_layout(
        cur,
        str(row["id"]),
        _layout_json(DashboardLayout(lg=[*layout.lg, placed], md=layout.md, sm=layout.sm)),
    )


def _layout(row: dict[str, Any]) -> DashboardLayout:
    raw = row["layout_json"] or {}
    return DashboardLayout(lg=raw.get("lg") or [], md=raw.get("md") or [], sm=raw.get("sm") or [])


def _layout_json(layout: DashboardLayout) -> dict[str, Any]:
    return {"version": 1, **layout.model_dump()}


def _detail(cur: Any, row: dict[str, Any], principal: AuthPrincipal) -> DashboardDetailResponse:
    return DashboardDetailResponse(
        id=str(row["id"]),
        name=row["name"],
        projectId=_opt(row["project_id"]),
        projectName=row["project_name"],
        isDefault=row["is_default"],
        editable=_editable(row, principal, _allowed(cur, principal)),
        layout=_layout(row),
        widgets=[_widget(w) for w in repo.list_widgets(cur, str(row["id"]))],
        updatedAt=row["updated_at"].isoformat(),
    )


def _widget(row: dict[str, Any]) -> WidgetResponse:
    return WidgetResponse(
        id=str(row["id"]),
        dashboardId=str(row["dashboard_id"]),
        template=row["template"],
        title=row["title"],
        spec=WidgetSpec.model_validate(row["spec_json"]),
        createdAt=row["created_at"].isoformat(),
        updatedAt=row["updated_at"].isoformat(),
    )


def _opt(value: Any) -> str | None:
    return None if value is None else str(value)
