import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { IssueProgress, RequirementIssue } from '@/types/api';

/**
 * 요구사항에 이어진 이슈·일감의 진행. 용역사가 그 요구사항으로 일을 얼마나 등록했고 얼마나
 * 닫았는지 본다. 이슈가 요구사항 코드를 참조하면 수집이 잇는다. 이행률과는 따로다.
 */

const STATUS_TEXT: Record<string, string> = {
  OPEN: '열림',
  IN_PROGRESS: '진행',
  RESOLVED: '해결',
  CLOSED: '종료',
};

const STATUS_TONE: Record<string, string> = {
  OPEN: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  IN_PROGRESS: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  RESOLVED: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  CLOSED: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
};

/** 목록 칸: 닫힘 b / 전체 n, 막대, 진행·열림 건수. 없으면 「등록된 이슈 없음」. */
export function IssueProgressCell({ progress }: { progress?: IssueProgress | null }): ReactNode {
  const p = progress ?? { total: 0, open: 0, inProgress: 0, closed: 0 };
  if (p.total === 0) {
    return (
      <span
        className="text-xs text-amber-700 dark:text-amber-300"
        title="이 요구사항 코드를 참조한 이슈·일감이 없습니다"
      >
        등록된 이슈 없음
      </span>
    );
  }
  const ratio = p.closed / p.total;
  const rest = [
    p.inProgress > 0 ? `진행 ${p.inProgress}` : null,
    p.open > 0 ? `열림 ${p.open}` : null,
  ].filter(Boolean);
  return (
    <div
      className="flex w-28 flex-col gap-1"
      title={`이슈·일감 ${p.total}건 중 ${p.closed}건 닫힘(해결·종료)`}
    >
      <span className="text-sm">
        닫힘 <span className="tnum font-medium">{p.closed}</span>
        <span className="text-muted-foreground"> / {p.total}</span>
      </span>
      <span className="bg-muted h-1.5 w-full overflow-hidden rounded-full" aria-hidden>
        <span
          className="block h-full rounded-full bg-emerald-500"
          style={{ width: `${Math.round(ratio * 100)}%` }}
        />
      </span>
      {rest.length > 0 && (
        <span className="text-muted-foreground text-[11px]">{rest.join(' · ')}</span>
      )}
    </div>
  );
}

/** 상세: 이어진 이슈·일감 하나하나. 열린 것이 앞에 온다. */
export function IssueList({ issues }: { issues: RequirementIssue[] }): ReactNode {
  if (issues.length === 0) {
    return (
      <p className="text-muted-foreground">
        이 요구사항 코드를 참조한 이슈·일감이 아직 없습니다. 용역사가 이슈·일감 제목이나 본문에
        요구사항 코드를 적으면 다음 수집 때 여기에 이어집니다.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {issues.map((i) => (
        <li key={i.id} className="flex items-center gap-2">
          <span
            className={cn(
              'shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium',
              STATUS_TONE[i.status] ?? 'bg-muted',
            )}
          >
            {STATUS_TEXT[i.status] ?? i.status}
          </span>
          {i.url ? (
            <a
              href={i.url}
              target="_blank"
              rel="noreferrer"
              className="min-w-0 truncate underline-offset-2 hover:underline"
              title={i.title}
            >
              {i.key && <span className="text-muted-foreground font-mono text-xs">{i.key} </span>}
              {i.title}
            </a>
          ) : (
            <span className="min-w-0 truncate" title={i.title}>
              {i.key && <span className="text-muted-foreground font-mono text-xs">{i.key} </span>}
              {i.title}
            </span>
          )}
          {i.kind === 'DEFECT' && (
            <span className="text-destructive shrink-0 text-[11px]">결함</span>
          )}
        </li>
      ))}
    </ul>
  );
}
