import { useState, type FormEvent, type ReactNode } from 'react';
import { CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDate } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import type {
  AcceptanceRecordResponse,
  ProjectClosureResponse,
  ProjectDetailResponse,
} from '@/types/api';

export function ClosurePage(): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const [acceptedBy, setAcceptedBy] = useState('');
  const [acceptedAt, setAcceptedAt] = useState('');
  const [conditions, setConditions] = useState('');
  const [pending, setPending] = useState(false);

  const closure = useAsync<ProjectClosureResponse>(
    () => api.get<ProjectClosureResponse>(`/projects/${project.id}/closure-check`),
    [project.id],
  );
  const record = useAsync<AcceptanceRecordResponse | null>(
    () =>
      api
        .get<AcceptanceRecordResponse>(`/projects/${project.id}/acceptance-record`)
        .catch(() => null),
    [project.id],
  );

  const submitRecord = async (e: FormEvent) => {
    e.preventDefault();
    if (!acceptedBy.trim() || !acceptedAt) {
      toast({ title: '인수자와 인수일은 필수입니다.', variant: 'error' });
      return;
    }
    setPending(true);
    try {
      await api.post<AcceptanceRecordResponse>(`/projects/${project.id}/acceptance-record`, {
        acceptedBy: acceptedBy.trim(),
        acceptedAt,
        conditions: conditions.trim() || null,
        documentId: null,
      });
      toast({ title: '검수확인서를 등록했습니다.', variant: 'success' });
      record.reload();
      closure.reload();
    } catch (err) {
      toast({
        title: '등록에 실패했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setPending(false);
    }
  };

  const closeProject = async () => {
    setPending(true);
    try {
      await api.post<ProjectDetailResponse>(`/projects/${project.id}/close`, {
        confirmationNote: null,
      });
      toast({ title: '프로젝트를 종료했습니다.', variant: 'success' });
      closure.reload();
    } catch (err) {
      toast({
        title: '종료할 수 없습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <PageHeader title="검수 · 종료" description="종료 조건 3가지를 모두 만족해야 종료됩니다." />
      <div className="flex max-w-3xl flex-col gap-4">
        <DataState state={closure} onRetry={closure.reload}>
          {(c) => (
            <Card>
              <CardHeader>
                <CardTitle>종료 조건</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <ul className="flex flex-col gap-2">
                  {c.checks.map((check) => (
                    <li key={check.key} className="flex items-start gap-2 text-sm">
                      {check.satisfied ? (
                        <CheckCircle2 className="mt-0.5 size-4 text-success" />
                      ) : (
                        <XCircle className="mt-0.5 size-4 text-destructive" />
                      )}
                      <div>
                        <p className="font-medium">{check.key}</p>
                        <p className="text-muted-foreground">{check.detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>
                <Button
                  className="self-start"
                  disabled={!c.closable || pending || project.status === 'CLOSED'}
                  onClick={closeProject}
                >
                  {project.status === 'CLOSED' ? '종료됨' : '프로젝트 종료'}
                </Button>
              </CardContent>
            </Card>
          )}
        </DataState>

        <Card>
          <CardHeader>
            <CardTitle>검수확인서</CardTitle>
          </CardHeader>
          <CardContent>
            {record.data ? (
              <dl className="flex flex-col gap-1 text-sm">
                <p>인수자: {record.data.acceptedBy}</p>
                <p>인수일: {formatDate(record.data.acceptedAt)}</p>
                <p>조건: {record.data.conditions ?? '없음'}</p>
                <p>상태: {record.data.status}</p>
              </dl>
            ) : (
              <form onSubmit={submitRecord} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="acceptedBy">인수자</Label>
                  <Input
                    id="acceptedBy"
                    value={acceptedBy}
                    onChange={(e) => setAcceptedBy(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="acceptedAt">인수일</Label>
                  <Input
                    id="acceptedAt"
                    type="date"
                    value={acceptedAt}
                    onChange={(e) => setAcceptedAt(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="conditions">조건</Label>
                  <Textarea
                    id="conditions"
                    rows={3}
                    value={conditions}
                    onChange={(e) => setConditions(e.target.value)}
                  />
                </div>
                <Button type="submit" className="self-start" disabled={pending}>
                  등록
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
