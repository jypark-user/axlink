import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import { ReviewBadge, ReviewButton, reviewCounts } from '@/features/deliverables/review-button';
import type { DeliverableReview, WbsDeliverableItem } from '@/types/api';

// 산출물 줄의 검토(11-18). 발주기관은 눌러 승인·반려하고, 용역사는 상태만 본다.

vi.mock('@/lib/http', () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(async (url: string) => ({
      id: url,
      fileName: '',
      status: 'STRUCTURED',
      charCount: 4,
      pageCount: null,
      text: `원문 ${url}`,
    })),
  },
  download: vi.fn(),
}));

const review = (
  status: DeliverableReview['status'],
  id = 'doc1',
  latest = true,
  designatedId: string | null = null,
): DeliverableReview => ({
  documentId: id,
  name: '시험결과서',
  fileName: '결과.xlsx',
  uploadedAt: '2026-11-18T00:00:00Z',
  status,
  rejectReason: status === 'REJECTED' ? '누락' : null,
  reviewedAt: null,
  latest,
  designatedId,
});

const item = (list: DeliverableReview[]): WbsDeliverableItem => ({
  wbsId: '2.1',
  name: '통합 시험',
  deliverable: '시험결과서',
  endDate: null,
  status: 'SUBMITTED',
  rule: null,
  ref: null,
  url: null,
  productType: null,
  documents: [],
  review: list,
});

describe('승인 현황', () => {
  it('상태별로 세고 지난 판은 빼며 0건은 그리지 않는다', () => {
    expect(reviewCounts([])).toEqual({ SUBMITTED: 0, APPROVED: 0, REJECTED: 0 });
    expect(
      reviewCounts([
        review('APPROVED'),
        review('SUBMITTED', 'w2'),
        review('SUBMITTED', 'w0', false),
      ]),
    ).toEqual({ SUBMITTED: 1, APPROVED: 1, REJECTED: 0 });
    render(<ReviewBadge item={item([review('APPROVED'), review('SUBMITTED', 'w2')])} />);
    expect(screen.getByText('승인 대기 1건')).toBeTruthy();
    expect(screen.getByText('승인 1건')).toBeTruthy();
    expect(screen.queryByText(/반려/)).toBeNull();
  });
});

describe('검토 단추', () => {
  it('발주기관은 눌러 승인·반려 창을 연다', () => {
    render(
      <MemoryRouter>
        <ToasterProvider>
          <ReviewButton
            projectId="p1"
            item={item([review('SUBMITTED')])}
            canReview
            onChanged={vi.fn()}
          />
        </ToasterProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '검토' }));
    expect(screen.getByRole('button', { name: '승인' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '반려' })).toBeInTheDocument();
    // 파일 이름은 링크가 아니다(11-19). 원문은 상세보기로, 내려받기는 옆 단추로
    expect(screen.queryByRole('link', { name: /결과\.xlsx/ })).toBeNull();
    expect(screen.getByRole('button', { name: '상세보기' })).toBeInTheDocument();
    expect(screen.getByText('내려받기')).toBeInTheDocument();
  });

  it('지난 판은 목록에 없고 최신 판 상세보기에서 원문과 함께 고른다', async () => {
    const list = [
      { ...review('SUBMITTED', 'new', true, 'f1'), fileName: '새판.pdf' },
      { ...review('REJECTED', 'old', false, 'f1'), fileName: '앞판.pdf' },
    ];
    render(
      <MemoryRouter>
        <ToasterProvider>
          <ReviewButton projectId="p1" item={item(list)} canReview onChanged={vi.fn()} />
        </ToasterProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '검토' }));
    expect(screen.queryByText('앞판.pdf')).toBeNull();
    expect(screen.getByText('지난 판 1개')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '상세보기' }));
    expect(await screen.findByText('원문 /documents/new/text')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /앞판\.pdf/ }));
    expect(await screen.findByText('원문 /documents/old/text')).toBeInTheDocument();
    expect(screen.getByText('반려 사유: 누락')).toBeInTheDocument();
  });

  it('용역사에게는 단추가 없고, 상태는 판정 칸 딱지로 본다', () => {
    const { container } = render(
      <MemoryRouter>
        <ToasterProvider>
          <ReviewButton
            projectId="p1"
            item={item([review('REJECTED')])}
            canReview={false}
            onChanged={vi.fn()}
          />
          <ReviewBadge item={item([review('REJECTED')])} />
        </ToasterProvider>
      </MemoryRouter>,
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(container).toHaveTextContent('반려');
  });

  it('제출본이 없으면 아무것도 그리지 않는다', () => {
    const { container } = render(
      <MemoryRouter>
        <ToasterProvider>
          <ReviewButton projectId="p1" item={item([])} canReview onChanged={vi.fn()} />
        </ToasterProvider>
      </MemoryRouter>,
    );
    expect(container.textContent).toBe('');
  });
});
