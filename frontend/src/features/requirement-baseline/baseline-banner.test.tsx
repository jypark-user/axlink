import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { BaselineBanner } from '@/features/requirement-baseline/baseline-banner';
import type { BaselineResponse, BaselineStateResponse } from '@/types/api';

// 사용자 화면에는 "기준선" 대신 요구사항 목록과 확정으로 쓴다. 내부 이름(baseline)은 그대로다.
// 확정 전에 보이는 기존 요구사항과 명세서에서 뽑은 확정 전 목록이 섞여 보이지 않아야 한다.

const confirmed = {
  version: 1,
  confirmedAt: '2026-10-16T06:19:00Z',
  sourceFilename: '요구사항명세서.docx',
  sourceDocVersion: '1.0',
} as unknown as BaselineResponse;

const state = (over: Partial<BaselineStateResponse>): BaselineStateResponse => ({
  state: 'NONE',
  confirmed: null,
  working: null,
  workingStatus: null,
  requirementCount: 0,
  outsideBaselineCount: 0,
  unresolvedCodeCount: 0,
  ...over,
});

const renderBanner = (s: BaselineStateResponse) =>
  render(
    <MemoryRouter>
      <BaselineBanner projectId="p1" state={s} />
    </MemoryRouter>,
  );

describe('요구사항 화면 머리의 확정 상태', () => {
  it('확정되면 확정된 요구사항 목록과 확정본 번호로 알린다', () => {
    const { container } = renderBanner(
      state({ state: 'CONFIRMED', confirmed, requirementCount: 5, outsideBaselineCount: 1 }),
    );
    expect(screen.getByText(/확정된 요구사항 목록 · 확정본 v1/)).toBeInTheDocument();
    expect(
      screen.getByText(/확정된 명세서에 포함되지 않은 요구사항이 1건 있습니다/),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '요구사항 등록·확정' })).toHaveAttribute(
      'href',
      '/p/p1/requirement-baseline',
    );
    expect(container.textContent).not.toContain('기준선');
  });

  it('확정 전이면 지금 요구사항이 확정된 목록이 아니고 확정 전 목록은 따로 있다고 알린다', () => {
    const { container } = renderBanner(
      state({ state: 'NONE', workingStatus: 'SUBMITTED', requirementCount: 2 }),
    );
    expect(screen.getByText('요구사항 목록 확정 전 · 발주기관 확정 대기')).toBeInTheDocument();
    expect(
      screen.getByText(/지금 보이는 요구사항 2건은 확정된 요구사항 목록이 아닙니다/),
    ).toBeInTheDocument();
    expect(screen.getByText(/확정 전 목록은 요구사항 등록·확정 화면에 있고/)).toBeInTheDocument();
    expect(container.textContent).not.toContain('기준선');
  });

  it('명세서가 없으면 누가 무엇을 하면 목록이 생기는지 알린다', () => {
    const { container } = renderBanner(state({}));
    expect(screen.getByText('요구사항 목록 확정 전 · 명세서 미등록')).toBeInTheDocument();
    expect(
      screen.getByText('요구사항 명세서를 올려 용역사가 정리·제출하고 발주기관이 확정하면 목록이 생깁니다.'),
    ).toBeInTheDocument();
    expect(container.textContent).not.toContain('기준선');
  });
});
