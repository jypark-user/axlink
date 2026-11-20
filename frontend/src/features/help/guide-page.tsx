import { useEffect, type ReactNode } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { FileDown } from 'lucide-react';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import type { HelpDocResponse, HelpEntryResponse } from '@/types/api';
import { sectionsOf } from '@/features/help/guide-links';
import { GuideMarkdown } from '@/features/help/guide-markdown';

const INDEX_SLUG = 'manual';

/**
 * 사용자 매뉴얼. 글은 화면에 두지 않고 납품 문서(docs/40-manual)를 /api/help 로 받아 그린다.
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

  return (
    <DataState state={state} onRetry={state.reload}>
      {(doc) => (
        <>
          <PageHeader
            title={doc.title}
            description={`사용자 매뉴얼 · 문서 갱신 ${formatDateTime(doc.updatedAt)}`}
            actions={
              <>
                <Button asChild variant="outline">
                  <Link to={`/guide/print?doc=${doc.slug}`}>
                    <FileDown className="size-4" /> 이 문서 PDF
                  </Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/guide/print?doc=all">
                    <FileDown className="size-4" /> 전체 PDF
                  </Link>
                </Button>
              </>
            }
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
              <GuideMarkdown markdown={doc.markdown} files={files} />
            </article>
          </div>
        </>
      )}
    </DataState>
  );
}
