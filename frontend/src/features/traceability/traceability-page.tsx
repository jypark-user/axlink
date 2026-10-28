import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink, PencilLine, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { SearchInput } from '@/components/ui/search-input';
import { DataState } from '@/components/common/data-state';
import { RequirementStatusBadge } from '@/components/common/requirement-status';
import { PaginationBar } from '@/components/common/pagination-bar';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { label } from '@/lib/labels';
import { toQueryString } from '@/lib/query';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import { useAuth } from '@/features/auth/auth-context';
import { StatusDecisionDialog } from '@/features/traceability/status-decision-dialog';
import {
  filterLabel,
  filterParams,
  implementedNote,
  NO_FILTER,
  rateText,
  sameFilter,
  sourceFilter,
  sourceStateWord,
  type RequirementFilter,
} from '@/features/traceability/requirement-filter';
import type {
  PageResponse,
  RequirementSummaryResponse,
  SourceState,
  SourceStateSummary,
  TraceCell,
  TraceLinkKind,
  TraceabilityRowResponse,
} from '@/types/api';
import type { BaselineStateResponse } from '@/types/api';
import { BaselineBanner } from '@/features/requirement-baseline/baseline-banner';

const PAGE_SIZE = 20;

export function TraceabilityPage(): ReactNode {
  const { project } = useProjectContext();
  const { me } = useAuth();
  // 요구사항 상태 지정은 발주기관이 한다(ARC-025). 용역사는 지정 결과와 사유만 본다
  const canDecide = me?.role === 'CLIENT' || me?.role === 'SUPER_ADMIN';
  const [deciding, setDeciding] = useState<TraceabilityRowResponse | null>(null);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState<RequirementFilter>(NO_FILTER);
  const [text, setText] = useState('');
  const [q, setQ] = useState('');

  // 찾기는 서버에서 한다. 표가 받은 한 쪽만 거르면 다른 쪽의 행은 못 찾는다.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(text.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [text]);

  // 목록 확정 상태(기준선). 미확정이면 지금 목록이 무엇인지 머리에 같이 적는다(GH-139)
  const baseline = useAsync<BaselineStateResponse>(
    () => api.get<BaselineStateResponse>(`/projects/${project.id}/requirement-baseline`),
    [project.id],
  );
  // 요약은 사업 전체를 서버가 센 값이다. 목록 조건·쪽과 상관없다.
  const summary = useAsync<RequirementSummaryResponse>(
    () => api.get<RequirementSummaryResponse>(`/projects/${project.id}/requirements/summary`),
    [project.id],
  );
  const state = useAsync<PageResponse<TraceabilityRowResponse>>(
    () =>
      api.get<PageResponse<TraceabilityRowResponse>>(
        `/projects/${project.id}/traceability${toQueryString({
          ...filterParams(filter),
          q: q || undefined,
          page,
          size: PAGE_SIZE,
        })}`,
      ),
    [project.id, page, filter, q],
  );

  const columns = useMemo(() => buildColumns(canDecide ? setDeciding : null), [canDecide]);
  const active = filterLabel(filter);
  const narrowed = active !== null || q !== '';
  const emptyText = narrowed ? '조건에 맞는 요구사항이 없습니다.' : '요구사항이 없습니다.';

  // 같은 칸을 다시 누르면 푼다. 조건이 바뀌면 첫 쪽부터 본다.
  const pick = (next: RequirementFilter) => {
    setFilter(sameFilter(next, filter) ? NO_FILTER : next);
    setPage(0);
  };
  const clear = () => {
    setFilter(NO_FILTER);
    setPage(0);
  };

  return (
    <>
      <PageHeader
        title="요구사항"
        description="요구사항마다 이어진 설계 문서, 코드 변경, 시험을 봅니다. 이어져 있다고 완료나 통과를 뜻하지는 않습니다. 근거가 사라진 연결은 붉게 표시합니다."
      />
      <div className="@container flex flex-col gap-5">
        {baseline.data && <BaselineBanner projectId={project.id} state={baseline.data} />}
        <DataState state={summary} onRetry={summary.reload}>
          {(n) => <Summary n={n} filter={filter} onPick={pick} />}
        </DataState>

        <div className="flex flex-wrap items-center gap-3">
          <SearchInput
            value={text}
            onValueChange={setText}
            placeholder="코드·요구사항으로 찾기"
            aria-label="코드·요구사항으로 찾기"
            className="max-w-xs"
          />
          {active && (
            <span className="inline-flex items-center gap-1 text-sm">
              <span className="text-muted-foreground">현재 필터</span>
              <Badge variant="primary">{active}</Badge>
              <Button size="sm" variant="ghost" onClick={clear} aria-label="필터 해제">
                <X className="size-4" /> 해제
              </Button>
            </span>
          )}
          {narrowed && state.data && (
            <span className="text-muted-foreground text-sm">
              조건에 맞는 {state.data.totalElements}건
              {summary.data ? ` · 사업 전체 ${summary.data.total}건` : ''}
            </span>
          )}
        </div>

        <DataState state={state} onRetry={state.reload}>
          {(data) =>
            data.content.length === 0 ? (
              <p className="text-muted-foreground py-10 text-center text-sm">{emptyText}</p>
            ) : (
              <>
                <DataTable<TraceabilityRowResponse, unknown>
                  columns={columns}
                  data={data.content}
                  paginated={false}
                  emptyText={emptyText}
                />
                <PaginationBar page={data} onChange={setPage} />
              </>
            )
          }
        </DataState>
      </div>
      <StatusDecisionDialog
        projectId={project.id}
        row={deciding}
        onOpenChange={(open) => {
          if (!open) setDeciding(null);
        }}
        onSaved={() => {
          summary.reload();
          state.reload();
        }}
      />
    </>
  );
}

