import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WbsView } from '@/features/schedule/schedule-views';
import { toScheduleTasks } from '@/features/schedule/wbs-tasks';
import type { WbsItemResponse } from '@/types/api';

const item = (over: Partial<WbsItemResponse>): WbsItemResponse => ({
  wbsId: '3.2',
  name: '민원 조회 화면',
  level: 1,
  owner: '',
  deliverable: null,
  startDate: '2026-08-01',
  endDate: '2026-08-31',
  weight: 0.2,
  progress: 40,
  planned: 100,
  externalUrl: null,
  ...over,
});

describe('WbsView 연결 이슈 (AC-041-4)', () => {
  it('작업 줄에 이어진 이슈 번호와 상태를 이슈 화면과 같은 말로 보인다', () => {
    const tasks = toScheduleTasks([
      item({
        linkedIssues: [
          {
            key: 'RM-204',
            title: '조회 화면 구현',
            status: 'IN_PROGRESS',
            url: 'https://rm.example/issues/204',
          },
        ],
      }),
      item({ wbsId: '3.3', name: '민원 등록 화면', progress: 20 }),
    ]);
    render(<WbsView tasks={tasks} />);
    expect(screen.getByRole('columnheader', { name: /연결 이슈/ })).toBeInTheDocument();
    const row = screen.getByText('민원 조회 화면').closest('tr') as HTMLElement;
    const link = within(row).getByRole('link', { name: 'RM-204' });
    expect(link).toHaveAttribute('href', 'https://rm.example/issues/204');
    expect(row).toHaveTextContent('진행중');
    const other = screen.getByText('민원 등록 화면').closest('tr') as HTMLElement;
    expect(within(other).queryByRole('link')).toBeNull();
  });
});
