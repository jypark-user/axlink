import { useEffect, useState, type ReactNode } from 'react';
import { Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import type { ProjectInviteResponse } from '@/types/api';

const inviteUrl = (token: string) =>
  `${window.location.origin}/invite/accept?token=${encodeURIComponent(token)}`;

/** 고를 것이 없다. 열리는 즉시 링크를 만들어 클립보드에 넣는다. */
export function InviteLinkDialog({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): ReactNode {
  const { toast } = useToast();
  const [issued, setIssued] = useState<ProjectInviteResponse | null>(null);

  const copy = async (token: string) => {
    try {
      await navigator.clipboard.writeText(inviteUrl(token));
      toast({ title: '링크를 복사했습니다.', variant: 'success' });
    } catch {
      toast({ title: '복사에 실패했습니다. 링크를 직접 선택해 복사하세요.', variant: 'error' });
    }
  };

  useEffect(() => {
    if (!open) {
      setIssued(null);
      return;
    }
    let cancelled = false;
    api
      .post<ProjectInviteResponse>(`/projects/${projectId}/invites`, {})
      .then((created) => {
        if (cancelled) return;
        setIssued(created);
        if (created.token) void copy(created.token);
      })
      .catch((err) => {
        if (cancelled) return;
        toast({
          title: '초대 링크 생성에 실패했습니다.',
          description: isApiError(err) ? err.message : undefined,
          variant: 'error',
        });
        onOpenChange(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>용역사 초대 링크</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Input
              readOnly
              aria-label="초대 링크"
              value={issued?.token ? inviteUrl(issued.token) : '링크를 만드는 중…'}
              className="font-mono text-xs"
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              aria-label="링크 복사"
              disabled={!issued?.token}
              onClick={() => issued?.token && void copy(issued.token)}
            >
              <Copy className="size-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            클립보드에 복사됐습니다. 링크를 받은 용역사가 직접 계정을 만들고 이 프로젝트에
            참여합니다. 여러 명이 같은 링크로 가입할 수 있고, 14일 뒤 만료됩니다. 창을 닫으면 이
            링크는 다시 볼 수 없습니다.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