/** 목록 위 요약. 칸을 누르면 그 조건으로 목록을 거른다. */
function Summary({
  n,
  filter,
  onPick,
}: {
  n: RequirementSummaryResponse;
  filter: RequirementFilter;
  onPick: (f: RequirementFilter) => void;
}): ReactNode {
  const is = (f: RequirementFilter) => sameFilter(f, filter);
  const linked = n.sources.filter((s) => s.connectionId !== null);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 @xl:grid-cols-3">
        <PickCard
          term="전체 요구사항"
          value={`${n.total}건`}
          hint="사업 전체"
          selected={filter.kind === 'all'}
          onClick={() => onPick(NO_FILTER)}
        />
        <PickCard
          term="검증 완료"
          value={`${n.verified}건`}
          hint={`${rateText(n.verifiedRate)} · 검증·인수 상태${
            n.decided > 0 ? ` · 발주기관 지정 ${n.decided}건 포함` : ''
          }`}
          selected={is({ kind: 'verified', value: true })}
          onClick={() => onPick({ kind: 'verified', value: true })}
        />
        <PickCard
          term="검증 미완료"
          value={`${n.notVerified}건`}
          hint="전체에서 검증 완료를 뺀 수"
          selected={is({ kind: 'verified', value: false })}
          onClick={() => onPick({ kind: 'verified', value: false })}
        />
      </div>

      <Card className="gap-0 py-3">
        <CardContent className="flex flex-col gap-2 px-4">
          <p className="win-label">상태별 건수</p>
          <div className="flex flex-wrap gap-1.5">
            {n.byStatus.map((s) => (
              <Chip
                key={s.status}
                selected={is({ kind: 'status', status: s.status })}
                disabled={s.count === 0}
                onClick={() => onPick({ kind: 'status', status: s.status })}
              >
                {label(s.status)} {s.count}
              </Chip>
            ))}
          </div>
          {n.implementedFromSourceClosed > 0 && (
            <p className="text-muted-foreground text-xs">{implementedNote(n)}</p>
          )}
        </CardContent>
      </Card>

      <Card className="gap-0 py-3">
        <CardContent className="flex flex-col gap-2 px-4">
          <p className="win-label">출처 이슈 상태</p>
          <p className="text-muted-foreground text-xs">
            명세서 등록 전에 이슈로 만든 요구사항은 그 이슈가 열렸는지 닫혔는지 따로 보여 줍니다.
            이슈가 닫혔다고 구현이 끝났다는 뜻은 아닙니다.
            {linked.length > 1 && ' 저장소마다 따로 셉니다.'}
          </p>
          {n.sources.length === 0 && (
            <p className="text-muted-foreground text-sm">요구사항이 없습니다.</p>
          )}
          {n.sources.map((s) => (
            <SourceRow key={s.connectionId ?? 'none'} s={s} is={is} onPick={onPick} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function SourceRow({
  s,
  is,
  onPick,
}: {
  s: SourceStateSummary;
  is: (f: RequirementFilter) => boolean;
  onPick: (f: RequirementFilter) => void;
}): ReactNode {
  const none: RequirementFilter = {
    kind: 'source',
    connectionId: null,
    sourceLabel: s.label,
    state: 'NONE',
  };
  const states = (['OPEN', 'CLOSED', 'UNKNOWN'] as const).filter(
    (st) => st !== 'UNKNOWN' || s.unknown > 0,
  );
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-sm font-medium">{s.label}</span>
      <span className="text-muted-foreground text-xs">요구사항 {s.total}건</span>
      {s.connectionId === null ? (
        <Chip selected={is(none)} onClick={() => onPick(none)}>
          목록 보기
        </Chip>
      ) : (
        states.map((st) => (
          <Chip
            key={st}
            selected={is(sourceFilter(s, st))}
            disabled={countOf(s, st) === 0}
            onClick={() => onPick(sourceFilter(s, st))}
          >
            {sourceStateWord(st)} {countOf(s, st)}
          </Chip>
        ))
      )}
    </div>
  );
}

function countOf(s: SourceStateSummary, st: Exclude<SourceState, 'NONE'>): number {
  if (st === 'OPEN') return s.open;
  if (st === 'CLOSED') return s.closed;
  return s.unknown;
}

function PickCard({
  term,
  value,
  hint,
  selected,
  onClick,
}: {
  term: string;
  value: string;
  hint: string;
  selected: boolean;
  onClick: () => void;
}): ReactNode {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        'bg-card hover:bg-accent rounded-md border px-4 py-3 text-left transition-colors',
        selected ? 'border-primary ring-primary/40 ring-1' : 'border-border',
      )}
    >
      <p className="win-label truncate">{term}</p>
      <p className="tnum text-foreground mt-1 text-2xl font-semibold">{value}</p>
      <p className="text-muted-foreground mt-0.5 text-xs font-semibold tracking-wide">{hint}</p>
    </button>
  );
}

