import { useState, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Window } from '@/components/ui/window';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import type { ParticipantResponse } from '@/types/api';

/**
 * 참여 업체(GH-138). 발주기관이 관리한다. 대표사·참여사는 표시 구분이고 권한이 같다.
 * 참여를 끝내면 그 업체 사용자의 할당이 해제되고, 그 업체가 만든 연결은 소유 불명확으로 남는다.
 */
export function ParticipantsPanel({
  projectId,
  rows,
  onChanged,
}: {
  projectId: string;
  rows: ParticipantResponse[];
  onChanged: (next: ParticipantResponse[]) => void;
}): ReactNode {
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const base = `/projects/${projectId}/participants`;

  const run = async (call: () => Promise<ParticipantResponse[]>, ok: string) => {
    setBusy(true);
    try {
      onChanged(await call());
      toast({ title: ok, variant: 'success' });
      return true;
    } catch (e) {
      toast({
        title: '처리하지 못했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    const ok = await run(
      () =>
        api.post<ParticipantResponse[]>(base, {
          organizationName: name.trim(),
          role: 'PARTICIPANT',
          workNote: note.trim() || null,
        }),
      '참여 업체를 추가했습니다.',
    );
    if (ok) {
      setName('');
      setNote('');
    }
  };

  return (
    <Window
      title="참여 업체"
      hint="공동 수급 업체입니다. 같은 사업의 업무 정보는 함께 보고, 도구 연결의 설정 변경·삭제는 그 연결의 소유 업체와 발주기관만 합니다. 대표사 표시는 권한과 상관없습니다."
    >
      <div className="flex flex-col gap-3 text-sm">
        {rows.length === 0 && <p className="text-muted-foreground">참여 업체가 없습니다.</p>}
        {rows.map((p) => (
          <div
            key={p.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
          >
            <div className="flex min-w-0 flex-col">
              <span className="flex items-center gap-2 font-medium">
                {p.organizationName}
                <Badge variant={p.role === 'REPRESENTATIVE' ? 'primary' : 'muted'}>
                  {p.role === 'REPRESENTATIVE' ? '대표사' : '참여사'}
                </Badge>
                {p.status === 'REMOVED' && <Badge variant="outline">참여 종료</Badge>}
              </span>
              <span className="text-muted-foreground text-xs">
                사용자 {p.userCount}명 · 연결 {p.connectionCount}개
                {p.workNote ? ` · ${p.workNote}` : ''}
              </span>
            </div>
            {p.status === 'ACTIVE' && (
              <div className="flex gap-2">
                {p.role !== 'REPRESENTATIVE' && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void run(
                        () =>
                          api.patch<ParticipantResponse[]>(`${base}/${p.id}`, {
                            role: 'REPRESENTATIVE',
                          }),
                        '대표사 표시를 바꿨습니다.',
                      )
                    }
                  >
                    대표사로 표시
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    window.confirm(
                      `${p.organizationName} 의 참여를 끝낼까요? 그 업체 사용자의 할당이 해제됩니다.`,
                    ) &&
                    void run(
                      () => api.del<ParticipantResponse[]>(`${base}/${p.id}`),
                      '참여를 끝냈습니다.',
                    )
                  }
                >
                  참여 종료
                </Button>
              </div>
            )}
          </div>
        ))}
        <div className="flex flex-wrap items-end gap-2 pt-1">
          <div className="flex min-w-56 flex-1 flex-col gap-1.5">
            <Label htmlFor="participant-name">업체 이름</Label>
            <Input
              id="participant-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="등록된 용역 업체 이름 또는 새 업체 이름"
            />
          </div>
          <div className="flex min-w-56 flex-1 flex-col gap-1.5">
            <Label htmlFor="participant-note">담당 업무 (선택)</Label>
            <Input id="participant-note" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <Button disabled={!name.trim() || busy} onClick={() => void add()}>
            참여 업체 추가
          </Button>
        </div>
      </div>
    </Window>
  );
}
