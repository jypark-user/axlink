import { useEffect, useState, type ReactNode } from 'react';
import { CalendarClock, Settings2 } from 'lucide-react';
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

type Part = 'sync' | 'snapshot';

const PART = {
  sync: {
    button: '수집 설정',
    icon: Settings2,
    title: '자동 수집',
    description: '서버가 스스로 연결된 도구를 다시 읽는 규칙입니다. 이 사업에만 적용됩니다.',
  },
  snapshot: {
    button: '스냅샷 설정',
    icon: CalendarClock,
    title: '일별 스냅샷',
    description: '서버가 스스로 지표를 하루 한 줄로 남기는 규칙입니다. 이 사업에만 적용됩니다.',
  },
} as const;

/**
 * 사업별 자동 수집 주기(동기화 화면)와 일별 스냅샷 시각(스냅샷 화면)을 정하는 창. 서버 안
 * 스케줄러가 이 값을 읽어 돈다. 둘은 다른 것이라 각자의 화면에서 연다(11-18 사용자 지시).
 * 발주기관·관리자에게만 여는 버튼이 보인다. 용역사는 결과만 본다.
 */
export function ScheduleSettingsDialog({
  projectId,
  part,
  onSaved,
}: {
  projectId: string;
  part: Part;
  onSaved?: () => void;
}): ReactNode {
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  if (!me || (me.role !== 'CLIENT' && me.role !== 'SUPER_ADMIN')) return null;
  const text = PART[part];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <text.icon className="size-4" />
          {text.button}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{text.title}</DialogTitle>
          <DialogDescription>{text.description}</DialogDescription>
        </DialogHeader>
        {open && (
          <ScheduleForm
            projectId={projectId}
            part={part}
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
  part,
  onSaved,
}: {
  projectId: string;
  part: Part;
  onSaved: () => void;
}): ReactNode {
  const { toast } = useToast();
  const state = useAsync<ProjectScheduleResponse>(
    () => api.get<ProjectScheduleResponse>(`/projects/${projectId}/schedule`),
    [projectId],
  );
  const [interval, setInterval] = useState<number>(30);
  const [syncTime, setSyncTime] = useState('06:00');
  const [snapshotTime, setSnapshotTime] = useState('00:10');
  const [snapshotEvery, setSnapshotEvery] = useState<number>(24);
  const [saving, setSaving] = useState<'sync' | 'snapshot' | null>(null);

  useEffect(() => {
    if (!state.data) return;
    setInterval(state.data.syncIntervalMinutes);
    setSyncTime(state.data.syncTime);
    setSnapshotTime(state.data.snapshotTime);
    setSnapshotEvery(state.data.snapshotIntervalHours);
  }, [state.data]);

  // 서버는 둘을 한 설정으로 갖는다. 따로 저장해도 바뀐 쪽만 다르게 보낸다.
  const save = async (which: 'sync' | 'snapshot') => {
    if (!state.data) return;
    setSaving(which);
    try {
      await api.put<ProjectScheduleResponse>(`/projects/${projectId}/schedule`, {
        syncIntervalMinutes: which === 'sync' ? interval : state.data.syncIntervalMinutes,
        syncTime: which === 'sync' ? syncTime : state.data.syncTime,
        snapshotTime: which === 'snapshot' ? snapshotTime : state.data.snapshotTime,
        snapshotIntervalHours:
          which === 'snapshot' ? snapshotEvery : state.data.snapshotIntervalHours,
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
          {part === 'sync' && (
            <section className="flex flex-col gap-3">
              <div>
                <h3 className="text-sm font-semibold">자동 수집 주기</h3>
                <p className="text-muted-foreground mt-1 text-sm">
                  이 간격으로 연결된 도구에서 변경분을 다시 읽습니다. 수동 수집은 언제든 됩니다.
                </p>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="sync-interval">빈도</Label>
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
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="sync-time">기준 시각 ({s.timezone})</Label>
                  <input
                    id="sync-time"
                    type="time"
                    className="bg-background border-input h-9 w-40 rounded-md border px-2 text-sm"
                    value={syncTime}
                    disabled={interval !== 1440}
                    title={interval !== 1440 ? '하루 한 번일 때만 씁니다' : undefined}
                    onChange={(e) => setSyncTime(e.target.value)}
                  />
                </div>
                <Button
                  size="sm"
                  onClick={() => void save('sync')}
                  disabled={
                    saving !== null ||
                    (interval === s.syncIntervalMinutes && syncTime === s.syncTime)
                  }
                >
                  {saving === 'sync' ? '저장 중…' : '저장'}
                </Button>
              </div>
              <span className="text-muted-foreground text-xs">
                최소 {s.minIntervalMinutes}분입니다. 너무 자주 부르면 도구의 호출 한도에 걸립니다.
                하루 한 번을 고르면 기준 시각에 돌고, 더 잦은 빈도는 마지막 수집 뒤 그 간격으로
                돕니다.
              </span>
            </section>
          )}

          {part === 'snapshot' && (
            <section className="flex flex-col gap-3">
              <div>
                <h3 className="text-sm font-semibold">일별 스냅샷</h3>
                <p className="text-muted-foreground mt-1 text-sm">
                  매일 정한 시각에 진척·일정·품질·산출물 지표를 한 줄로 남깁니다. 추이 그래프의
                  재료입니다. 과업지시서 Ⅱ.2의 일별 기록이 최소이고, 더 자주 갱신하면 그날 값이
                  최신으로 덮입니다.
                </p>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="snapshot-every">빈도</Label>
                  <select
                    id="snapshot-every"
                    className="bg-background border-input h-9 rounded-md border px-2 text-sm"
                    value={snapshotEvery}
                    onChange={(e) => setSnapshotEvery(Number(e.target.value))}
                  >
                    {s.snapshotOptions.map((o) => (
                      <option key={o.hours} value={o.hours}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="snapshot-time">기준 시각 ({s.timezone})</Label>
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
                  disabled={
                    saving !== null ||
                    (snapshotTime === s.snapshotTime && snapshotEvery === s.snapshotIntervalHours)
                  }
                >
                  {saving === 'snapshot' ? '저장 중…' : '저장'}
                </Button>
              </div>
              <span className="text-muted-foreground text-xs tnum">
                마지막 기록 {s.lastSnapshotDate ? formatDate(s.lastSnapshotDate) : '없음'} · 다음{' '}
                {formatDateTime(s.nextSnapshotAt)}
              </span>
            </section>
          )}
          <DialogFooter />
        </div>
      )}
    </DataState>
  );
}
