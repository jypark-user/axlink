import { useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { Markdown } from '@/components/ui/markdown';
import { api, fetchBlob } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import type { HelpDocResponse, HelpEntryResponse } from '@/types/api';
import { assetPathOf, routeOf, sectionsOf, splitAnchor } from '@/features/help/guide-links';

const INDEX_SLUG = 'manual';

/**
 * 문서 안 화면 캡처. 그림 API 도 로그인이 필요해 img 에 주소를 바로 걸 수 없다. 토큰을 실어
 * 받아 잠시 쓰는 주소로 그린다. 대체 글은 그림 아래 설명으로도 보인다.
 */
function GuideImage({ src, alt }: { src?: string; alt?: string }): ReactNode {
  const path = src ? assetPathOf(src) : null;
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!path) return;
    let href: string | null = null;
    let alive = true;
    fetchBlob(path)
      .then((blob) => {
        href = URL.createObjectURL(blob);
        if (alive) setUrl(href);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      if (href) URL.revokeObjectURL(href);
    };
  }, [path]);
  const shown = path ? url : (src ?? null);
  return (
    <span className="my-2 block">
      {shown ? (
        <img
          src={shown}
          alt={alt ?? ''}
          className="border-border block max-w-full rounded-md border"
        />
      ) : (
        <span className="bg-muted text-muted-foreground block rounded-md px-3 py-6 text-center text-sm">
          {failed ? '그림을 불러오지 못했습니다' : '그림을 불러오는 중'}
        </span>
      )}
      {alt && <span className="text-muted-foreground mt-1 block text-xs">{alt}</span>}
    </span>
  );
}
/**
 * 사용 설명서. 글은 화면에 두지 않고 납품 문서(docs/40-manual)를 /api/help 로 받아 그린다.
 * 왼쪽에 문서 목록과 이 문서의 절, 오른쪽에 본문. 다른 화면은 `/guide/<문서>#<절>` 로 바로 연다.
 */
export function GuidePage(): ReactNode {
  const { slug = INDEX_SLUG } = useParams();
  const location = useLocation();
  const index = useAsync<HelpEntryResponse[]>(() => api.get<HelpEntryResponse[]>('/help'), []);
  const state = useAsync<HelpDocResponse>(
    () => api.get<HelpDocResponse>(`/help/${encodeURIComponent(slug)}`),
    [slug],
  );
  const files = new Map((index.data ?? []).map((e) => [e.file, e.slug]));

  // 주소의 #절 로 내려간다. 본문이 그려진 뒤에야 그 절이 있다
  const loaded = state.data?.slug;
  useEffect(() => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!loaded || !id) return;
    document.getElementById(id)?.scrollIntoView({ block: 'start' });
  }, [loaded, location.hash]);

  const heading =
    (Tag: 'h2' | 'h3', className: string) =>
    ({ children }: { children?: ReactNode }) => {
      const { id, children: text } = splitAnchor(children);
      return (
        <Tag id={id} className={cn('scroll-mt-4', className)}>
          {text}
        </Tag>
      );
    };

  return (
    <DataState state={state} onRetry={state.reload}>
      {(doc) => (
        <>
          <PageHeader
            title={doc.title}
            description={`사용 설명서 · 문서 갱신 ${formatDateTime(doc.updatedAt)}`}
          />
          <div className="flex flex-col gap-8 pb-16 lg:flex-row lg:items-start">
            <nav
              aria-label="설명서 목차"
              className="flex shrink-0 flex-col gap-4 text-sm lg:sticky lg:top-4 lg:w-56"
            >
              <ul className="flex flex-col gap-1">
                {(index.data ?? []).map((e) => (
                  <li key={e.slug}>
                    <Link
                      to={`/guide/${e.slug}`}
                      className={cn(
                        'hover:text-foreground block rounded-md px-2 py-1',
                        e.slug === doc.slug
                          ? 'bg-muted text-foreground font-medium'
                          : 'text-muted-foreground',
                      )}
                    >
                      {e.title}
                    </Link>
                  </li>
                ))}
              </ul>
              {sectionsOf(doc.markdown).length > 0 && (
                <ul className="border-border flex flex-col gap-1 border-l pl-3">
                  {sectionsOf(doc.markdown).map((s) => (
                    <li key={s.id}>
                      <Link
                        to={`#${s.id}`}
                        className="text-muted-foreground hover:text-foreground block py-0.5"
                      >
                        {s.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </nav>
            <article className="min-w-0 max-w-4xl flex-1">
              <Markdown
                components={{
                  h2: heading('h2', 'text-lg font-semibold tracking-tight mt-4 first:mt-0'),
                  h3: heading('h3', 'text-sm font-semibold mt-2 first:mt-0'),
                  img: ({ src, alt }) => (
                    <GuideImage src={typeof src === 'string' ? src : undefined} alt={alt} />
                  ),
                  a: ({ href, children }) => {
                    const to = href ? routeOf(href, files) : null;
                    return to ? (
                      <Link to={to} className="text-primary hover:underline">
                        {children}
                      </Link>
                    ) : (
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary hover:underline"
                      >
                        {children}
                      </a>
                    );
                  },
                }}
              >
                {doc.markdown}
              </Markdown>
            </article>
          </div>
        </>
      )}
    </DataState>
  );
}