function Chip({
  selected,
  disabled,
  onClick,
  children,
}: {
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}): ReactNode {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={cn(
        'tnum rounded-full border px-2.5 py-0.5 text-xs transition-colors',
        selected ? 'border-primary bg-primary-muted text-primary' : 'border-border hover:bg-accent',
        disabled && 'cursor-default opacity-50 hover:bg-transparent',
      )}
    >
      {children}
    </button>
  );
}

function buildColumns(
  onDecide: ((row: TraceabilityRowResponse) => void) | null,
): ColumnDef<TraceabilityRowResponse, unknown>[] {
  return [
    {
      accessorKey: 'requirementCode',
      header: ({ column }) => <SortableHeader column={column}>코드</SortableHeader>,
      cell: ({ row }) => <span className="font-mono text-xs">{row.original.requirementCode}</span>,
    },
    {
      accessorKey: 'requirementTitle',
      header: ({ column }) => <SortableHeader column={column}>요구사항</SortableHeader>,
      cell: ({ row }) => <TitleCell text={row.original.requirementTitle} />,
    },
    {
      accessorKey: 'requirementStatus',
      header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
      cell: ({ row }) => <StatusCell row={row.original} onDecide={onDecide} />,
    },
    {
      // 출처 이슈의 열림·닫힘. 위 상태 칸과 따로 읽는다
      accessorKey: 'sourceState',
      header: '출처 이슈',
      cell: ({ row }) => (
        <span
          className={cn(
            'text-xs',
            (row.original.sourceState === 'NONE' || row.original.sourceState === 'UNKNOWN') &&
              'text-muted-foreground',
          )}
        >
          {SOURCE_CELL[row.original.sourceState]}
        </span>
      ),
    },
    {
      id: 'designs',
      header: '설계 근거',
      cell: ({ row }) => (
        <Cells cells={row.original.designs} kind="DESIGNS" broken={row.original.brokenAt} />
      ),
    },
    {
      id: 'implements',
      header: '구현 관련 변경',
      cell: ({ row }) => (
        <Cells
          cells={row.original.implementsList}
          kind="IMPLEMENTS"
          broken={row.original.brokenAt}
        />
      ),
    },
    {
      id: 'tests',
      header: '시험 연결',
      cell: ({ row }) => (
        <Cells cells={row.original.tests} kind="TESTS" broken={row.original.brokenAt} />
      ),
    },
  ];
}

/** 상태 칸. 지정이 있으면 근거 상태와 사유를 함께 보이고, 발주기관에게는 지정 버튼을 둔다. */
function StatusCell({
  row,
  onDecide,
}: {
  row: TraceabilityRowResponse;
  onDecide: ((row: TraceabilityRowResponse) => void) | null;
}): ReactNode {
  const decision = row.requirementDecision;
  const evidence = row.requirementEvidenceStatus;
  return (
    <div className="flex flex-col items-start gap-1">
      <span title={decision ? `지정 사유: ${decision.reason}` : undefined}>
        <RequirementStatusBadge status={row.requirementStatus} basis={row.requirementStatusBasis} />
      </span>
      {decision && evidence && evidence !== row.requirementStatus && (
        <span className="text-muted-foreground text-[11px] leading-none">
          근거: {label(evidence)}
        </span>
      )}
      {onDecide && (
        <button
          type="button"
          onClick={() => onDecide(row)}
          className="text-primary inline-flex items-center gap-1 text-[11px] hover:underline"
          aria-label={`${row.requirementCode} 상태 지정`}
        >
          <PencilLine className="size-3" /> {decision ? '지정 변경' : '상태 지정'}
        </button>
      )}
    </div>
  );
}

