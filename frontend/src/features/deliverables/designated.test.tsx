import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import {
  DesignatedCell,
  DesignatedSheet,
  type DesignatedActions,
} from '@/features/deliverables/designated';
import type { DesignatedDeliverable, WbsDeliverableItem } from '@/types/api';

// 발주기관 지정 산출물(UC-033). 지정은 발주기관만, 제출본 올리기는 항목을 골라서 한다.

vi.mock('@/lib/http', () => ({ api: {}, download: vi.fn() }));

const entry: DesignatedDeliverable = {
  id: 'd1',
  taskKey: 'k1',
  wbsIdAt: '2.1',
  taskNameAt: '통합 시험',
  name: '시험결과서',
  description: null,
  productType: 'TEST_REPORT',
  guide: '결함 0건이면 통과로 적는다',
  templateFileName: '양식.xlsx',
  templateSize: 10,
  status: 'REJECTED',
  needsRedesignation: false,
  versions: [
    {
      documentId: 'doc1',
      fileName: '결과-v1.xlsx',
      uploadedAt: '2026-11-16T01:00:00Z',
      state: 'REJECTED',
      workProductId: 'w1',
      version: '1.0',
      rejectReason: '결함 목록 누락',
      decidedAt: null,
      isCurrent: true,
    },
  ],
};

const row = (designated: DesignatedDeliverable[]): WbsDeliverableItem => ({
  wbsId: '2.1',
  name: '통합 시험',
  deliverable: '시험결과서',
  endDate: null,
  status: 'MISSING',
  rule: 'DESIGNATED',
  ref: '지정 산출물 1건 중 0건 제출',
  url: null,
  productType: null,
  documents: [],
  taskKey: 'k1',
  designated,
});

const actions = (canDesignate: boolean): DesignatedActions => ({
  projectId: 'p1',
  canDesignate,
  typeNames: { TEST_REPORT: '시험 보고서' },
  onUpload: vi.fn(),
  onEdit: vi.fn(),
  onChanged: vi.fn(),
  onOpen: vi.fn(),
});

const renderCell = (item: WbsDeliverableItem, a: DesignatedActions) =>
  render(
    <ToasterProvider>
      <DesignatedCell item={item} actions={a} />
    </ToasterProvider>,
  );

describe('발주기관 지정 산출물 칸', () => {
  it('지정이 없으면 발주기관에게만 지정 버튼이 보인다', () => {
    const client = actions(true);
    renderCell(row([]), client);
    fireEvent.click(screen.getByRole('button', { name: '산출물 지정' }));
    expect(client.onEdit).toHaveBeenCalledWith({
      mode: 'create',
      taskKey: 'k1',
      taskLabel: '2.1 통합 시험',
    });
  });

  it('지정이 있으면 표 칸에는 요약만 두고 누르면 옆 창을 연다', () => {
    const contractor = actions(false);
    renderCell(row([entry]), contractor);
    expect(screen.queryByRole('button', { name: '산출물 지정' })).toBeNull();
    const summary = screen.getByRole('button', { name: /내야 할 산출물/ });
    expect(summary).toHaveTextContent('내야 할 산출물 1건');
    expect(screen.queryByText(/양식 내려받기/)).toBeNull(); // 표 칸을 넓히지 않는다
    fireEvent.click(summary);
    expect(contractor.onOpen).toHaveBeenCalledWith('2.1');
  });

  it('옆 창에서 용역사는 양식·반려 사유를 보고 그 항목으로 올린다', () => {
    const contractor = actions(false);
    render(
      <ToasterProvider>
        <DesignatedSheet item={row([entry])} actions={contractor} onClose={vi.fn()} />
      </ToasterProvider>,
    );
    expect(screen.getByText('양식 내려받기: 양식.xlsx')).toBeInTheDocument();
    expect(screen.getByText('시험 보고서')).toBeInTheDocument();
    expect(screen.getByText(/반려 사유: 결함 목록 누락/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '고치기' })).toBeNull();
    expect(screen.queryByRole('button', { name: '산출물 더 지정' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '새 버전 제출' }));
    expect(contractor.onUpload).toHaveBeenCalledWith('2.1', 'd1');
  });

  it('올렸지만 확정 전이면 미제출과 나눠 「제출 확정 대기」로 보이고 제출하러 가는 버튼이 있다', () => {
    const waiting: DesignatedDeliverable = {
      ...entry,
      status: 'REGISTERED',
      versions: [
        {
          ...entry.versions[0],
          documentId: 'doc9',
          state: 'REGISTERED',
          workProductId: null,
          version: null,
          rejectReason: null,
          submit: 'READY',
        },
      ],
    };
    const contractor = actions(false);
    render(
      <MemoryRouter>
        <ToasterProvider>
          <DesignatedCell item={row([waiting])} actions={contractor} />
          <DesignatedSheet item={row([waiting])} actions={contractor} onClose={vi.fn()} />
        </ToasterProvider>
      </MemoryRouter>,
    );
    expect(screen.getByText('제출 확정 대기 1')).toBeInTheDocument();
    expect(screen.queryByText(/미제출/)).toBeNull();
    const go = screen.getByRole('link', { name: '산출물로 제출하러 가기' });
    expect(go).toHaveAttribute('href', '/p/p1/documents/doc9/draft');
  });
});
