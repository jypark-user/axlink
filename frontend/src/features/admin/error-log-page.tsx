import { useState, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { ErrorLogResponse, PageResponse } from '@/types/api';

/**
 * 서버 오류 기록. 500 으로 끝난 요청의 경로·메시지·스택을 최고관리자가 여기서 본다.
 * 폐쇄망에서 로그 파일을 열어 볼 사람이 없다는 전제다.
 */
export function ErrorLogPage(): ReactNode {
  const { toast } = useToast();
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);

  const state = useAsync<PageResponse<ErrorLogResponse>>(
    () => api.get<PageResponse<ErrorLogResponse>>(`/admin/errors${toQueryString({ page, size: 50 })}`),
    [page],
  );
  const { reload } = state;

  const clear = async () => {
    if (!window.confirm('오류 기록을 모두 지웁니다. 계속할까요?')) return;
    try {
      await api.del('/admin/errors');
      toast({ title: '지웠습니다.', variant: 'success' });
      reload();
    } catch {
      toast({ title: '지우지 못했습니다.', variant: 'error' });
    }
  };

  return (
    <>
      <PageHeader
        guide="admin#errors"
        title="서버 오류 기록"
        actions={
          <>
            <Button size="sm" variant="outline" onClick={reload}>
              새로 고침
            </Button>
            <Button size="sm" variant="ghost" onClick={clear}>
              모두 지우기
            </Button>
          </>
        }
      />
      <DataState state={state} onRetry={reload} empty={{ text: '기록된 오류가 없습니다.' }}>
        {(data) =>
          data.content.length === 0 ? (
            <p className="text-muted-foreground text-sm">기록된 오류가 없습니다.</p>
          ) : (
            <>
              <ul className="flex flex-col divide-y rounded border">
                {data.content.map((e) => (
                  <li key={e.id} className="flex flex-col gap-1 p-3">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="text-muted-foreground tnum whitespace-nowrap">
                        {formatDateTime(e.occurredAt)}
                      </span>
                      <Badge variant="destructive">{e.statusCode}</Badge>
                      <span className="font-mono text-xs">
                        {e.method} {e.path}
                      </span>
                      {e.username && (
                        <span className="text-muted-foreground text-xs">
                          {e.userName ?? e.username}
                        </span>
                      )}
                    </div>
                    <p className="text-sm break-all">{e.message}</p>
                    {e.traceback && (
                      <div>
                        <button
                          type="button"
                          className="text-muted-foreground text-xs underline-offset-2 hover:underline"
                          onClick={() => setOpen(open === e.id ? null : e.id)}
                        >
                          {open === e.id ? '스택 접기' : '스택 보기'}
                        </button>
                        {open === e.id && (
                          <pre className="bg-muted mt-2 max-h-96 overflow-auto rounded p-3 text-xs leading-5">
                            {e.traceback}
                          </pre>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              <PaginationBar page={data} onChange={setPage} />
            </>
          )
        }
      </DataState>
    </>
  );
}