const SOURCE_CELL: Record<SourceState, string> = {
  OPEN: '열림',
  CLOSED: '닫힘',
  UNKNOWN: '기록 없음',
  NONE: '없음',
};

/** 요구사항 제목. 두 줄까지 보이고, 누르면 전체를 펼친다. 마우스를 올려도 전체가 보인다. */
function TitleCell({ text }: { text: string }): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <button
      type="button"
      onClick={() => setOpen((v) => !v)}
      aria-expanded={open}
      title={open ? undefined : text}
      className={cn(
        'block max-w-md text-left whitespace-normal break-keep hover:underline',
        !open && 'line-clamp-2',
      )}
    >
      {text}
    </button>
  );
}

/** 근거가 이만큼 넘으면 앞 몇 개만 두고 나머지는 '더 보기' 로 접는다. */
const CELL_PREVIEW = 3;

/**
 * 빈 칸 문구. "없음" 은 설계·구현·시험이 없다는 판정처럼 읽힌다. 여기서 아는 것은 연결된 근거가
 * 없다는 사실뿐이다(ARC-024). 구현 칸은 구현 완료가 아니라 관련 변경, 시험 칸은 통과가 아니라 연결이다.
 */
const EMPTY_TEXT: Partial<Record<TraceLinkKind, string>> = {
  DESIGNS: '연결된 설계 근거 없음',
  IMPLEMENTS: '연결된 구현 관련 변경 없음',
  TESTS: '연결된 시험 없음',
};

/** 문서가 스스로 선언한 상태. 승인·설계 완료와 같지 않다. */
const DOC_STATUS_TAG: Record<string, string> = { DRAFT: '초안', UNKNOWN: '상태 미표기' };

/** 표 뼈대는 DataTable 이 만든다 — 여기서는 칸 안쪽만 그린다. */
function Cells({
  cells,
  kind,
  broken,
}: {
  cells: TraceCell[];
  kind: TraceLinkKind;
  broken: TraceLinkKind[];
}): ReactNode {
  const [all, setAll] = useState(false);
  const isBroken = broken.includes(kind);
  const hidden = cells.length - CELL_PREVIEW;
  const shown = all || hidden <= 0 ? cells : cells.slice(0, CELL_PREVIEW);
  return (
    <div className={cn('-mx-2 px-2 py-1', isBroken && 'bg-destructive/10')}>
      {cells.length === 0 ? (
        <span className="text-muted-foreground text-xs">{EMPTY_TEXT[kind] ?? '연결 없음'}</span>
      ) : (
        // 근거는 한 줄에 하나. 긴 커밋 제목은 끝을 말줄임하고, 마우스를 올리면 전체가 보인다
        <ul className="flex w-64 flex-col gap-0.5">
          {shown.map((c) => {
            const tags = [
              c.docStatus ? DOC_STATUS_TAG[c.docStatus] : undefined,
              c.qualifier ?? undefined,
            ].filter((t): t is string => Boolean(t));
            const name = c.section ? `${c.label} · ${c.section}` : c.label;
            return (
              <li key={c.targetId} className="min-w-0 text-xs" title={name}>
                <span className="flex min-w-0 items-center gap-1">
                  {c.externalUrl ? (
                    <a
                      className="flex min-w-0 items-center gap-1 hover:underline"
                      href={c.externalUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span className="truncate">{name}</span>
                      <ExternalLink className="text-muted-foreground size-3 shrink-0" />
                    </a>
                  ) : (
                    <span className="block truncate">{name}</span>
                  )}
                  {tags.map((t) => (
                    <span
                      key={t}
                      className="text-muted-foreground shrink-0 rounded border px-1 text-[10px]"
                    >
                      {t}
                    </span>
                  ))}
                </span>
              </li>
            );
          })}
          {hidden > 0 && (
            <li>
              <button
                type="button"
                onClick={() => setAll((v) => !v)}
                aria-expanded={all}
                className="text-primary text-xs hover:underline"
              >
                {all ? '접기' : `외 ${hidden}건 더 보기`}
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
