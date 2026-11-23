import { type ReactNode, useState } from 'react';
import { DataState } from '@/components/common/data-state';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useAsync } from '@/lib/use-async';
import { api } from '@/lib/http';
import { cn } from '@/lib/utils';
import type { Iso29110Response, Iso29110Status } from '@/types/api';

const STATUS_TEXT: Record<Iso29110Status, string> = {
  UNPLANNED: '계획 없음',
  PLANNED: '미제출',
  SUBMITTED: '제출',
  APPROVED: '승인',
};

const STATUS_TONE: Record<Iso29110Status, string> = {
  UNPLANNED: 'text-muted-foreground',
  PLANNED: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  SUBMITTED: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  APPROVED: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
};

const ORDER: Iso29110Status[] = ['APPROVED', 'SUBMITTED', 'PLANNED', 'UNPLANNED'];

function StatusPill({ status }: { status: Iso29110Status }): ReactNode {
  return (
    <span
      className={cn(
        'inline-block rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
        STATUS_TONE[status],
      )}
    >
      {STATUS_TEXT[status]}
    </span>
  );
}

/**
 * ISO/IEC 29110 산출물 22종 충족 현황(11-19 사용자 결정, 인도 점검표 대신). 화면 머리 오른쪽
 * 버튼으로 열고 창에서 본다. 22종마다 예상 산출물(WBS 자동 + 발주사 요청)에 계획됐는지와
 * 제출·승인을 네 상태로 보인다. 읽기만 한다. 창을 열 때마다 새로 읽는다.
 */
export function Iso29110Button({ projectId }: { projectId: string }): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        ISO/IEC 29110 충족 현황
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>ISO/IEC 29110 산출물 충족 현황</DialogTitle>
          </DialogHeader>
          {open && <Iso29110Body projectId={projectId} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

function Iso29110Body({ projectId }: { projectId: string }): ReactNode {
  const state = useAsync<Iso29110Response>(
    () => api.get<Iso29110Response>(`/projects/${projectId}/wbs/iso29110`),
    [projectId],
  );
  return (
    <div className="max-h-[70vh] overflow-y-auto">
      <DataState state={state} empty={{ text: '22종 현황이 없습니다.' }}>
        {(data) => (
          <>
            <p className="text-muted-foreground mb-3 flex flex-wrap gap-x-3 text-sm">
              {ORDER.map((k) => (
                <span key={k}>
                  {STATUS_TEXT[k]}{' '}
                  <span className="tnum text-foreground font-medium">{data.counts[k] ?? 0}</span>종
                </span>
              ))}
            </p>
            <div className="grid gap-x-8 md:grid-cols-2">
              {(['PM', 'SI'] as const).map((proc) => (
                <div key={proc} className="min-w-0">
                  <h3 className="text-muted-foreground mb-1 text-xs font-semibold">
                    {proc === 'PM' ? '프로젝트 관리(PM)' : '소프트웨어 구현(SI)'}
                  </h3>
                  <ul className="divide-y border-y">
                    {data.items
                      .filter((i) => i.process === proc)
                      .map((i) => (
                        <li key={i.type} className="flex min-w-0 items-center gap-3 py-1.5">
                          <span className="w-28 shrink-0 text-sm">{i.name}</span>
                          <StatusPill status={i.status} />
                          <span
                            className="text-muted-foreground min-w-0 truncate text-xs"
                            title={i.sources.map((s) => `${s.wbsId} ${s.name}`).join(', ')}
                          >
                            {i.sources.map((s) => `${s.wbsId} ${s.name}`).join(', ')}
                          </span>
                        </li>
                      ))}
                  </ul>
                </div>
              ))}
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}
