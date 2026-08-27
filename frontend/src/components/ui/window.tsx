import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { CardAction, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

/** ax-pms 의 화면 한 칸. 제목·힌트·동작을 위에, 상태를 아래에 둔다. */
export function Window({
  title,
  chip,
  hint,
  status,
  action,
  bleed,
  scroll,
  innerClassName,
  className,
  children,
}: {
  title?: string;
  chip?: string;
  hint?: ReactNode;
  status?: ReactNode;
  action?: ReactNode;
  bleed?: boolean;
  scroll?: boolean;
  innerClassName?: string;
  className?: string;
  children: ReactNode;
}) {
  const hasHeader = Boolean(title || hint || action);

  return (
    <section
      className={cn(
        'flex min-h-0 flex-col',
        hasHeader || !bleed ? 'pt-6' : null,
        status || !bleed ? 'pb-6' : null,
        className,
      )}
    >
      {hasHeader && (
        <CardHeader className={cn('shrink-0 pb-4', innerClassName)}>
          <CardTitle className="text-lg font-semibold tracking-tight flex min-w-0 items-center gap-2">
            <span className="truncate">{title}</span>
            {chip && <Badge variant="muted">{chip}</Badge>}
          </CardTitle>

          {hint && <p className="text-muted-foreground text-sm font-normal">{hint}</p>}

          {action && <CardAction className="flex items-center gap-1">{action}</CardAction>}
        </CardHeader>
      )}

      <CardContent className={cn('min-h-0 flex-1', bleed && 'px-0', scroll && 'overflow-y-auto')}>
        {children}
      </CardContent>

      {status && (
        <CardFooter className="text-muted-foreground text-sm shrink-0 pt-4">{status}</CardFooter>
      )}
    </section>
  );
}
