import { useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { useAuth } from '@/features/auth/auth-context';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import type { ProjectDetailResponse } from '@/types/api';

/**
 * 사업 삭제. 등록할 때 정한 비밀번호를 맞춰야 지워지고,
 * 사업에 딸린 자료·요구사항·연동까지 함께 사라진다.
 */
export function ProjectDeleteDialog({
  project,
  open,
  onOpenChange,
}: {
  project: ProjectDetailResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): ReactNode {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { refreshMe } = useAuth();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password) {
      setError('삭제 비밀번호를 입력하세요.');
      return;
    }
    setPending(true);
    setError(null);
    try {
      await api.del<void>(`/projects/${project.id}`, { password });
      await refreshMe();
      onOpenChange(false);
      toast({ title: `${project.name} 사업을 삭제했습니다.`, variant: 'success' });
      void navigate('/projects', { replace: true });
    } catch (err) {
      setError(isApiError(err) ? err.message : '삭제하지 못했습니다.');
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          setPassword('');
          setError(null);
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold tracking-tight">
            사업을 삭제할까요?
          </DialogTitle>
          <DialogDescription>
            <b className="text-foreground font-medium">{project.name}</b> 과 여기 딸린
            자료·요구사항·연동이 모두 사라집니다. 되돌릴 수 없습니다.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="flex flex-col gap-1.5">
          <Label htmlFor="delete-password">삭제 비밀번호</Label>
          <Input
            id="delete-password"
            type="password"
            autoComplete="off"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}

          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              취소
            </Button>
            <Button type="submit" variant="destructive" disabled={pending}>
              {pending ? '삭제 중…' : '삭제'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
