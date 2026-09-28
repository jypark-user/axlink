import { useEffect, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import type { ProjectScheduleResponse } from '@/types/api';

/**
 * 사업별 수집 주기와 스냅샷 시각. 서버 안 스케줄러가 이 값을 읽어 돈다.
 * 주기는 선택지 중 하나이고 15분보다 짧을 수 없다. 발주기관만 바꾼다.
 */
export function ScheduleSettingsCard({ projectId }: { projectId: string }): ReactNode {
  const { toast } = useToast();
  const state = useAsync<ProjectScheduleResponse>(
    () => api.get<ProjectScheduleResponse>(`/projects/${projectId}/schedule`),
    [projectId],
  );
  const [interval, setInterval] = useState<number>(30);
  const [snapshotTime, setSnapshotTime] = useState('00:10');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!state.data) return;
    setInterval(state.data.syncIntervalMinutes);
    setSnapshotTime(state.data.snapshotTime);
  }, [state.data]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put<ProjectScheduleResponse>(`/projects/${projectId}/schedule`, {
        syncIntervalMinutes: interval,
        snapshotTime,
      });
      toast({ title: '수집 주기를 저장했습니다.', variant: 'success' });
      state.reload();
    } catch (err) {
      toast({
        title: '저장하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <DataState state={state} onRetry={state.reload}>
      {(s) => (
        <section className="mb-6 flex flex-col gap-4 rounded border p-5">
          <div>
            <h2 className="text-sm font-semibold">자동 수집과 일별 스냅샷</h2>
            <p className="text-muted-foreground mt-1 text-sm">
              서버가 정한 주기로 도구에서 변경분을 가져오고, 매일 정한 시각에 진척·품질 지표를 한
              줄로 남깁니다. 추이 그래프는 이 기록으로 그려집니다.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sync-interval">수집 주기</Label>
              <select
                id="sync-interval"
                className="bg-background border-input h-9 rounded-md border px-2 text-sm"
                value={interval}
                disabled={!s.editable}
                onChange={(e) => setInterval(Number(e.target.value))}
              >
                {s.options.map((o) => (
                  <option key={o.minutes} value={o.minutes}>
                    {o.label}
                  </option>
                ))}
              </select>
              <span className="text-muted-foreground text-xs">
                최소 {s.minIntervalMinutes}분입니다. 너무 자주 부르면 도구의 호출 한도에 걸립니다.
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="snapshot-time">스냅샷 시각 ({s.timezone})</Label>
              <input
                id="snapshot-time"
                type="time"
                className="bg-background border-input h-9 rounded-md border px-2 text-sm"
                value={snapshotTime}
                disabled={!s.editable}
                onChange={(e) => setSnapshotTime(e.target.value)}
              />
              <span className="text-muted-foreground text-xs tnum">
                마지막 기록 {s.lastSnapshotDate ? formatDate(s.lastSnapshotDate) : '없음'} · 다음{' '}
                {formatDateTime(s.nextSnapshotAt)}
              </span>
            </div>
          </div>
          {s.editable ? (
            <div>
              <Button size="sm" onClick={save} disabled={saving}>
                {saving ? '저장 중…' : '저장'}
              </Button>
            </div>
          ) : (
            <p className="text-muted-foreground text-xs">발주기관 담당자가 정합니다.</p>
          )}
        </section>
      )}
    </DataState>
  );
}
