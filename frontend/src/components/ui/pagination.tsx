import { type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * 보여 줄 쪽 번호. 쪽이 많아도 자리는 7칸으로 고정하고, 끊긴 구간은 'gap' 으로 표시한다.
 * 번호는 0 부터 센다 — 화면에는 +1 해서 쓴다.
 */
export function pageWindow(current: number, total: number): (number | 'gap')[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i);
  }
  const out: (number | 'gap')[] = [0];
  const start = Math.max(1, Math.min(current - 1, total - 5));
  const end = Math.min(total - 2, Math.max(current + 1, 4));
  if (start > 1) out.push('gap');
  for (let i = start; i <= end; i++) out.push(i);
  if (end < total - 2) out.push('gap');
  out.push(total - 1);
  return out;
}

/** 쪽 번호 버튼 줄. 이전·다음 대신 번호를 직접 누른다. */
export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}): ReactNode {
  if (totalPages <= 1) return null;
  return (
    <nav aria-label="쪽 이동" className="flex items-center gap-1">
      {pageWindow(page, totalPages).map((slot, i) =>
        slot === 'gap' ? (
          <span key={`gap-${i}`} className="text-muted-foreground px-1 text-sm select-none">
            …
          </span>
        ) : (
          <Button
            key={slot}
            size="sm"
            variant={slot === page ? 'default' : 'ghost'}
            aria-current={slot === page ? 'page' : undefined}
            className={cn('tnum size-8 p-0', slot !== page && 'text-muted-foreground')}
            onClick={() => onChange(slot)}
          >
            {slot + 1}
          </Button>
        ),
      )}
    </nav>
  );
}
