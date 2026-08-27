import type { ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

/** ax-pms 화면 뼈대 — 스스로 스크롤하는 한 장, 가운데 정렬된 폭, 12칸 격자. */
export type TileSpan = 3 | 4 | 6 | 8 | 9 | 12;

const spanClass: Record<TileSpan, string> = {
  3: '@3xl:col-span-4 @6xl:col-span-3',
  4: '@3xl:col-span-6 @6xl:col-span-4',
  6: '@3xl:col-span-6',
  8: '@3xl:col-span-12 @6xl:col-span-8',
  9: '@3xl:col-span-8 @6xl:col-span-9',
  12: '@3xl:col-span-12',
};

export function Page({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('@container h-full overflow-y-auto', className)}>{children}</div>;
}

export function PageWidth({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('mx-auto w-full max-w-7xl px-6', className)}>{children}</div>;
}

export function PageGrid({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <PageWidth className="@container pb-6">
      <div className={cn('grid grid-cols-1 items-start gap-3 @3xl:grid-cols-12', className)}>
        {children}
      </div>
    </PageWidth>
  );
}

export const tileSurface = 'min-w-0 gap-0 overflow-hidden py-0';

export function Tile({
  span = 12,
  className,
  children,
}: {
  span?: TileSpan;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card className={cn(tileSurface, 'empty:hidden', spanClass[span], className)}>{children}</Card>
  );
}
