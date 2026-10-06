import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { DataState } from '@/components/common/data-state';
import { api } from '@/lib/http';
import { formatDate, formatPercent } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import {
  APPROVAL_WORD,
  completionText,
  FILE_CHECK_WORD,
  rateText,
  SUBMISSION_WORD,
} from '@/features/review-requests/completion-text';
import type { CompletionItem, CompletionSummaryResponse } from '@/types/api';

/**
 * 보고 진척률과 완료 확인율 (ARC-019).
 * 보고 진척률은 용역사가 WBS 에 적은 실적이고, 완료 확인율은 발주기관이 '작업 완료 확인'
 * 요청으로 완료를 인정한 작업의 가중치 비율이다. 두 값을 나란히 두고 섞지 않는다.
 */
export function CompletionPanel({ projectId }: { projectId: string }): ReactNode {
  const state = useAsync<CompletionSummaryResponse>(
    () => api.get<CompletionSummaryResponse>(`/projects/${projectId}/wbs/completion`),
    [projectId],
  );
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
          {s.items.length > 0 && <CompletionTable items={s.items} />}
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

/** 작업마다 네 사실. 파일 대조·정식 제출·산출물 승인은 근거이고, 마지막 칸만 완료 확인이다. */
function CompletionTable({ items }: { items: CompletionItem[] }): ReactNode {
  return (
    <div className="overflow-x-auto rounded border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-muted-foreground text-xs">
          <tr>
            <th className="px-3 py-2 text-left font-medium">작업</th>
            <th className="px-3 py-2 text-right font-medium">가중치</th>
            <th className="px-3 py-2 text-right font-medium">보고 실적</th>
            <th className="px-3 py-2 text-left font-medium">파일 대조</th>
            <th className="px-3 py-2 text-left font-medium">정식 제출</th>
            <th className="px-3 py-2 text-left font-medium">산출물 승인</th>
            <th className="px-3 py-2 text-left font-medium">작업 완료 확인</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.taskKey} className="border-t">
              <td className="px-3 py-2">
                <span className="tnum text-muted-foreground mr-1.5 text-xs">{i.wbsId}</span>
                {i.name}
              </td>
              <td className="tnum px-3 py-2 text-right">{formatPercent(i.weight, 0)}</td>
              <td className="tnum px-3 py-2 text-right">
                {i.reportedActual === null ? '-' : formatPercent(i.reportedActual, 0)}
              </td>
              <td className="px-3 py-2 text-xs" title={i.fileRef ?? undefined}>
                {i.fileCheck ? (FILE_CHECK_WORD[i.fileCheck] ?? i.fileCheck) : '-'}
              </td>
              <td className="px-3 py-2 text-xs">{SUBMISSION_WORD[i.submission] ?? i.submission}</td>
              <td className="px-3 py-2 text-xs">
                {APPROVAL_WORD[i.approval] ?? i.approval}
                {i.productVersion && (
                  <span className="text-muted-foreground"> · {i.productVersion}</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs">
                <CompletionCell item={i} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompletionCell({ item: i }: { item: CompletionItem }): ReactNode {
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
