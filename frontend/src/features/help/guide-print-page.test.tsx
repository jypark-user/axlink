import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { GuidePrintPage } from '@/features/help/guide-print-page';

// 앱 공통 스타일이 body 를 화면 높이에 묶고 넘치는 부분을 숨긴다. 앱 틀 밖에 있는 인쇄 화면은
// 스스로 스크롤하지 않으면 첫 화면 아래를 읽을 수 없다. 인쇄할 때는 그 묶음을 풀어야 모든 쪽이 나온다.
// 실제 스크롤과 쪽 수는 브라우저에서 따로 잰다. 여기서는 그 장치가 빠지지 않았는지만 본다.

vi.mock('@/lib/http', () => ({
  api: {
    get: vi.fn((path: string) =>
      Promise.resolve(
        path === '/help'
          ? [{ slug: 'a', file: 'a.md', title: '가' }]
          : { slug: 'a', title: '가', markdown: '# 가\n\n본문', updatedAt: '2026-10-28T00:00:00Z' },
      ),
    ),
  },
  fetchBlob: vi.fn(),
}));

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/guide/print?doc=a']}>
      <GuidePrintPage />
    </MemoryRouter>,
  );

describe('설명서 인쇄 화면', () => {
  it('화면에서는 인쇄 화면 틀이 스크롤하고 인쇄할 때는 틀을 푼다', async () => {
    renderPage();
    await screen.findByText('본문');
    const frame = screen.getByTestId('guide-print-scroll');
    expect(frame).toHaveClass(
      'h-full',
      'overflow-y-auto',
      'print:h-auto',
      'print:overflow-visible',
    );
    // 열자마자 키보드로 내려갈 수 있어야 한다
    expect(frame).toHaveFocus();
  });

  it('인쇄할 때는 html·body 의 높이 묶음과 숨김을 푼다', async () => {
    const { container } = renderPage();
    await screen.findByText('본문');
    const css = container.querySelector('style')?.textContent ?? '';
    expect(css).toMatch(
      /@media print[\s\S]*html, body, #root \{ height: auto !important; overflow: visible !important; \}/,
    );
  });
});
