import { useState, type ReactNode } from 'react';
import { Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import type { ParticipantResponse, ProjectInviteResponse } from '@/types/api';

const inviteUrl = (token: string) =>
  `${window.location.origin}${import.meta.env.BASE_URL}invite/accept?token=${encodeURIComponent(token)}`;

const NEW_ORG = 'NEW';

/**
 * 초대 링크. 참여 업체를 골라 만들면 가입자는 그 업체로만 들어간다(GH-138).
 * "새 업체 직접 등록" 은 아직 참여 업체로 등록하지 않은 업체가 스스로 이름을 적어 가입하는 링크다.
 * 이미 있는 업체 이름으로는 가입되지 않는다.
 */
export function InviteLinkDialog({
  projectId,
  open,
  onOpenChange,
  participants,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  participants: ParticipantResponse[];
}): ReactNode {
  const { toast } = useToast();
  const [issued, setIssued] = useState<ProjectInviteResponse | null>(null);
  const [orgId, setOrgId] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const active = participants.filter((p) => p.status === 'ACTIVE');

  // 닫을 때 비운다. 다시 열면 업체를 새로 고른다
  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setIssued(null);
      setOrgId('');
    }
    onOpenChange(next);
  };

  const copy = async (token: string) => {
    try {
      await navigator.clipboard.writeText(inviteUrl(token));
      toast({ title: '링크를 복사했습니다.', variant: 'success' });
    } catch {
      toast({ title: '복사에 실패했습니다. 링크를 직접 선택해 복사하세요.', variant: 'error' });
    }
  };

  const create = async () => {
    setBusy(true);
    try {
      const created = await api.post<ProjectInviteResponse>(`/projects/${projectId}/invites`, {
        organizationId: orgId === NEW_ORG ? null : orgId,
      });
      setIssued(created);
      if (created.token) void copy(created.token);
    } catch (err) {
      toast({
        title: '초대 링크 생성에 실패했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>용역사 초대 링크</DialogTitle>
        </DialogHeader>

        {!issued ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="invite-org">가입할 업체</Label>
              <Select value={orgId} onValueChange={setOrgId}>
                <SelectTrigger id="invite-org">
                  <SelectValue placeholder="참여 업체를 고르세요" />
                </SelectTrigger>
                <SelectContent>
                  {active.map((p) => (
                    <SelectItem key={p.organizationId} value={p.organizationId}>
                      {p.organizationName} ({p.role === 'REPRESENTATIVE' ? '대표사' : '참여사'})
                    </SelectItem>
                  ))}
                  <SelectItem value={NEW_ORG}>
                    새 업체 직접 등록 (가입자가 회사명을 적음)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-muted-foreground">
              참여 업체를 고르면 가입자는 회사명과 상관없이 그 업체로 들어갑니다. 새 업체 직접 등록
              링크로는 이미 등록된 업체 이름으로 가입할 수 없습니다.
            </p>
            <div className="flex justify-end">
              <Button disabled={!orgId || busy} onClick={() => void create()}>
                링크 만들기
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {issued.organizationName && (
              <p className="text-sm">
                가입 업체: <span className="font-medium">{issued.organizationName}</span>
              </p>
            )}
            <div className="flex items-center gap-2">
              <Input
                readOnly
                aria-label="초대 링크"
                value={issued.token ? inviteUrl(issued.token) : ''}
                className="font-mono text-xs"
              />
              <Button
                type="button"
                size="icon"
                variant="outline"
                aria-label="링크 복사"
                disabled={!issued.token}
                onClick={() => issued.token && void copy(issued.token)}
              >
                <Copy className="size-4" />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              클립보드에 복사됐습니다. 여러 명이 같은 링크로 가입할 수 있고, 7일 뒤 만료됩니다. 창을
              닫으면 이 링크는 다시 볼 수 없습니다.
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
