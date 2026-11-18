import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import { ReviewButton, reviewState } from '@/features/deliverables/review-button';
import type { DeliverableReview, WbsDeliverableItem } from '@/types/api';

// 산출물 줄의 검토(11-18). 발주기관은 눌러 승인·반려하고, 용역사는 상태만 본다.

vi.mock('@/lib/http', () => ({ api: { post: vi.fn() } }));

const review = (status: DeliverableReview['status'], id = 'w1'): DeliverableReview => ({
  workProductId: id,
  name: '시험결과서',
  fileName: '결과.xlsx',
  version: '1.0',
  status,
  rejectReason: status === 'REJECTED' ? '누락' : null,
  isCurrent: true,
});

const item = (list: DeliverableReview[]): WbsDeliverableItem =>
  ({
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
  }) as WbsDeliverableItem;

describe('검토 상태', () => {
  it('하나라도 대기면 승인 대기, 모두 승인이면 승인, 그 밖은 반려', () => {
    expect(reviewState([])).toBeNull();
    expect(reviewState([review('APPROVED'), review('SUBMITTED', 'w2')])).toBe('SUBMITTED');
    expect(reviewState([review('APPROVED'), review('APPROVED', 'w2')])).toBe('APPROVED');
    expect(reviewState([review('APPROVED'), review('REJECTED', 'w2')])).toBe('REJECTED');
  });
});

describe('검토 단추', () => {
  it('발주기관은 눌러 승인·반려 창을 연다', () => {
    render(
      <ToasterProvider>
        <ReviewButton
          projectId="p1"
          item={item([review('SUBMITTED')])}
          canReview
          onChanged={vi.fn()}
        />
      </ToasterProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: '승인 대기' }));
    expect(screen.getByRole('button', { name: '승인' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '반려' })).toBeInTheDocument();
  });

  it('용역사는 상태만 본다', () => {
    render(
      <ToasterProvider>
        <ReviewButton
          projectId="p1"
          item={item([review('REJECTED')])}
          canReview={false}
          onChanged={vi.fn()}
        />
      </ToasterProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('반려')).toBeInTheDocument();
  });

  it('제출본이 없으면 아무것도 그리지 않는다', () => {
    const { container } = render(
      <ToasterProvider>
        <ReviewButton projectId="p1" item={item([])} canReview onChanged={vi.fn()} />
      </ToasterProvider>,
    );
    expect(container.textContent).toBe('');
  });
});
