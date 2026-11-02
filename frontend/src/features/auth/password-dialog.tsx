import { useState, type FormEvent, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/common/toaster';
import { isApiError } from '@/lib/api-error';
import { api } from '@/lib/http';

/** 자기 비밀번호 바꾸기. 발급받은 첫 비밀번호를 받은 사람이 바꾼다(GH-187). */
export function PasswordDialog({ onClose }: { onClose: () => void }): ReactNode {
  const { toast } = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 8) return setError('새 비밀번호는 8자 이상입니다.');
    if (next !== again) return setError('새 비밀번호 두 칸이 다릅니다.');
    setBusy(true);
    setError(null);
    try {
      await api.post('/auth/password', { currentPassword: current, newPassword: next });
      toast({ title: '비밀번호를 바꿨습니다.', variant: 'success' });
      onClose();
    } catch (err) {
      setError(isApiError(err) ? err.message : '바꾸지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>비밀번호 바꾸기</DialogTitle>
            <DialogDescription>
              지금 비밀번호를 맞춰야 바꿉니다. 새 비밀번호는 8자 이상입니다.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pw-current">지금 비밀번호</Label>
            <Input
              id="pw-current"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pw-next">새 비밀번호</Label>
            <Input
              id="pw-next"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pw-again">새 비밀번호 다시</Label>
            <Input
              id="pw-again"
              type="password"
              autoComplete="new-password"
              value={again}
              onChange={(e) => setAgain(e.target.value)}
            />
          </div>
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              그만두기
            </Button>
            <Button type="submit" disabled={busy || !current || !next || !again}>
              바꾸기
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
