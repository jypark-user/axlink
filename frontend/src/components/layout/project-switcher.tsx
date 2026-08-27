import { useMemo, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SearchInput } from '@/components/ui/search-input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { api } from '@/lib/http';
import { cn } from '@/lib/utils';
import { formatPeriod } from '@/lib/format';
import { label } from '@/lib/labels';
import { useAsync } from '@/lib/use-async';
import type { PageResponse, ProjectSummaryResponse } from '@/types/api';

export function ProjectSwitcher(): ReactNode {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const currentId = pathname.match(/^\/p\/([^/]+)/)?.[1];

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const projects = useAsync<PageResponse<ProjectSummaryResponse>>(
    () => api.get<PageResponse<ProjectSummaryResponse>>('/projects?size=100'),
    [],
  );

  const all = useMemo(() => projects.data?.content ?? [], [projects.data]);
  const current = all.find((p) => p.id === currentId);

  const shown = useMemo(() => {
    const running = all.filter((p) => p.status !== 'CLOSED');
    const needle = query.trim();
    const matched = needle
      ? running.filter((p) => p.name.includes(needle) || p.clientOrgName.includes(needle))
      : running;
    return [...matched].sort((a, b) => a.name.localeCompare(b.name));
  }, [all, query]);

  const pick = (projectId: string) => {
    setOpen(false);
    void navigate(`/p/${projectId}`);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery('');
      }}
    >
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="text-foreground hover:bg-accent border-border flex min-w-0 items-center justify-between gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors sm:min-w-44"
      >
        <span className="min-w-0 truncate">{current?.name ?? '사업 선택'}</span>
        <ChevronDown className="text-muted-foreground size-4 shrink-0" />
      </button>

      <DialogContent className="max-h-[78vh] gap-0 p-0 sm:max-w-3xl">
        <DialogHeader className="px-6 pt-5 pb-4">
          <DialogTitle>사업 선택</DialogTitle>
        </DialogHeader>

        <div className="mx-6 mb-4 shrink-0">
          <SearchInput
            autoFocus
            value={query}
            onValueChange={setQuery}
            placeholder="사업명 · 발주사로 찾기"
          />
        </div>

        <div className="border-border/60 min-h-0 flex-1 overflow-y-auto border-t">
          {shown.length === 0 ? (
            <p className="text-muted-foreground px-6 py-16 text-center text-sm">
              {projects.loading
                ? '불러오는 중…'
                : query.trim()
                  ? '찾는 사업이 없습니다.'
                  : '사업이 없습니다.'}
            </p>
          ) : (
            <Table>
              <TableHeader className="bg-card sticky top-0 z-10">
                <TableRow>
                  <TableHead className="px-6">사업명</TableHead>
                  <TableHead className="hidden px-4 sm:table-cell">발주기관</TableHead>
                  <TableHead className="hidden px-6 whitespace-nowrap md:table-cell">
                    기간
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shown.map((p) => {
                  const active = p.id === currentId;
                  return (
                    <TableRow
                      key={p.id}
                      tabIndex={0}
                      aria-current={active ? 'true' : undefined}
                      onClick={() => pick(p.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          pick(p.id);
                        }
                      }}
                      className={cn('cursor-pointer', active && 'bg-accent')}
                    >
                      <TableCell className="px-6 py-3.5">
                        <span
                          className={cn(
                            'block text-sm font-medium',
                            active ? 'text-primary' : 'text-foreground',
                          )}
                        >
                          {p.name}
                        </span>
                        <span className="text-muted-foreground text-xs">{label(p.status)}</span>
                      </TableCell>
                      <TableCell className="text-muted-foreground hidden px-4 py-3.5 text-sm sm:table-cell">
                        {p.clientOrgName}
                      </TableCell>
                      <TableCell className="text-muted-foreground hidden px-6 py-3.5 text-sm whitespace-nowrap md:table-cell">
                        {formatPeriod(p.startDate, p.endDate)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>

        <DialogFooter className="border-border/60 border-t p-0 sm:justify-center">
          <Button
            variant="ghost"
            className="w-full rounded-none py-3.5"
            onClick={() => {
              setOpen(false);
              void navigate('/projects');
            }}
          >
            모든 사업 보기
            <ChevronRight className="size-4" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
