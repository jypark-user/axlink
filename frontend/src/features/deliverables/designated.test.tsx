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

describe('예상 산출물 칸', () => {
  it('없으면 「-」와 발주기관에게 [관리]가 보이고, 누르면 옆 창을 연다', () => {
    const client = actions(true);
    renderCell(row([]), client);
    expect(screen.getByText('-')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '관리' }));
    expect(client.onOpen).toHaveBeenCalledWith('2.1');
  });

  it('용역사에게는 없으면 「-」만 보인다', () => {
    renderCell(row([]), actions(false));
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('첫 산출물 이름과 「외 n건」을 보이고 양식은 칸에 두지 않는다', () => {
    const wbs = { ...entry, id: 'w1', name: '착수보고서', origin: 'WBS' as const };
    renderCell(row([wbs, entry]), actions(false));
    expect(screen.getByText('착수보고서')).toBeInTheDocument();
    expect(screen.getByText('외 1건')).toBeInTheDocument();
    expect(screen.queryByText(/양식 내려받기/)).toBeNull();
    expect(screen.getByRole('button', { name: '보기' })).toBeInTheDocument();
  });
});

describe('예상 산출물 옆 창', () => {
  it('올리지 않는다. 발주기관은 WBS 자동 항목도 고치고 요청을 더한다', () => {
    const client = actions(true);
    const wbs = { ...entry, id: 'w1', name: '착수보고서', origin: 'WBS' as const };
    render(
      <ToasterProvider>
        <DesignatedSheet item={row([wbs, entry])} actions={client} onClose={vi.fn()} />
      </ToasterProvider>,
    );
    expect(screen.getByText('WBS 자동')).toBeInTheDocument();
    expect(screen.getAllByText('양식 내려받기: 양식.xlsx')).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: '고치기' })).toHaveLength(2);
    expect(screen.getByRole('button', { name: '산출물 요청 추가' })).toBeInTheDocument();
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
