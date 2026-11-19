import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import {
  DesignatedCell,
  DesignatedSheet,
  UploadDialog,
  type DesignatedActions,
} from '@/features/deliverables/designated';
import type { DesignatedDeliverable, WbsDeliverableItem } from '@/types/api';

// 산출물 양식(UC-033). 양식 등록·수정은 발주기관만, 제출은 [올리기] 창에서만 한다(11-18).

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
  onUploadRepo: vi.fn(),
  hasRepo: false,
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

describe('산출물 양식 칸', () => {
  it('양식이 없으면 발주기관에게만 [등록]이 보인다', () => {
    const client = actions(true);
    renderCell(row([]), client);
    fireEvent.click(screen.getByRole('button', { name: '양식 등록' }));
    expect(client.onEdit).toHaveBeenCalledWith({
      mode: 'create',
      taskKey: 'k1',
      taskLabel: '2.1 통합 시험',
    });
  });

  it('용역사에게는 양식이 없으면 「-」다', () => {
    renderCell(row([]), actions(false));
    expect(screen.queryByRole('button', { name: '양식 등록' })).toBeNull();
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('양식이 있으면 건수만 두고 누르면 옆 창을 연다', () => {
    const client = actions(true);
    renderCell(row([entry]), client);
    const count = screen.getByRole('button', { name: '1건' });
    expect(screen.queryByText(/양식 내려받기/)).toBeNull(); // 표 칸을 넓히지 않는다
    fireEvent.click(count);
    expect(client.onOpen).toHaveBeenCalledWith('2.1');
  });

  it('양식 옆 창에서는 올리지 않는다. 발주기관은 고치고 승인한다', () => {
    const client = actions(true);
    render(
      <ToasterProvider>
        <DesignatedSheet item={row([entry])} actions={client} onClose={vi.fn()} />
      </ToasterProvider>,
    );
    expect(screen.getByText('양식 내려받기: 양식.xlsx')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '고치기' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '양식 추가 등록' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '올리기' })).toBeNull();
  });
});

describe('올리기 창', () => {
  it('용역사는 양식을 내려받고 그 양식으로 올리기만 한다', () => {
    const contractor = actions(false);
    render(
      <ToasterProvider>
        <UploadDialog
          item={row([entry])}
          actions={contractor}
          onClose={vi.fn()}
          onUploadPlain={vi.fn()}
        />
      </ToasterProvider>,
    );
    expect(screen.getByText('양식 내려받기: 양식.xlsx')).toBeInTheDocument();
    expect(screen.getByText('시험 보고서')).toBeInTheDocument();
    expect(screen.getByText(/반려 사유: 결함 목록 누락/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '고치기' })).toBeNull();
    expect(screen.queryByRole('button', { name: '거두기' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '올리기' }));
    expect(contractor.onUpload).toHaveBeenCalledWith('2.1', 'd1');
  });

  it('기타 산출물 올리기는 양식 없이 그 작업에 올린다', () => {
    const plain = vi.fn();
    render(
      <MemoryRouter>
        <ToasterProvider>
          <UploadDialog
            item={row([entry])}
            actions={actions(false)}
            onClose={vi.fn()}
            onUploadPlain={plain}
          />
        </ToasterProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '기타 산출물 올리기' }));
    expect(plain).toHaveBeenCalledWith('2.1');
  });
});
