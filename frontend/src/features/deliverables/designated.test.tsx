import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import { DesignatedCell, type DesignatedActions } from '@/features/deliverables/designated';
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

  it('용역사는 지정 버튼 없이 항목·양식·반려 사유를 보고 그 항목으로 올린다', () => {
    const contractor = actions(false);
    const { container } = renderCell(row([entry]), contractor);
    expect(screen.queryByRole('button', { name: '산출물 지정' })).toBeNull();
    expect(container.querySelector('summary')).toHaveTextContent('내야 할 산출물 1건');
    container.querySelector('details')?.setAttribute('open', '');
    expect(screen.getByText('양식 내려받기: 양식.xlsx')).toBeInTheDocument();
    expect(screen.getByText('시험 보고서')).toBeInTheDocument();
    expect(screen.getByText(/반려 사유: 결함 목록 누락/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '고치기' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '새 버전 제출' }));
    expect(contractor.onUpload).toHaveBeenCalledWith('2.1', 'd1');
  });
});
