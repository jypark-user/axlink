import { useEffect, useState, type ReactNode } from 'react';
import { Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { useAuth } from '@/features/auth/auth-context';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import type { ProjectScheduleResponse } from '@/types/api';

/**
 * 사업별 자동 수집 주기와 일별 스냅샷 시각을 정하는 창. 서버 안 스케줄러가 이 값을 읽어 돈다.
 * 둘은 다른 것이다. 수집은 몇 분마다 도구를 다시 읽을지이고, 스냅샷은 요구사항대로 하루 한 번
 * 지표를 남기는 시각이다. 발주기관·관리자에게만 여는 버튼이 보인다. 용역사는 결과만 본다.
 */
export function ScheduleSettingsDialog({
  projectId,
  onSaved,
}: {
  projectId: string;
  onSaved?: () => void;
}): ReactNode {
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  if (!me || (me.role !== 'CLIENT' && me.role !== 'SUPER_ADMIN')) return null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Settings2 className="size-4" />
          수집 설정
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>자동 수집과 일별 스냅샷</DialogTitle>
          <DialogDescription>
            서버가 스스로 도구를 다시 읽고 지표를 남기는 규칙입니다. 이 사업에만 적용됩니다.
          </DialogDescription>
        </DialogHeader>
        {open && (
          <ScheduleForm
            projectId={projectId}
            onSaved={() => {
              onSaved?.();
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ScheduleForm({
  projectId,
  onSaved,
}: {
  projectId: string;
  onSaved: () => void;
}): ReactNode {
  const { toast } = useToast();
  const state = useAsync<ProjectScheduleResponse>(
    () => api.get<ProjectScheduleResponse>(`/projects/${projectId}/schedule`),
    [projectId],
  );
  const [interval, setInterval] = useState<number>(30);
  const [snapshotTime, setSnapshotTime] = useState('00:10');
  const [saving, setSaving] = useState<'sync' | 'snapshot' | null>(null);

  useEffect(() => {
    if (!state.data) return;
    setInterval(state.data.syncIntervalMinutes);
    setSnapshotTime(state.data.snapshotTime);
  }, [state.data]);

  // 서버는 둘을 한 설정으로 갖는다. 따로 저장해도 바뀐 쪽만 다르게 보낸다.
  const save = async (which: 'sync' | 'snapshot') => {
    if (!state.data) return;
    setSaving(which);
    try {
      await api.put<ProjectScheduleResponse>(`/projects/${projectId}/schedule`, {
        syncIntervalMinutes: which === 'sync' ? interval : state.data.syncIntervalMinutes,
        snapshotTime: which === 'snapshot' ? snapshotTime : state.data.snapshotTime,
      });
      toast({
        title: which === 'sync' ? '수집 주기를 저장했습니다.' : '스냅샷 시각을 저장했습니다.',
        variant: 'success',
      });
      state.reload();
      onSaved();
    } catch (err) {
      toast({
        title: '저장하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setSaving(null);
    }
  };

  return (
    <DataState state={state} onRetry={state.reload}>
      {(s) => (
        <div className="flex flex-col gap-6">
          <section className="flex flex-col gap-3">
            <div>
              <h3 className="text-sm font-semibold">자동 수집 주기</h3>
              <p className="text-muted-foreground mt-1 text-sm">
                이 간격으로 연결된 도구에서 변경분을 다시 읽습니다. 수동 수집은 언제든 됩니다.
              </p>
            </div>
            <div className="flex items-end gap-3">
              <div className="flex flex-1 flex-col gap-1.5">
                <Label htmlFor="sync-interval">주기</Label>
                <select
                  id="sync-interval"
                  className="bg-background border-input h-9 rounded-md border px-2 text-sm"
                  value={interval}
                  onChange={(e) => setInterval(Number(e.target.value))}
                >
                  {s.options.map((o) => (
                    <option key={o.minutes} value={o.minutes}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                size="sm"
                onClick={() => void save('sync')}
                disabled={saving !== null || interval === s.syncIntervalMinutes}
              >
                {saving === 'sync' ? '저장 중…' : '저장'}
              </Button>
            </div>
            <span className="text-muted-foreground text-xs">
              최소 {s.minIntervalMinutes}분입니다. 너무 자주 부르면 도구의 호출 한도에 걸립니다.
            </span>
          </section>

          <section className="flex flex-col gap-3 border-t pt-5">
            <div>
              <h3 className="text-sm font-semibold">일별 스냅샷 시각</h3>
              <p className="text-muted-foreground mt-1 text-sm">
                매일 이 시각에 진척·일정·품질·산출물 지표를 한 줄로 남깁니다. 추이 그래프의
                재료입니다. 하루 한 번이 기준이라 주기는 없고 시각만 정합니다.
              </p>
            </div>
            <div className="flex items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="snapshot-time">시각 ({s.timezone})</Label>
                <input
                  id="snapshot-time"
                  type="time"
                  className="bg-background border-input h-9 w-40 rounded-md border px-2 text-sm"
                  value={snapshotTime}
                  onChange={(e) => setSnapshotTime(e.target.value)}
                />
              </div>
              <Button
                size="sm"
                onClick={() => void save('snapshot')}
                disabled={saving !== null || snapshotTime === s.snapshotTime}
              >
                {saving === 'snapshot' ? '저장 중…' : '저장'}
              </Button>
            </div>
            <span className="text-muted-foreground text-xs tnum">
              마지막 기록 {s.lastSnapshotDate ? formatDate(s.lastSnapshotDate) : '없음'} · 다음{' '}
              {formatDateTime(s.nextSnapshotAt)}
            </span>
          </section>
          <DialogFooter />
        </div>
      )}
    </DataState>
  );
}
