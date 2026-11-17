import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { DataState } from '@/components/common/data-state';
import { RequirementStatusBadge } from '@/components/common/requirement-status';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { label } from '@/lib/labels';
import { EVIDENCE_KIND_TEXT, evidenceLocation } from '@/features/traceability/trace-evidence';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import type {
  EntityHistoryResponse,
  RequirementDetailResponse,
  TraceLinkResponse,
} from '@/types/api';

/**
 * 요구사항 한 건의 상세(GH-158). 정의, 상태와 지정, 확정 명세서의 원문 위치, 연결 목록(상태·사유),
 * 변경 이력을 한 곳에서 본다. 값은 모두 상세 API 에서 온다. 화면은 읽기만 한다.
 */
export function RequirementDetailSheet({
  projectId,
  requirementId,
  onClose,
}: {
  projectId: string;
  requirementId: string | null;
  onClose: () => void;
}): ReactNode {
  return (
    <Sheet open={requirementId !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="flex w-full flex-col gap-0 overflow-y-auto sm:max-w-2xl">
        {requirementId && <Detail projectId={projectId} requirementId={requirementId} />}
      </SheetContent>
    </Sheet>
  );
}

function Detail({
  projectId,
  requirementId,
}: {
  projectId: string;
  requirementId: string;
}): ReactNode {
  const state = useAsync<RequirementDetailResponse>(
    () =>
      api.get<RequirementDetailResponse>(`/projects/${projectId}/requirements/${requirementId}`),
    [projectId, requirementId],
  );
  return (
    <DataState state={state} onRetry={state.reload}>
      {(r) => (
        <>
          <SheetHeader className="gap-2 px-6 pt-6 pb-5">
            <div className="flex items-center gap-2 pr-8">
              <span className="text-muted-foreground font-mono text-xs">{r.code}</span>
              <RequirementStatusBadge status={r.status} basis={r.statusBasis} />
              <Badge variant="outline">{label(r.priority)}</Badge>
            </div>
            <SheetTitle className="text-lg">{r.title}</SheetTitle>
            <SheetDescription>{sourceText(r)}</SheetDescription>
          </SheetHeader>
          <div className="flex flex-col gap-6 px-6 pb-8 text-sm">
            {r.body && r.body !== r.title && (
              <Section title="정의">
                <p className="leading-relaxed whitespace-pre-wrap">{r.body}</p>
              </Section>
            )}
            <Section title="상태">
              <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2">
                <Row term="현재 상태">
                  <RequirementStatusBadge status={r.status} basis={r.statusBasis} />
                </Row>
                {r.evidenceStatus && r.evidenceStatus !== r.status && (
                  <Row term="근거 상태">{label(r.evidenceStatus)}</Row>
                )}
                {r.decision && (
                  <>
                    <Row term="지정 사유">{r.decision.reason ?? '사유 없음'}</Row>
                    <Row term="지정">
                      {r.decision.decidedBy ?? '-'}
                      {r.decision.decidedByRole === 'SUPER_ADMIN' ? '(관리자)' : ''}
                      {r.decision.decidedAt && (
                        <span className="text-muted-foreground tnum">
                          {' '}
                          · {formatDateTime(r.decision.decidedAt)}
                        </span>
                      )}
                    </Row>
                  </>
                )}
              </dl>
            </Section>
            <BaselineSection projectId={projectId} r={r} />
            <Section title={`연결 ${r.traceLinks.length}건`}>
              {r.traceLinks.length === 0 ? (
                <p className="text-muted-foreground">연결된 근거가 없습니다.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {r.traceLinks.map((lk) => (
                    <LinkItem key={lk.id} link={lk} requirementId={r.id} />
                  ))}
                </ul>
              )}
            </Section>
            <Section title="변경 이력">
              {r.history.length === 0 ? (
                <p className="text-muted-foreground">기록이 없습니다.</p>
              ) : (
                <ol className="flex flex-col gap-1.5">
                  {r.history.map((h) => (
                    <HistoryItem key={h.id} h={h} />
                  ))}
                </ol>
              )}
            </Section>
          </div>
        </>
      )}
    </DataState>
  );
}

function sourceText(r: RequirementDetailResponse): string {
  if (r.baselineSource) return `요구사항 목록 확정 v${r.baselineSource.version}`;
  if (r.source.tool === 'UPLOAD') return '명세서';
  if (r.source.connectionName) return `${label(r.source.tool)} · ${r.source.connectionName}`;
  return label(r.source.tool);
}

/** 명세서로 확정한 요구사항의 출처. 판본과 그 안의 표·행 위치다(SWFR.PIP.002). */
function BaselineSection({
  projectId,
  r,
}: {
  projectId: string;
  r: RequirementDetailResponse;
}): ReactNode {
  const b = r.baselineSource;
  if (!b) {
    if (!r.source.externalUrl) return null;
    return (
      <Section title="출처">
        <a
          className="text-primary inline-flex items-center gap-1 break-all hover:underline"
          href={r.source.externalUrl}
          target="_blank"
          rel="noreferrer"
        >
          {r.source.externalUrl} <ExternalLink className="size-3 shrink-0" />
        </a>
      </Section>
    );
  }
  return (
    <Section title="출처 (확정 명세서)">
      <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2">
        <Row term="명세서">
          {b.documentId ? (
            <Link
              className="text-primary hover:underline"
              to={`/p/${projectId}/documents/${b.documentId}`}
            >
              {b.sourceFilename}
            </Link>
          ) : (
            b.sourceFilename
          )}
          {b.sourceDocVersion && (
            <span className="text-muted-foreground"> · 문서 판본 {b.sourceDocVersion}</span>
          )}
        </Row>
        <Row term="원문 위치">{b.location ?? '위치 기록 없음'}</Row>
        <Row term="목록 확정">
          v{b.version}
          {b.match && (
            <span className="text-muted-foreground"> · {MATCH_TEXT[b.match] ?? b.match}</span>
          )}
        </Row>
        {b.confirmedAt && (
          <Row term="확정">
            {b.confirmedBy ?? '-'}
            <span className="text-muted-foreground tnum"> · {formatDateTime(b.confirmedAt)}</span>
          </Row>
        )}
      </dl>
    </Section>
  );
}

const MATCH_TEXT: Record<string, string> = {
  NEW: '새로 들어옴',
  SAME: '기존 정의와 같음',
  CHANGED: '기존 정의와 다름',
};

const LINK_STATUS_TEXT: Record<string, string> = {
  ACTIVE: '유효',
  BROKEN: '근거 사라짐',
  SUPERSEDED: '대체됨',
};

function LinkItem({
  link,
  requirementId,
}: {
  link: TraceLinkResponse;
  requirementId: string;
}): ReactNode {
  // 이 요구사항이 아닌 쪽이 상대다
  const other = link.fromId === requirementId ? link.toLabel : link.fromLabel;
  const inactive = link.status !== 'ACTIVE';
  return (
    <li
      className={cn(
        'rounded-md border px-3 py-2',
        inactive && 'border-destructive/40 bg-destructive/5',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{label(link.linkKind)}</Badge>
        {link.externalUrl ? (
          <a
            className="inline-flex min-w-0 items-center gap-1 hover:underline"
            href={link.externalUrl}
            target="_blank"
            rel="noreferrer"
          >
            <span className="truncate">{other}</span>
            <ExternalLink className="text-muted-foreground size-3 shrink-0" />
          </a>
        ) : (
          <span className="truncate">{other}</span>
        )}
        <span className={cn('text-xs', inactive ? 'text-destructive' : 'text-muted-foreground')}>
          {LINK_STATUS_TEXT[link.status] ?? link.status}
          {link.origin === 'MANUAL' ? ' · 수기' : ''}
        </span>
      </div>
      {(link.evidenceKind || link.origin === 'MANUAL') && (
        <p className="text-muted-foreground mt-1 text-xs">
          근거 유형:{' '}
          {link.evidenceKind
            ? (EVIDENCE_KIND_TEXT[link.evidenceKind] ?? link.evidenceKind)
            : '사람이 직접 이음'}
        </p>
      )}
      {link.evidenceText && (
        <p className="text-muted-foreground mt-1 truncate text-xs" title={link.evidenceText}>
          근거 원문: {link.evidenceText}
        </p>
      )}
      {evidenceLocation(link.evidenceMeta) && (
        <p className="text-muted-foreground mt-1 truncate text-xs">
          원문 위치: {evidenceLocation(link.evidenceMeta)}
        </p>
      )}
      {link.statusReason && (
        <p className="text-destructive mt-1 text-xs">사유: {link.statusReason}</p>
      )}
    </li>
  );
}

const HISTORY_FIELD: Record<string, string> = {
  baseline: '요구사항 목록 확정',
  status: '상태',
  status_decision: '상태 지정',
  status_decision_revert: '지정 되돌림',
  title: '제목',
  priority: '중요도',
};

function HistoryItem({ h }: { h: EntityHistoryResponse }): ReactNode {
  const name = HISTORY_FIELD[h.field] ?? h.field;
  const change =
    h.fromValue && h.toValue
      ? `${historyValue(h.field, h.fromValue)} → ${historyValue(h.field, h.toValue)}`
      : historyValue(h.field, h.toValue ?? h.fromValue ?? '');
  return (
    <li className="grid grid-cols-[9rem_1fr] gap-x-3 text-xs">
      <span className="text-muted-foreground tnum">{formatDateTime(h.changedAt)}</span>
      <span>
        <span className="font-medium">{name}</span> {change}
        <span className="text-muted-foreground"> · {h.actorName ?? h.actor}</span>
      </span>
    </li>
  );
}

function historyValue(field: string, value: string): string {
  if (field === 'status' || field === 'priority') return label(value);
  if (field === 'baseline') {
    const [version, match] = value.split(' ');
    return match ? `${version} (${MATCH_TEXT[match] ?? match})` : value;
  }
  return value;
}

function Section({ title, children }: { title: string; children: ReactNode }): ReactNode {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}

function Row({ term, children }: { term: string; children: ReactNode }): ReactNode {
  return (
    <>
      <dt className="text-muted-foreground">{term}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  );
}
