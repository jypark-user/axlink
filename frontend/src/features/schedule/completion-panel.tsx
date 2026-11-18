import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { DataState } from '@/components/common/data-state';
import { formatDate, formatPercent } from '@/lib/format';
import type { AsyncState } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import { completionText, rateText } from '@/features/review-requests/completion-text';
import type { CompletionItem, CompletionSummaryResponse } from '@/types/api';

/**
 * 보고 진척률과 완료 확인율 (ARC-019).
 * 보고 진척률은 용역사가 WBS 에 적은 실적이고, 완료 확인율은 발주기관이 '작업 완료 확인'
 * 요청으로 완료를 인정한 작업의 가중치 비율이다. 두 값을 나란히 두고 섞지 않는다.
 */
export function CompletionPanel({
  state,
}: {
  state: AsyncState<CompletionSummaryResponse>;
}): ReactNode {
  return (
    <DataState state={state} onRetry={state.reload}>
      {(s) => (
        <section className="mb-6 flex flex-col gap-3" aria-label="작업 완료 확인">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Stat
              term="보고 진척률"
              value={s.reportedPct === null ? '산출 불가' : formatPercent(s.reportedPct, 1)}
              hint="용역사가 WBS 에 적은 실적의 가중 평균"
            />
            <Stat term="완료 확인율" value={rateText(s.completionRate)} hint={s.basis} />
          </div>
          <p className="text-muted-foreground text-sm">
            말단 작업 <span className="tnum">{s.leafCount}</span>개 중 완료 확인{' '}
            <span className="tnum text-foreground font-medium">{s.confirmedCount}</span>개 · 보고
            100% 작업 <span className="tnum">{s.reported100Count}</span>개 중 확인 대기{' '}
            <span className="tnum text-foreground font-medium">{s.reported100Pending}</span>개 ·
            확인 진행 중 <span className="tnum">{s.inProgressCount}</span>개
            {s.reconfirmCount > 0 && (
              <>
                {' '}
                · 재확인 필요 <span className="tnum text-warning">{s.reconfirmCount}</span>개
              </>
            )}
          </p>
        </section>
      )}
    </DataState>
  );
}

function Stat({ term, value, hint }: { term: string; value: string; hint: string }): ReactNode {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <p className="win-label">{term}</p>
        <p className="tnum text-foreground mt-1 text-2xl font-semibold">{value}</p>
        <p className="text-muted-foreground mt-0.5 text-xs">{hint}</p>
      </CardContent>
    </Card>
  );
}

/**
 * 작업 완료 확인 칸 (UC-032 4단계). 위쪽에 따로 두던 작업별 표는 WBS 탭과 겹쳐 뺐고(11-18 사용자
 * 지시), 이 칸만 WBS 탭 표에 붙는다.
 */
export function CompletionCell({ item: i }: { item: CompletionItem }): ReactNode {
  const confirmed = i.completionStatus === 'CONFIRMED';
  const attention =
    i.completionStatus === 'RECONFIRM' || (i.completionStatus === 'NONE' && i.predecessorConfirmed);
  return (
    <div className="flex flex-col gap-0.5">
      <span className={cn(confirmed && 'text-success font-medium', attention && 'text-warning')}>
        {completionText(i)}
      </span>
      {confirmed && i.confirmedAt && (
        <span className="text-muted-foreground">
          {i.confirmedBy} · {formatDate(i.confirmedAt)}
          {i.weightAtConfirm !== null && i.weightAtConfirm !== i.weight && (
            <> · 확인 당시 가중치 {formatPercent(i.weightAtConfirm, 0)}</>
          )}
          {i.planVersionAtConfirm && <> · WBS {i.planVersionAtConfirm}</>}
        </span>
      )}
      {confirmed && i.evidenceRevised && (
        <Badge variant="outline" className="w-fit">
          확인 후 근거 개정됨
        </Badge>
      )}
      {i.openRequestId && (
        <Link to={`../reviews?open=${i.openRequestId}`} relative="path" className="text-primary">
          확인 요청 진행 중
        </Link>
      )}
    </div>
  );
}
