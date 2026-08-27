import { type ReactNode } from 'react';
import { Pagination } from '@/components/ui/pagination';
import type { PageResponse } from '@/types/api';

export function PaginationBar<T>({
  page,
  onChange,
}: {
  page: PageResponse<T>;
  onChange: (page: number) => void;
}): ReactNode {
  const cur = page.page;
  const total = Math.max(page.totalPages, 1);
  const go = (p: number) => onChange(Math.min(Math.max(p, 0), total - 1));
  return (
    <div className="flex items-center justify-between gap-2 px-4 py-2 text-sm md:px-6">
      <span className="text-muted-foreground">
        총 {page.totalElements.toLocaleString()}건 · {cur + 1}/{total}페이지
      </span>
      <Pagination page={cur} totalPages={total} onChange={go} />
    </div>
  );
}
