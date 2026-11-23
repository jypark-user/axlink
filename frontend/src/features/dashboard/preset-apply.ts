import { api } from '@/lib/http';
import {
  packGrid,
  toWidgetSpec,
  type DashboardPreset,
} from '@/features/dashboard/dashboard-presets';
import type { WidgetResponse } from '@/types/api';

/** 지금 놓인 위젯을 모두 치운다. 「전체 삭제」와 구성 바꾸기가 함께 쓴다. */
export async function clearWidgets(widgets: WidgetResponse[]): Promise<void> {
  for (const widget of widgets) {
    await api.del<void>(`/widgets/${widget.id}`);
  }
}

/**
 * 지금 놓인 위젯을 치우고 구성 하나를 놓는다. 「초기화」(기본 구성)·추천 구성·빈 화면의 「기본 구성
 * 놓기」가 같은 길을 쓴다. 위젯마다 서버가 카탈로그로 검증해 저장한다.
 */
export async function applyPreset(
  dashboardId: string,
  projectId: string,
  current: WidgetResponse[],
  preset: DashboardPreset,
): Promise<void> {
  await clearWidgets(current);
  const grid = packGrid(preset.widgets, 0);
  for (const [i, widget] of preset.widgets.entries()) {
    await api.post(`/dashboards/${dashboardId}/widgets`, {
      spec: toWidgetSpec(widget, projectId),
      gridItem: grid[i],
    });
  }
}
