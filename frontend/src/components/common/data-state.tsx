import { type ReactNode } from 'react';
import { isApiError } from '@/lib/api-error';

export interface DataStateLike<T> {
  data: T | null | undefined;
  error: unknown;
  loading: boolean;
}

// 불러오는 중·오류·비어 있음. 문구와 짜임은 ax-pms LoadState 를 따른다.
export function LoadingState({ skeleton }: { skeleton?: ReactNode }): ReactNode {
  return (
    <>
      {skeleton ?? (
        <p className="text-muted-foreground text-sm py-10 text-center" role="status">
          자료를 불러오는 중입니다.
        </p>
      )}
    </>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}): ReactNode {
  const msg = isApiError(error) ? error.message : '오류가 발생했습니다.';
  const code = isApiError(error) ? error.code : '';
  return (
    <div className="py-10 text-center" role="alert">
      <p className="text-destructive text-sm font-medium">{msg}</p>
      <p className="text-muted-foreground text-sm mt-1">잠시 후 다시 시도해 주십시오.</p>
      {code && (
        <p className="text-muted-foreground text-xs font-semibold tracking-wide mt-1 font-mono">
          {code}
        </p>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry} className="text-primary text-sm mt-2 font-medium">
          다시 불러오기
        </button>
      )}
    </div>
  );
}

export function EmptyState({ text, action }: { text: string; action?: ReactNode }): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
      <p className="text-muted-foreground text-sm">{text}</p>
      {action}
    </div>
  );
}

export function DataState<T>({
  state,
  skeleton,
  empty,
  onRetry,
  children,
}: {
  state: DataStateLike<T>;
  skeleton?: ReactNode;
  empty?: { text: string; action?: ReactNode };
  onRetry?: () => void;
  children: (data: T) => ReactNode;
}): ReactNode {
  if (state.loading && state.data == null) return <LoadingState skeleton={skeleton} />;
  if (state.error) return <ErrorState error={state.error} onRetry={onRetry} />;
  if (state.data == null || (Array.isArray(state.data) && state.data.length === 0)) {
    return empty ? <EmptyState text={empty.text} action={empty.action} /> : null;
  }
  return <>{children(state.data)}</>;
}
