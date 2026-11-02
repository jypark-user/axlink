import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ToasterProvider } from '@/components/common/toaster';
import { PasswordDialog } from '@/features/auth/password-dialog';

// 발급받은 첫 비밀번호를 받은 사람이 바꾼다(GH-187). 서버가 지금 비밀번호를 맞춘다.

const post = vi.fn((_path: string, _body: unknown) => Promise.resolve(undefined));
vi.mock('@/lib/http', () => ({
  api: { post: (path: string, body: unknown) => post(path, body) },
}));

const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

const renderDialog = (onClose = vi.fn()) => {
  render(
    <ToasterProvider>
      <PasswordDialog onClose={onClose} />
    </ToasterProvider>,
  );
  return onClose;
};

describe('비밀번호 바꾸기', () => {
  it('새 비밀번호 두 칸이 다르면 보내지 않는다', () => {
    renderDialog();
    fill('지금 비밀번호', 'temp-1234567');
    fill('새 비밀번호', 'new-password-1');
    fill('새 비밀번호 다시', 'new-password-2');
    fireEvent.click(screen.getByRole('button', { name: '바꾸기' }));
    expect(screen.getByRole('alert')).toHaveTextContent('두 칸이 다릅니다');
    expect(post).not.toHaveBeenCalled();
  });

  it('맞으면 지금·새 비밀번호를 보내고 닫는다', async () => {
    const onClose = renderDialog();
    fill('지금 비밀번호', 'temp-1234567');
    fill('새 비밀번호', 'new-password-1');
    fill('새 비밀번호 다시', 'new-password-1');
    fireEvent.click(screen.getByRole('button', { name: '바꾸기' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith('/auth/password', {
      currentPassword: 'temp-1234567',
      newPassword: 'new-password-1',
    });
  });
});
