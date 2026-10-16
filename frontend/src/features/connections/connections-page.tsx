import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataState } from '@/components/common/data-state';
import { ConnectionFormDialog } from '@/features/connections/connection-form-dialog';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { useAsync } from '@/lib/use-async';
import type { SyncJobResponse, ToolConnectionResponse } from '@/types/api';

export function ConnectionsPage(): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const state = useAsync<ToolConnectionResponse[]>(
    () => api.get<ToolConnectionResponse[]>(`/projects/${project.id}/connections`),
    [project.id],
  );
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ToolConnectionResponse | null>(null);
  const [deleting, setDeleting] = useState<ToolConnectionResponse | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      toast({ title: done, variant: 'success' });
      state.reload();
    } catch (e) {
      toast({
        title: '요청에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    }
  };

  const runSync = async (c: ToolConnectionResponse) => {
    setSyncingId(c.id);
    try {
      const job = await api.post<SyncJobResponse>(`/connections/${c.id}/sync`, {
        kind: 'BACKFILL',
      });
      const s = job.stats;
      const summary = `가져옴 ${s.fetched.toLocaleString('ko-KR')}건 · 신규·갱신 ${s.upserted} · 변경없음 ${s.skippedUnchanged}`;
      if (job.status === 'FAILED') {
        toast({ title: '수집 실패', description: job.error ?? summary, variant: 'error' });
      } else {
        toast({
          title: `수집 완료 — ${s.fetched.toLocaleString('ko-KR')}건`,
          // job.error 는 실패가 아니라 "권한 없어 건너뛴 항목" 같은 부분성공 안내다.
          description: job.error ? `${summary}\n${job.error}` : summary,
          variant: 'success',
        });
      }
    } catch (e) {
      toast({
        title: '수집 요청에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setSyncingId(null);
      state.reload();
    }
  };

  return (
    <>
      <PageHeader
        title="연동"
        description="GitHub · Redmine 연결과 수집 상태입니다."
        actions={
          <>
            <Button asChild variant="outline">
              <Link to="/guide/tool-integration">
                <BookOpen className="size-4" /> 연동 가이드
              </Link>
            </Button>
            <Button
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              연동 등록
            </Button>
          </>
        }
      />
      <DataState state={state} onRetry={state.reload} empty={{ text: '등록된 연결이 없습니다.' }}>
        {(list) => (
          <div className="grid gap-4 lg:grid-cols-2">
            {list.map((c) => (
              <Card key={c.id}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="truncate">{c.name}</span>
                    <Badge variant="outline">{c.tool}</Badge>
                    <Badge variant={badgeVariantFor(c.status)}>{label(c.status)}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2 text-sm">
                  <p className="truncate text-muted-foreground">
                    {c.baseUrl} · {c.targetResource}
                  </p>
                  <p className="text-muted-foreground">
                    소유 업체{' '}
                    {c.ownerState === 'UNCLEAR' ? (
                      <Badge
                        variant="warning"
                        title="참여 업체가 아닌 조직이 만든 연결입니다. 발주기관이 소유 업체를 지정합니다."
                      >
                        불명확{c.ownerOrgName ? ` · ${c.ownerOrgName}` : ''}
                      </Badge>
                    ) : (
                      <span className="text-foreground">
                        {c.ownerOrgName ?? '-'}
                        {c.ownerState === 'CLIENT' ? ' (발주기관)' : ''}
                      </span>
                    )}
                  </p>
                  {c.credentialMasked && (
                    <p className="text-muted-foreground">인증 {c.credentialMasked}</p>
                  )}
                  <p className="text-muted-foreground">
                    수집 {c.ingestedCount.toLocaleString('ko-KR')}건 · 매핑규칙 {c.mappingRuleCount}
                    개
                  </p>
                  <p className="text-muted-foreground">
                    마지막 동기화 {c.lastSyncedAt ? formatDateTime(c.lastSyncedAt) : '없음'}
                    {c.lastSyncStatus && ` (${label(c.lastSyncStatus)})`}
                  </p>
                  {c.lastSyncError && (
                    <p className="whitespace-pre-wrap rounded bg-destructive/10 p-2 font-mono text-xs text-destructive">
                      {c.lastSyncError}
                    </p>
                  )}
                  {
                    <div className="flex flex-wrap gap-2">
                      {c.canManage && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            act(
                              () => api.post(`/connections/${c.id}/test`, {}),
                              '연결 테스트에 성공했습니다.',
                            )
                          }
                        >
                          연결 테스트
                        </Button>
                      )}
                      <Button size="sm" disabled={syncingId === c.id} onClick={() => runSync(c)}>
                        {syncingId === c.id ? '수집 중…' : '전체 수집'}
                      </Button>
                      {c.canManage &&
                        (c.status === 'ACTIVE' ||
                          c.status === 'PAUSED' ||
                          c.status === 'VERIFIED') && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              act(
                                () =>
                                  api.patch(`/connections/${c.id}/status`, {
                                    status: c.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE',
                                  }),
                                '상태를 변경했습니다.',
                              )
                            }
                          >
                            {c.status === 'ACTIVE' ? '일시중지' : '활성화'}
                          </Button>
                        )}
                      {c.canManage ? (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setEditing(c);
                              setFormOpen(true);
                            }}
                          >
                            수정
                          </Button>
                          <Button size="sm" variant="destructive" onClick={() => setDeleting(c)}>
                            삭제
                          </Button>
                        </>
                      ) : (
                        // 설정 변경·삭제는 소유 업체와 발주기관만 한다(GH-138)
                        <span className="text-muted-foreground self-center text-xs">
                          설정 변경은 소유 업체·발주기관만 할 수 있습니다
                        </span>
                      )}
                    </div>
                  }
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </DataState>
      {formOpen && (
        <ConnectionFormDialog
          key={editing?.id ?? 'new'}
          projectId={project.id}
          connection={editing ?? undefined}
          open={formOpen}
          onOpenChange={setFormOpen}
          onSaved={state.reload}
        />
      )}
      <AlertDialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>연결을 삭제할까요?</AlertDialogTitle>
            <AlertDialogDescription>{deleting?.name}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const target = deleting;
                setDeleting(null);
                if (target)
                  void act(() => api.del(`/connections/${target.id}`), '연결을 삭제했습니다.');
              }}
            >
              삭제
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
