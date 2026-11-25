import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { SourceFilePanel } from '@/features/schedule/source-file-panel';
import { WbsView } from '@/features/schedule/schedule-views';
import { ScheduleWarnings } from '@/features/schedule/schedule-warnings';
import type { ScheduleTask } from '@/features/schedule/schedule-task';
import type { CompletionItem, WbsScheduleResponse } from '@/types/api';

// 일정(WBS) 수치의 원천 파일과, WBS 탭의 작업 완료 확인 칸 (11-18 사용자 지시)

const base = {
  source: 'WBS_FILE',
  sourceLabel: '용역사 WBS (docs/00-management/WBS.xlsx)',
  sourceUrl: 'https://github.com/o/r/blob/main/docs/00-management/WBS.xlsx',
  baseDate: '2026-11-18',
  planVersion: '01ee824c5bc5',
  planUpdatedAt: null,
  items: [],
  warnings: [],
  notice: null,
} as unknown as WbsScheduleResponse;

describe('수치의 원천', () => {
  it('저장소 파일이면 저장소·경로·읽은 버전과 반영 방법을 보인다', () => {
    render(
      <SourceFilePanel
        data={{
          ...base,
          sourceFile: {
            origin: 'REPOSITORY',
            path: 'docs/00-management/WBS.xlsx',
            url: 'https://github.com/o/r/blob/main/docs/00-management/WBS.xlsx',
            tool: 'GITHUB',
            repository: 'o/r',
            revision: '01ee824c5bc5bc0b3a6e',
            readAt: '2026-10-28T10:59:05Z',
            lastSyncedAt: '2026-10-28T10:59:16Z',
          },
        }}
      />,
    );
    const box = screen.getByTestId('wbs-source');
    expect(box).toHaveTextContent('GitHub 저장소 o/r');
    expect(screen.getByRole('link', { name: 'docs/00-management/WBS.xlsx' })).toHaveAttribute(
      'href',
      'https://github.com/o/r/blob/main/docs/00-management/WBS.xlsx',
    );
    expect(box).toHaveTextContent('01ee824c5bc5');
    expect(box).toHaveTextContent('저장소에 커밋하면, 다음 동기화 때');
  });

  it('Redmine 일정을 대신 쓰면 그렇다고 말한다', () => {
    render(<SourceFilePanel data={{ ...base, source: 'REDMINE', sourceFile: null }} />);
    expect(screen.getByTestId('wbs-source')).toHaveTextContent('Redmine 이슈의 시작일·종료일');
  });

  it('원천이 없으면 그리지 않는다', () => {
    const { container } = render(<SourceFilePanel data={{ ...base, source: 'NONE' }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('WBS 탭 완료 확인 칸 (UC-032 4단계)', () => {
  it('작업 번호로 이어 완료 확인 상태를 보인다', () => {
    const task = {
      id: 't1',
      code: '1.1',
      level: 1,
      name: '착수보고',
      owner: '',
      startAt: '2026-08-01',
      endAt: '2026-08-11',
      progress: 100,
      planned: 100,
      deliverable: null,
      deliverableStatus: 'NONE',
      deliverableRef: null,
      deliverableUrl: null,
      gapWarning: null,
      linkedIssues: [],
    } as ScheduleTask;
    const item = {
      taskKey: 'k1',
      wbsId: '1.1',
      name: '착수보고',
      completionStatus: 'CONFIRMED',
      confirmedBy: '김주무관',
      confirmedAt: '2026-08-12T00:00:00Z',
      weight: 0.01,
      weightAtConfirm: 0.01,
      planVersionAtConfirm: null,
      evidenceRevised: false,
      openRequestId: null,
      predecessorConfirmed: false,
    } as unknown as CompletionItem;
    render(
      <MemoryRouter>
        <WbsView tasks={[task]} completion={new Map([['1.1', item]])} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('columnheader', { name: '완료 확인' })).toBeInTheDocument();
    expect(screen.getByText(/김주무관/)).toBeInTheDocument();
  });
});

describe('일정 경고 버튼', () => {
  it('경고가 없으면 그리지 않는다', () => {
    const { container } = render(<ScheduleWarnings warnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('격차 경고 건수를 버튼에 보이고 누르면 목록을 연다', async () => {
    render(
      <ScheduleWarnings
        warnings={[
          '격차 경고: 2.3 설계 — 실적 90% 신고, 산출물 미제출',
          '가중치 합이 1이 아닙니다',
        ]}
      />,
    );
    const button = screen.getByTestId('schedule-warnings');
    expect(button).toHaveTextContent('격차 경고 1건');
    fireEvent.click(button);
    expect(await screen.findByText('2.3 설계 — 실적 90% 신고, 산출물 미제출')).toBeInTheDocument();
    expect(screen.getByText('가중치 합이 1이 아닙니다')).toBeInTheDocument();
  });
});
