import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import { ReviewBadge, ReviewButton, reviewState } from '@/features/deliverables/review-button';
import type { DeliverableReview, WbsDeliverableItem } from '@/types/api';

// 산출물 줄의 검토(11-18). 발주기관은 눌러 승인·반려하고, 용역사는 상태만 본다.

vi.mock('@/lib/http', () => ({ api: { post: vi.fn() }, download: vi.fn() }));

const review = (
  status: DeliverableReview['status'],
  id = 'doc1',
  latest = true,
): DeliverableReview => ({
  documentId: id,
  name: '시험결과서',
  fileName: '결과.xlsx',
  uploadedAt: '2026-11-18T00:00:00Z',
  status,
  rejectReason: status === 'REJECTED' ? '누락' : null,
  reviewedAt: null,
  latest,
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

describe('검토 상태', () => {
  it('하나라도 대기면 승인 대기, 모두 승인이면 승인, 그 밖은 반려', () => {
    expect(reviewState([])).toBeNull();
    expect(reviewState([review('APPROVED'), review('SUBMITTED', 'w2')])).toBe('SUBMITTED');
    expect(reviewState([review('APPROVED'), review('APPROVED', 'w2')])).toBe('APPROVED');
    expect(reviewState([review('APPROVED'), review('REJECTED', 'w2')])).toBe('REJECTED');
    // 지난 판은 보지 않는다
    expect(reviewState([review('APPROVED'), review('SUBMITTED', 'w0', false)])).toBe('APPROVED');
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
    // 파일 이름을 누르면 원문(자료 상세)으로 가고, 내려받기도 있다
    expect(screen.getByRole('link', { name: /결과\.xlsx/ })).toHaveAttribute(
      'href',
      '/p/p1/documents/doc1',
    );
    expect(screen.getByText('내려받기')).toBeInTheDocument();
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
