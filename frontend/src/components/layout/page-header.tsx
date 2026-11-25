import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GUIDE_NEW_TAB } from '@/features/help/guide-links';
import { cn } from '@/lib/utils';

/**
 * 화면 머리. ax-pms PageHeader 와 같은 짜임 — 제목은 크게, 동작은 오른쪽 아래 정렬.
 * 화면 설명은 머리에 적지 않고 매뉴얼로 보낸다(11-25). `guide` 는 `/guide/` 뒤의 `<문서>#<절>` 이고,
 * 주면 동작 맨 앞에 같은 모양의 [매뉴얼] 버튼이 붙는다.
 */
export function PageHeader({
  title,
  description,
  actions,
  guide,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  guide?: string;
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
      {(actions || guide) && (
        <div className="flex shrink-0 items-center gap-2 pb-4">
          {guide && (
            <Button asChild size="sm" variant="outline">
              <Link to={`/guide/${guide}`} {...GUIDE_NEW_TAB}>
                <BookOpen className="size-4" /> 매뉴얼
              </Link>
            </Button>
          )}
          {actions}
        </div>
      )}
    </div>
  );
}
