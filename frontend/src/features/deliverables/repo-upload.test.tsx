import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UploadMenu } from '@/features/deliverables/repo-upload';

// 업로드(11-19): 파일을 직접 올리거나 저장소 파일을 고른다. 저장소 파일이 없으면 바로 파일을 고른다.

describe('업로드 단추', () => {
  it('저장소 파일이 없으면 바로 파일을 고른다', () => {
    const onFile = vi.fn();
    const onRepo = vi.fn();
    render(<UploadMenu hasRepo={false} onFile={onFile} onRepo={onRepo} />);
    fireEvent.click(screen.getByRole('button', { name: '업로드' }));
    expect(onFile).toHaveBeenCalledOnce();
    expect(onRepo).not.toHaveBeenCalled();
  });

  it('저장소 파일이 있으면 펼침 단추로 둘 중에 고른다', () => {
    render(<UploadMenu hasRepo onFile={vi.fn()} onRepo={vi.fn()} />);
    const trigger = screen.getByRole('button', { name: '업로드' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
  });
});
