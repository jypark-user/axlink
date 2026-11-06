import { useMemo, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { fetchAllPages } from '@/lib/paging';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import { localToday, milestoneText } from '@/features/issues/milestone-text';
import type {
  IssueResponse,
  IssueSourceCount,
  IssueSummaryResponse,
  PageResponse,
  SourceRef,
} from '@/types/api';

/** 이 화면이 세는 범위. 명세서 등록 전에 요구사항으로 만든 이슈는 요구사항 화면에 있다. */
const GENERAL_ISSUE_SCOPE = '수집한 이슈입니다';
const EMPTY_TEXT = '수집된 일반 이슈가 없습니다. 연동을 붙이면 도구의 이슈가 여기 쌓입니다.';
const ALL_CONNECTIONS = 'ALL';
const TOOL_NAME: Record<string, string> = {
  GITHUB: 'GitHub',
  REDMINE: 'Redmine',
  UPLOAD: '업로드',
  MANUAL: '수기',
};

const toolName = (tool: string | null | undefined): string =>
  tool ? (TOOL_NAME[tool] ?? tool) : '-';

/** 도구 번호. 저장소·프로젝트와 같이 적어야 GH-5 가 둘일 때 어느 쪽인지 안다 */
const sourceNumber = (source: SourceRef): string | null => {
  if (!source.number) return null;
  return source.target ? `${source.target} #${source.number}` : `#${source.number}`;
};

export function IssuesPage(): ReactNode {
  const { project } = useProjectContext();
  // 같은 도구의 연결이 여럿이면 GH-5 가 둘일 수 있다. 연결을 골라 따로 본다(GH-140)
  const [connectionId, setConnectionId] = useState<string>(ALL_CONNECTIONS);
  const [selected, setSelected] = useState<IssueResponse | null>(null);
  const filter = connectionId === ALL_CONNECTIONS ? undefined : connectionId;

  // 카드는 서버가 사업 전체(연결을 고르면 그 연결)를 센 값이다. 표가 받아 온 행 수와 상관없다.
  const summary = useAsync<IssueSummaryResponse>(
    () =>
      api.get<IssueSummaryResponse>(
        `/projects/${project.id}/issues/summary${toQueryString({ connectionId: filter })}`,
      ),
    [project.id, filter],
  );
  // 표는 검색·정렬을 손에서 하므로 끝까지 받는다.
  const list = useAsync<IssueResponse[]>(
    () =>
      fetchAllPages((page, size) =>
        api.get<PageResponse<IssueResponse>>(
          `/projects/${project.id}/issues${toQueryString({ page, size, connectionId: filter })}`,
        ),
      ),
    [project.id, filter],
  );

  const columns = useMemo(() => buildColumns(), []);
  // 고르기 목록은 연결을 골라도 사업 전체 연결이 온다. 도구에서 오지 않은 묶음은 고를 수 없다
  const connections = (summary.data?.sources ?? []).filter(
    (s): s is IssueSourceCount & { connectionId: string } => s.connectionId !== null,
  );

  return (
    <>
      <PageHeader
        title="일반 이슈"
        description={`${GENERAL_ISSUE_SCOPE}. 예전에 요구사항으로 만든 이슈는 요구사항 화면에서 봅니다.`}
      />
      <div className="@container flex flex-col gap-5">
        {connections.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="win-label">연결</span>
            <Select value={connectionId} onValueChange={setConnectionId}>
              <SelectTrigger className="w-full max-w-md" aria-label="연결로 거르기">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_CONNECTIONS}>전체 연결</SelectItem>
                {connections.map((c) => (
                  <SelectItem key={c.connectionId} value={c.connectionId}>
                    {toolName(c.tool)} · {c.name} ({c.target}) {c.count}건
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <DataState state={summary} onRetry={summary.reload}>
          {(n) => (
            <div className="grid grid-cols-2 gap-3 @2xl:grid-cols-4">
              <MetricCard term="열린 일반 이슈" value={n.open} hint={`전체 ${n.total}건`} />
              <MetricCard
                term="심각·높음"
                value={n.heavyOpen}
                hint={
                  n.unspecifiedOpen > 0
                    ? `열린 것 중 · 심각도 미지정 ${n.unspecifiedOpen}건 별도`
                    : '열린 것 중'
                }
                tone={n.heavyOpen > 0 ? 'text-destructive' : undefined}
              />
              <MetricCard
                term="담당 없음"
                value={n.unassignedOpen}
                hint="열린 것 중"
                tone={n.unassignedOpen > 0 ? 'text-warning' : undefined}
              />
              <MetricCard
                term="해결·닫힘"
                value={n.closed}
                hint={n.total > 0 ? `${Math.round((n.closed / n.total) * 100)}%` : '0%'}
              />
            </div>
          )}
        </DataState>

        <DataState
          state={list}
          onRetry={list.reload}
          // 배열이 비면 DataState 가 표 대신 이 문구를 낸다
          empty={{ text: EMPTY_TEXT }}
        >
          {(rows) => (
            <DataTable<IssueResponse, unknown>
              columns={columns}
              data={rows}
              filterColumn="title"
              filterPlaceholder="이슈 제목으로 찾기"
              pageSize={25}
              emptyText={EMPTY_TEXT}
              onRowClick={setSelected}
            />
          )}
        </DataState>
      </div>
      <IssueDetailSheet issue={selected} onClose={() => setSelected(null)} />
    </>
  );
}

/** 이슈 현황 한 칸. 숫자를 크게 두고 무엇을 센 값인지 아래에 적는다. */
function MetricCard({
  term,
  value,
  hint,
  tone,
}: {
  term: string;
  value: number;
  hint?: string;
  tone?: string;
}): ReactNode {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <p className="win-label truncate">{term}</p>
        <p className={`tnum mt-1 text-2xl font-semibold ${tone ?? 'text-foreground'}`}>{value}</p>
        {hint && (
          <p className="text-muted-foreground text-xs font-semibold tracking-wide mt-0.5">{hint}</p>
        )}
      </CardContent>
    </Card>
  );
}

/** 이슈 한 건. 목록 행의 값만 쓴다. 어느 연결의 무엇인지가 여기서 보여야 한다. */
function IssueDetailSheet({
  issue,
  onClose,
}: {
  issue: IssueResponse | null;
  onClose: () => void;
}): ReactNode {
  return (
    <Sheet open={issue !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="flex w-full flex-col gap-0 overflow-y-auto sm:max-w-xl">
        {issue && (
          <>
            <SheetHeader className="gap-2 px-6 pt-6 pb-5">
              <div className="flex items-center gap-2 pr-8">
                <span className="text-muted-foreground font-mono text-xs">{issue.key}</span>
                <Badge variant={badgeVariantFor(issue.status)}>{label(issue.status)}</Badge>
              </div>
              <SheetTitle className="text-lg">{issue.title}</SheetTitle>
              <SheetDescription>
                {toolName(issue.source.tool)}
                {issue.source.connectionName ? ` · ${issue.source.connectionName}` : ''}
              </SheetDescription>
            </SheetHeader>
            <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2.5 px-6 pb-6 text-sm">
              <DetailRow term="도구">{toolName(issue.source.tool)}</DetailRow>
              <DetailRow term="연결">{issue.source.connectionName ?? '-'}</DetailRow>
              <DetailRow term="저장소·프로젝트">
                <span className="font-mono text-xs">{issue.source.target ?? '-'}</span>
              </DetailRow>
              <DetailRow term="도구 번호">
                <span className="font-mono text-xs">
                  {issue.source.number ? `#${issue.source.number}` : '-'}
                </span>
              </DetailRow>
              <DetailRow term="원문">
                {issue.source.externalUrl ? (
                  <a
                    className="text-primary inline-flex items-center gap-1 break-all hover:underline"
                    href={issue.source.externalUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {issue.source.externalUrl} <ExternalLink className="size-3 shrink-0" />
                  </a>
                ) : (
                  '-'
                )}
              </DetailRow>
              <DetailRow term="심각도">
                {issue.severity ? label(issue.severity) : '미지정'}
                {issue.sourcePriority && (
                  <span className="text-muted-foreground">
                    {' '}
                    · 도구 우선순위 {issue.sourcePriority}
                  </span>
                )}
              </DetailRow>
              <DetailRow term="마일스톤">
                <MilestoneCell issue={issue} />
              </DetailRow>
              <DetailRow term="담당">{issue.assignee ?? '-'}</DetailRow>
              {issue.tracker && <DetailRow term="트래커">{issue.tracker}</DetailRow>}
              {(issue.requirementRefs?.length ?? 0) > 0 && (
                <DetailRow term="요구사항 ID">{issue.requirementRefs?.join(', ')}</DetailRow>
              )}
              {(issue.relations?.length ?? 0) > 0 && (
                <DetailRow term="이슈관계">
                  {issue.relations?.map((r) => `${r.type} ${r.issueKey}`).join(', ')}
                </DetailRow>
              )}
              <DetailRow term="수정일">
                <span className="tnum">{formatDateTime(issue.updatedAt)}</span>
              </DetailRow>
              {issue.resolvedAt && (
                <DetailRow term="해결일">
                  <span className="tnum">{formatDateTime(issue.resolvedAt)}</span>
                </DetailRow>
              )}
            </dl>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

/** 원천 마일스톤. 기한이 지났는데 열려 있으면 기한만 강조한다(지연 판정은 하지 않는다). */
function MilestoneCell({ issue }: { issue: IssueResponse }): ReactNode {
  const m = milestoneText(issue.milestone, localToday());
  if (!issue.milestone) return <span className="text-muted-foreground text-xs">{m.text}</span>;
  return (
    <span
      className="text-xs"
      title={m.overdue ? '기한이 지났고 원천에서 아직 열려 있습니다' : undefined}
    >
      {issue.milestone.title}
      {m.due && (
        <span className={m.overdue ? 'text-warning font-medium' : 'text-muted-foreground'}>
          {' '}
          · {m.due}
        </span>
      )}
      <span className="text-muted-foreground">
        {' '}
        · {issue.milestone.state === 'CLOSED' ? '완료' : '진행 중'}
      </span>
    </span>
  );
}

function DetailRow({ term, children }: { term: string; children: ReactNode }): ReactNode {
  return (
    <>
      <dt className="text-muted-foreground">{term}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  );
}

function buildColumns(): ColumnDef<IssueResponse, unknown>[] {
  return [
    {
      accessorKey: 'key',
      header: ({ column }) => <SortableHeader column={column}>이슈번호</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground font-mono text-xs">{row.original.key}</span>
      ),
    },
    {
      accessorKey: 'title',
      header: ({ column }) => <SortableHeader column={column}>제목</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-md truncate" title={row.original.title}>
          {row.original.title}
        </span>
      ),
    },
    {
      accessorKey: 'severity',
      header: ({ column }) => <SortableHeader column={column}>심각도</SortableHeader>,
      cell: ({ row }) => (
        <div className="flex flex-col items-start gap-0.5">
          {row.original.severity ? (
            <Badge variant={badgeVariantFor(row.original.severity)}>
              {label(row.original.severity)}
            </Badge>
          ) : (
            // 도구에 심각도가 없다. 낮다는 뜻이 아니다
            <Badge variant="muted" title="도구에 심각도 값이 없어 비워 두었습니다">
              미지정
            </Badge>
          )}
          {row.original.sourcePriority && (
            <span className="text-muted-foreground text-xs">
              도구 우선순위 {row.original.sourcePriority}
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
      cell: ({ row }) => (
        <Badge variant={badgeVariantFor(row.original.status)}>{label(row.original.status)}</Badge>
      ),
    },
    {
      id: 'milestone',
      header: '마일스톤',
      cell: ({ row }) => <MilestoneCell issue={row.original} />,
    },
    {
      accessorKey: 'assignee',
      header: '담당',
      cell: ({ row }) => row.original.assignee ?? '-',
    },
    {
      accessorKey: 'updatedAt',
      header: ({ column }) => <SortableHeader column={column}>수정일</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">{formatDateTime(row.original.updatedAt)}</span>
      ),
    },
    {
      id: 'source',
      header: '도구',
      cell: ({ row }) => {
        const source = row.original.source;
        const number = sourceNumber(source);
        // 원문 링크는 이슈마다 받은 주소다. 같은 GH-5 라도 저장소가 다르면 주소가 다르다
        return (
          <div className="flex flex-col items-start gap-0.5 text-xs">
            <span>
              {toolName(source.tool)}
              {source.connectionName && (
                <span className="text-muted-foreground"> · {source.connectionName}</span>
              )}
            </span>
            {number &&
              (source.externalUrl ? (
                <a
                  className="text-primary inline-flex items-center gap-1 font-mono hover:underline"
                  href={source.externalUrl}
                  target="_blank"
                  rel="noreferrer"
                  // 행을 누르면 상세가 열린다. 원문 링크는 상세를 열지 않고 바로 간다
                  onClick={(e) => e.stopPropagation()}
                >
                  {number} <ExternalLink className="size-3" />
                </a>
              ) : (
                <span className="text-muted-foreground font-mono">{number}</span>
              ))}
          </div>
        );
      },
    },
  ];
}
