import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** 화면 머리. ax-pms PageHeader 와 같은 짜임 — 제목은 크게, 힌트는 한 줄 아래, 동작은 오른쪽 아래 정렬. */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}): ReactNode {
  return (
    <div className={cn('flex flex-wrap items-end justify-between gap-x-4 gap-y-3', className)}>
      <div className="min-w-0 py-4">
        <h1 className="text-foreground text-2xl font-bold tracking-tight min-w-0 truncate">
          {title}
        </h1>
        {description && <p className="text-muted-foreground text-sm mt-1">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2 pb-4">{actions}</div>}
    </div>
  );
}
