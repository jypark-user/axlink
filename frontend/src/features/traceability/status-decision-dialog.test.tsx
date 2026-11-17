import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import { StatusDecisionDialog } from '@/features/traceability/status-decision-dialog';
import type { TraceabilityRowResponse } from '@/types/api';

// 요구사항 상태 지정의 사유는 선택이다(2026-11-17 사용자 결정, ARC-025 개정).

const put = vi.fn((_path: string, _body: unknown) => Promise.resolve({}));
const post = vi.fn((_path: string, _body: unknown) => Promise.resolve({}));
vi.mock('@/lib/http', () => ({
  api: {
    put: (path: string, body: unknown) => put(path, body),
    post: (path: string, body: unknown) => post(path, body),
  },
}));

const row = {
  requirementId: 'r1',
  requirementCode: 'SWFR.WEB.001',
  requirementTitle: '대시보드',
  requirementStatus: 'IMPLEMENTED',
  requirementStatusBasis: 'CLIENT_DECIDED',
  requirementEvidenceStatus: 'DEFINED',
  requirementDecision: {
    status: 'IMPLEMENTED',
    reason: null,
    decidedBy: '김발주',
    decidedAt: '2026-11-17T01:00:00Z',
  },
} as unknown as TraceabilityRowResponse;

const renderDialog = () =>
  render(
    <ToasterProvider>
      <StatusDecisionDialog projectId="p1" row={row} onOpenChange={vi.fn()} onSaved={vi.fn()} />
    </ToasterProvider>,
  );

describe('요구사항 상태 지정', () => {
  it('사유 없이도 지정하고, 비운 사유는 보내지 않는다', async () => {
    renderDialog();
    expect(screen.getByText('사유 (선택)')).toBeInTheDocument();
    const decide = screen.getByRole('button', { name: '지정' });
    expect(decide).toBeEnabled();
    fireEvent.click(decide);
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect(put.mock.calls[0][1]).toEqual({ status: 'IMPLEMENTED', reason: null });
  });

  it('사유 없이 남은 지정은 「사유 없음」으로 보이고 사유 없이 해제한다', async () => {
    renderDialog();
    expect(screen.getByText('사유 없음')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /지정 해제/ }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).toEqual({ reason: null });
  });
});
