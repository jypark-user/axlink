import { useMemo, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { fetchAllPages } from '@/lib/paging';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { IssueResponse, IssueSummaryResponse, PageResponse } from '@/types/api';

/** 이 화면이 세는 범위. 요구사항 라벨이 붙은 원천 이슈는 요구사항으로 가서 여기 없다. */
const GENERAL_ISSUE_SCOPE = '요구사항으로 분류된 항목 제외';
const EMPTY_TEXT = '수집된 일반 이슈가 없습니다. 연동을 붙이면 도구의 이슈가 여기 쌓입니다.';

export function IssuesPage(): ReactNode {
  const { project } = useProjectContext();

  // 카드는 서버가 사업 전체를 센 값이다. 표가 받아 온 행 수와 상관없다.
  const summary = useAsync<IssueSummaryResponse>(
    () => api.get<IssueSummaryResponse>(`/projects/${project.id}/issues/summary`),
    [project.id],
  );
  // 표는 검색·정렬을 손에서 하므로 끝까지 받는다.
  const list = useAsync<IssueResponse[]>(
    () =>
      fetchAllPages((page, size) =>
        api.get<PageResponse<IssueResponse>>(
          `/projects/${project.id}/issues${toQueryString({ page, size })}`,
        ),
      ),
    [project.id],
  );

  const columns = useMemo(() => buildColumns(), []);

  return (
    <>
      <PageHeader
        title="일반 이슈"
        description={`${GENERAL_ISSUE_SCOPE}. 요구사항은 사업 개요의 요구사항과 추적 화면에서 봅니다.`}
      />
      <div className="@container flex flex-col gap-5">
        <DataState state={summary} onRetry={summary.reload}>
          {(n) => (
            <div className="grid grid-cols-2 gap-3 @2xl:grid-cols-4">
              <MetricCard term="열린 일반 이슈" value={n.open} hint={`전체 ${n.total}건`} />
              <MetricCard
                term="심각·높음"
                value={n.heavyOpen}
                hint="열린 것 중"
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
            />
          )}
        </DataState>
      </div>
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
      cell: ({ row }) =>
        row.original.severity ? (
          <Badge variant={badgeVariantFor(row.original.severity)}>
            {label(row.original.severity)}
          </Badge>
        ) : (
          '-'
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
      header: '원문',
      cell: ({ row }) =>
        row.original.source.externalUrl ? (
          <a
            className="text-primary inline-flex items-center gap-1 hover:underline"
            href={row.original.source.externalUrl}
            target="_blank"
            rel="noreferrer"
          >
            {row.original.source.tool} <ExternalLink className="size-3" />
          </a>
        ) : (
          <span className="text-muted-foreground">{row.original.source.tool}</span>
        ),
    },
  ];
}
