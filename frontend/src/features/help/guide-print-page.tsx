import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, FileDown } from 'lucide-react';
import { DataState } from '@/components/common/data-state';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import type { HelpDocResponse, HelpEntryResponse } from '@/types/api';
import { assetPathOf } from '@/features/help/guide-links';
import { GuideMarkdown } from '@/features/help/guide-markdown';

const ALL = 'all';
const IMAGE = /!\[[^\]]*\]\(([^)\s]+)\)/g;

// 인쇄 여백과 쪽 나눔. 화면 틀 밖의 페이지라 본문만 남는다
const PRINT_CSS = `
@page { size: A4; margin: 16mm 14mm; }
@media print {
  html, body { background: #fff !important; }
  tr, img, pre, blockquote { break-inside: avoid; }
  a { color: inherit !important; text-decoration: none !important; }
}
`;

interface PrintSet {
  entries: HelpEntryResponse[];
  docs: HelpDocResponse[];
}

/** 문서들이 품은 그림 중 그림 API 로 받는 것. 다 받아야 인쇄한다. */
function imagePaths(docs: HelpDocResponse[]): Set<string> {
  const out = new Set<string>();
  for (const d of docs) {
    for (const m of d.markdown.matchAll(IMAGE)) {
      const path = assetPathOf(m[1]);
      if (path) out.add(path);
    }
  }
  return out;
}

/**
 * 설명서 인쇄 화면. 메뉴·목차 없이 본문과 그림만 이어 그리고 브라우저 인쇄로 PDF 를 만든다.
 * `?doc=<문서>` 는 그 문서 하나, `?doc=all` 은 목차 순서대로 전체(표지 + 문서마다 새 쪽).
 * 서버에 변환 도구를 두지 않아 폐쇄망에서도 그대로 된다. 글꼴은 브라우저 것을 쓴다.
 */
export function GuidePrintPage(): ReactNode {
  const [params] = useSearchParams();
  const doc = params.get('doc') || ALL;
  const state = useAsync<PrintSet>(async () => {
    const entries = await api.get<HelpEntryResponse[]>('/help');
    const slugs = doc === ALL ? entries.map((e) => e.slug) : [doc];
    const docs = await Promise.all(
      slugs.map((s) => api.get<HelpDocResponse>(`/help/${encodeURIComponent(s)}`)),
    );
    return { entries, docs };
  }, [doc]);

  // 인쇄는 밝은 바탕으로 한다. 어두운 색은 .dark 와 시스템 설정(:root:not(.light)) 두 곳에서
  // 오므로 dark 를 떼고 light 를 붙인다. 테마 설정이 뒤에 다시 바꾸므로 이 화면에 있는 동안은
  // 바뀌는 대로 되돌리고, 떠나면 원래대로 둔다
  useEffect(() => {
    const root = document.documentElement;
    const before = { className: root.className, colorScheme: root.style.colorScheme };
    const light = () => {
      if (root.classList.contains('dark')) root.classList.remove('dark');
      if (!root.classList.contains('light')) root.classList.add('light');
      if (root.style.colorScheme !== 'light') root.style.colorScheme = 'light';
    };
    light();
    const watch = new MutationObserver(light);
    watch.observe(root, { attributes: true, attributeFilter: ['class', 'style'] });
    return () => {
      watch.disconnect();
      root.className = before.className;
      root.style.colorScheme = before.colorScheme;
    };
  }, []);

  const [settled, setSettled] = useState<Set<string>>(() => new Set());
  const onImageSettled = useCallback(
    (path: string) => setSettled((prev) => (prev.has(path) ? prev : new Set(prev).add(path))),
    [],
  );

  return (
    <div className="bg-background text-foreground min-h-screen">
      <style>{PRINT_CSS}</style>
      <DataState state={state} onRetry={state.reload}>
        {({ entries, docs }) => {
          const files = new Map(entries.map((e) => [e.file, e.slug]));
          const wanted = imagePaths(docs);
          const ready = [...wanted].every((p) => settled.has(p));
          const title = doc === ALL ? 'AX Link 사용 설명서' : docs[0]?.title;
          const back = doc === ALL ? '/guide' : `/guide/${doc}`;
          return (
            <>
              <div className="border-border bg-background sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b px-6 py-3 print:hidden">
                <Button asChild variant="ghost" size="sm">
                  <Link to={back}>
                    <ArrowLeft className="size-4" /> 설명서로
                  </Link>
                </Button>
                <span className="text-muted-foreground text-sm">
                  {ready
                    ? '인쇄 창에서 대상을 "PDF로 저장"으로 고르세요.'
                    : `그림을 불러오는 중 (${settled.size}/${wanted.size})`}
                </span>
                <Button className="ml-auto" disabled={!ready} onClick={() => window.print()}>
                  <FileDown className="size-4" /> PDF로 저장
                </Button>
              </div>

              <main className="mx-auto max-w-4xl px-6 py-10 print:max-w-none print:p-0">
                {doc === ALL && (
                  <section className="flex min-h-[60vh] flex-col justify-center gap-6 print:min-h-[240mm]">
                    <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
                    <ol className="ml-5 list-decimal space-y-1 text-sm">
                      {docs.map((d) => (
                        <li key={d.slug}>
                          {d.title}
                          <span className="text-muted-foreground">
                            {' '}
                            · 문서 갱신 {formatDateTime(d.updatedAt)}
                          </span>
                        </li>
                      ))}
                    </ol>
                    <p className="text-muted-foreground text-xs">
                      출력 {formatDateTime(new Date().toISOString())}
                    </p>
                  </section>
                )}
                {docs.map((d, i) => (
                  <article
                    key={d.slug}
                    className={doc === ALL || i > 0 ? 'mt-12 break-before-page print:mt-0' : ''}
                  >
                    <h1 className="mb-1 text-2xl font-bold tracking-tight">{d.title}</h1>
                    <p className="text-muted-foreground mb-6 text-xs">
                      문서 갱신 {formatDateTime(d.updatedAt)}
                    </p>
                    <GuideMarkdown
                      markdown={d.markdown}
                      files={files}
                      onImageSettled={onImageSettled}
                    />
                  </article>
                ))}
              </main>
            </>
          );
        }}
      </DataState>
    </div>
  );
}
