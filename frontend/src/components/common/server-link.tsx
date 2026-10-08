import type { ReactNode } from 'react';
import { useToast } from '@/components/common/toaster';
import { apiDownloadPath, appHref } from '@/lib/app-path';
import { isApiError } from '@/lib/api-error';
import { download } from '@/lib/http';
import { cn } from '@/lib/utils';

/**
 * 서버가 준 주소로 가는 링크. 세 가지를 가른다.
 * - '/api/...' 내려받기: 토큰이 있어야 열려서 링크로 걸면 401 이다. 받아서 넘긴다.
 * - '/...' 화면 경로: 앱 경로(/ax-link/ 등) 아래로 옮긴다.
 * - 바깥 주소: 새 창으로 연다.
 */
export function ServerLink({
  url,
  filename,
  className,
  title,
  children,
}: {
  url: string;
  filename: string;
  className?: string;
  title?: string;
  children: ReactNode;
}): ReactNode {
  const { toast } = useToast();
  const path = apiDownloadPath(url);
  if (path) {
    return (
      <button
        type="button"
        title={title}
        className={cn('cursor-pointer text-left', className)}
        onClick={() => {
          download(path, filename).catch((e: unknown) =>
            toast({
              title: '파일을 내려받지 못했습니다.',
              description: isApiError(e) ? e.message : undefined,
              variant: 'error',
            }),
          );
        }}
      >
        {children}
      </button>
    );
  }
  return (
    <a href={appHref(url)} target="_blank" rel="noreferrer" title={title} className={className}>
      {children}
    </a>
  );
}
