import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WidgetHost } from '@/features/widgets/widget-host';
import type { WidgetDataResponse, WidgetResponse, WidgetSpec } from '@/types/api';

// 지표마다 산출 근거가 붙어야 한다 (QUR.WEB.002). 값은 서버 응답의 문장 그대로 보이고
// 화면이 지어내지 않는다. 근거가 없는 응답이면 버튼도 없다.

const BASIS = '해결·종료되지 않은 일반 이슈 수다. 도구에서 닫으면 다음 수집 때 줄어든다.';

const data = (basis: string | null): WidgetDataResponse => ({
  measure: 'open_issue_count',
  measureLabel: '미해결 이슈 수',
  unit: '건',
  dimensions: [],
  columns: [{ key: 'value', label: '값', type: 'number' }],
  rows: [{ values: { value: 7 } }],
  total: { values: { value: 7 } },
  previousTotal: null,
  target: null,
  appliedProjectIds: ['p1'],
  truncated: false,
  generatedAt: '2026-11-03T00:00:00Z',
  basis,
});

let response: WidgetDataResponse = data(BASIS);
vi.mock('@/lib/http', () => ({
  api: { post: () => Promise.resolve(response) },
}));

const widget: WidgetResponse = {
  id: 'w1',
  dashboardId: 'd1',
  template: 'STAT_CARD',
  title: '미해결 이슈',
  spec: {
    template: 'STAT_CARD',
    title: '미해결 이슈',
    query: null,
    options: null,
  } as unknown as WidgetSpec,
  createdAt: '2026-11-03T00:00:00Z',
  updatedAt: '2026-11-03T00:00:00Z',
};

describe('위젯 산출 근거', () => {
  it('근거 버튼을 누르면 서버가 준 문장이 그대로 보인다', async () => {
    response = data(BASIS);
    render(<WidgetHost widget={widget} editing={false} />);
    const button = await screen.findByRole('button', { name: '산출 근거' });
    expect(screen.queryByTestId('widget-basis')).toBeNull();
    fireEvent.click(button);
    expect(screen.getByTestId('widget-basis').textContent).toBe(BASIS);
  });

  it('근거가 없는 응답이면 버튼을 그리지 않는다', async () => {
    response = data(null);
    render(<WidgetHost widget={widget} editing={false} />);
    await waitFor(() => expect(screen.getByText(/미해결 이슈 수/)).toBeTruthy());
    expect(screen.queryByRole('button', { name: '산출 근거' })).toBeNull();
  });
});
