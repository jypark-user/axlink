import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GuideMarkdown } from '@/features/help/guide-markdown';
import { fetchBlob } from '@/lib/http';

// 인쇄 화면은 그림마다 "끝남" 을 받아야 PDF 저장 단추를 켠다. 받기는 됐는데(HTTP 200) 그림을
// 해석하지 못한 경우에도 끝남을 알려야 한다(점검 UI-02). 못 그린 그림은 그 자리에 안내가 남는다.

vi.mock('@/lib/http', () => ({ fetchBlob: vi.fn() }));

const PATH = '/help/assets/images/a.png';

const renderDoc = (onSettled: (path: string, ok: boolean) => void) =>
  render(
    <MemoryRouter>
      <GuideMarkdown
        markdown="![연결 화면](images/a.png)"
        files={new Map()}
        onImageSettled={onSettled}
      />
    </MemoryRouter>,
  );

describe('설명서 그림', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'URL',
      Object.assign(URL, {
        createObjectURL: vi.fn(() => 'blob:fake'),
        revokeObjectURL: vi.fn(),
      }),
    );
  });
  afterEach(() => {
    vi.mocked(fetchBlob).mockReset();
  });

  it('그림이 그려지면 끝남(성공)을 알린다', async () => {
    vi.mocked(fetchBlob).mockResolvedValue(new Blob(['png']));
    const settled = vi.fn();
    renderDoc(settled);
    const img = await screen.findByRole('img');
    fireEvent.load(img);
    expect(settled).toHaveBeenCalledWith(PATH, true);
  });

  it('받기는 됐지만 그림을 해석하지 못하면 끝남(실패)을 알리고 안내를 남긴다', async () => {
    vi.mocked(fetchBlob).mockResolvedValue(new Blob(['not a png']));
    const settled = vi.fn();
    renderDoc(settled);
    const img = await screen.findByRole('img');
    fireEvent.error(img);
    expect(settled).toHaveBeenCalledWith(PATH, false);
    await waitFor(() => expect(screen.getByText('그림을 불러오지 못했습니다')).toBeTruthy());
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('받기부터 실패하면(404 등) 끝남(실패)을 알린다', async () => {
    vi.mocked(fetchBlob).mockRejectedValue(new Error('404'));
    const settled = vi.fn();
    renderDoc(settled);
    await waitFor(() => expect(settled).toHaveBeenCalledWith(PATH, false));
    expect(screen.getByText('그림을 불러오지 못했습니다')).toBeTruthy();
  });
});
