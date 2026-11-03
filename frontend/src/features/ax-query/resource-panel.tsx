import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ExternalLink, FileText, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SearchInput } from '@/components/ui/search-input';
import { Skeleton } from '@/components/ui/skeleton';
import { Window } from '@/components/ui/window';
import { cn } from '@/lib/utils';
import { appHref } from '@/lib/app-path';
import type { MessageSourceResponse } from '@/types/api';

/** 자료 칸에 펼 수 있는 것. ax-pms 의 PanelView 와 같은 구성이다. */
export type PanelView = 'library' | 'evidence' | 'dashboard' | 'traceability' | 'deliverables';

const DashboardPage = lazy(() =>
  import('@/features/dashboard/dashboard-page').then((m) => ({
    default: m.DashboardPage,
  })),
);
const TraceabilityPage = lazy(() =>
  import('@/features/traceability/traceability-page').then((m) => ({
    default: m.TraceabilityPage,
  })),
);
const DeliverablesPage = lazy(() =>
  import('@/features/deliverables/deliverables-page').then((m) => ({
    default: m.DeliverablesPage,
  })),
);

const SCREENS = {
  dashboard: {
    label: '진행 상황',
    detail: '진척 · 지표 · 리스크',
    render: () => <DashboardPage />,
  },
  traceability: {
    label: '요구사항 추적',
    detail: '요구사항 ↔ 설계 ↔ 시험',
    render: () => <TraceabilityPage />,
  },
  deliverables: {
    label: '산출물',
    detail: 'ISO/IEC 29110 산출물 22종',
    render: () => <DeliverablesPage />,
  },
} as const;

/** 근거 하나를 문서의 한 절처럼 다룬다. */
interface SourceDoc {
  id: string;
  label: string;
  blocks: MessageSourceResponse[];
}

const groupBySource = (sources: MessageSourceResponse[]): SourceDoc[] => {
  const byLabel = new Map<string, SourceDoc>();
  for (const s of sources) {
    const doc = byLabel.get(s.sourceLabel);
    if (doc) doc.blocks.push(s);
    else
      byLabel.set(s.sourceLabel, {
        id: s.sourceLabel,
        label: s.sourceLabel,
        blocks: [s],
      });
  }
  return [...byLabel.values()];
};

function PanelFrame({
  onBack,
  onClose,
  children,
}: {
  onBack?: () => void;
  onClose: () => void;
  children: ReactNode;
}): ReactNode {
  return (
    <div className="relative h-full min-h-0">
      <div className="border-border bg-card/95 absolute top-3 right-3 z-20 flex items-center gap-1 rounded-md border p-1 shadow-win backdrop-blur-sm">
        {onBack && (
          <Button
            variant="ghost"
            onClick={onBack}
            className="text-muted-foreground text-sm h-7 px-2 font-medium"
          >
            참고자료 목록
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          title="자료 닫기"
          className="text-muted-foreground size-7"
        >
          <span className="sr-only">자료 닫기</span>
          <X className="size-4" />
        </Button>
      </div>

      {children}
    </div>
  );
}

/** 근거 원문. ax-pms DocumentViewer 와 같은 구성 — 문서 탭 · 문서 내 검색 · 절 강조. */
function EvidenceViewer({
  docs,
  activeFootnote,
  onSelectFootnote,
  onBack,
  onClose,
}: {
  docs: SourceDoc[];
  activeFootnote: number | null;
  onSelectFootnote: (footnoteNo: number) => void;
  onBack: () => void;
  onClose: () => void;
}): ReactNode {
  const focusedDoc = docs.find((d) => d.blocks.some((b) => b.footnoteNo === activeFootnote));
  const [activeId, setActiveId] = useState(() => (focusedDoc ?? docs[0]).id);
  const [query, setQuery] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const activeDoc = docs.find((d) => d.id === activeId) ?? docs[0];

  const visible = useMemo(() => {
    const keyword = query.trim();
    if (!keyword) return activeDoc.blocks;
    return activeDoc.blocks.filter((b) => `${b.sourceLabel} ${b.snippet}`.includes(keyword));
  }, [activeDoc, query]);

  // 밖에서 다른 근거를 고르면 그 문서로 옮기고 검색을 푼다.
  useEffect(() => {
    if (!focusedDoc || focusedDoc.id === activeId) return;
    setActiveId(focusedDoc.id);
    setQuery('');
  }, [focusedDoc, activeId]);

  useEffect(() => {
    const target = scrollRef.current?.querySelector<HTMLElement>(
      `[data-footnote="${activeFootnote}"]`,
    );
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeFootnote, visible]);

  return (
    <Window
      bleed
      className="h-full"
      status={
        <>
          표시 중인 근거 <span className="tnum text-foreground font-medium">{visible.length}</span>{' '}
          / <span className="tnum">{activeDoc.blocks.length}</span>
        </>
      }
    >
      <div className="flex h-full min-h-0 flex-col">
        {docs.length > 1 && (
          <div
            role="tablist"
            aria-label="근거 산출물"
            className="border-border flex shrink-0 gap-1 overflow-x-auto border-b px-3 pt-2"
          >
            {docs.map((doc) => {
              const isActive = doc.id === activeDoc.id;
              return (
                <button
                  key={doc.id}
                  role="tab"
                  type="button"
                  aria-selected={isActive}
                  onClick={() => setActiveId(doc.id)}
                  className={cn(
                    'text-sm flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 font-medium whitespace-nowrap transition-colors',
                    isActive
                      ? 'border-primary text-primary bg-accent/50'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted border-transparent',
                  )}
                >
                  <FileText className="size-3.5" />
                  {doc.label}
                </button>
              );
            })}
          </div>
        )}

        {/* 머리는 두 줄로 나눈다 — 위는 오가는 단추, 아래는 지금 보는 문서와 찾기. */}
        <div className="border-border flex shrink-0 flex-col gap-3 border-b px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onBack}
              className="text-muted-foreground -ml-2 h-7 gap-1 px-2 font-medium"
            >
              <ChevronLeft className="size-4" />
              참고자료 목록
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              title="자료 닫기"
              className="text-muted-foreground -mr-1 size-7"
            >
              <span className="sr-only">자료 닫기</span>
              <X className="size-4" />
            </Button>
          </div>

          <div className="min-w-0">
            <h2 className="text-lg font-semibold tracking-tight text-foreground min-w-0 truncate">
              {activeDoc.label}
            </h2>
            <p className="text-muted-foreground text-sm mt-0.5 truncate">
              {activeDoc.blocks[0].projectName} · 근거{' '}
              <span className="tnum">{activeDoc.blocks.length}</span>개
            </p>
          </div>

          <div className="flex items-center gap-2">
            <SearchInput
              id="evidence-search"
              value={query}
              onValueChange={setQuery}
              placeholder="이 문서에서 찾기"
              aria-label="이 문서에서 찾기"
              className="min-w-0 flex-1 [&_input]:h-9"
            />
            {query.trim() && (
              <span
                aria-live="polite"
                className={cn(
                  'text-sm tnum shrink-0',
                  visible.length === 0 ? 'text-destructive' : 'text-muted-foreground',
                )}
              >
                {visible.length}건
              </span>
            )}
          </div>
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-5 lg:px-6">
          {visible.length === 0 ? (
            <p className="text-muted-foreground text-sm py-10 text-center">
              «{query}» 와 일치하는 근거가 없습니다. 다른 검색어를 입력해 보세요.
            </p>
          ) : (
            <article className="mx-auto max-w-2xl space-y-6">
              {visible.map((block) => {
                const isFocused = block.footnoteNo === activeFootnote;
                const url = block.externalUrl ?? block.documentUrl;
                return (
                  <section
                    key={block.docChunkId}
                    data-footnote={block.footnoteNo}
                    className="scroll-mt-6"
                  >
                    <header className="mb-2 flex items-baseline gap-2">
                      <button
                        type="button"
                        onClick={() => onSelectFootnote(block.footnoteNo)}
                        className="tnum text-primary text-lg font-semibold tracking-tight font-mono"
                      >
                        [{block.footnoteNo}]
                      </button>
                      {block.location && (
                        <span className="text-muted-foreground min-w-0 truncate text-sm">
                          {block.location}
                        </span>
                      )}
                      {url && (
                        <a
                          className="text-primary text-sm inline-flex items-center gap-1 hover:underline"
                          href={appHref(url)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          원문 <ExternalLink className="size-3" />
                        </a>
                      )}
                    </header>

                    <p
                      className={cn(
                        'text-foreground text-sm leading-[1.9]',
                        isFocused && 'evidence-hit -mx-2 px-2 py-2',
                      )}
                    >
                      {block.snippet}
                    </p>
                  </section>
                );
              })}
            </article>
          )}
        </div>
      </div>
    </Window>
  );
}

function ScreenFrame({
  onBack,
  onClose,
  children,
}: {
  onBack: () => void;
  onClose: () => void;
  children: ReactNode;
}): ReactNode {
  return (
    <PanelFrame onBack={onBack} onClose={onClose}>
      <div className="@container bg-background h-full min-h-0 overflow-y-auto p-3">
        <Suspense fallback={<Skeleton className="h-64 w-full" />}>{children}</Suspense>
      </div>
    </PanelFrame>
  );
}

/** 참고자료 목록. 근거와 사업 화면을 한자리에 둔다. */
function Library({
  docs,
  onOpenFootnote,
  onOpenScreen,
  onClose,
}: {
  docs: SourceDoc[];
  onOpenFootnote: (footnoteNo: number) => void;
  onOpenScreen: (view: PanelView) => void;
  onClose: () => void;
}): ReactNode {
  return (
    <PanelFrame onClose={onClose}>
      <Window scroll className="h-full">
        <section className="pt-6 pr-28">
          <h3 className="win-label">근거 산출물</h3>
          {docs.length === 0 ? (
            <p className="text-muted-foreground text-sm mt-2 leading-relaxed">
              아직 고른 근거가 없습니다. 답변의 각주나 근거 칩을 누르면 이 자리에 원문이 놓입니다.
            </p>
          ) : (
            <ul className="mt-2 space-y-1">
              {docs.map((doc) => (
                <li key={doc.id}>
                  <button
                    type="button"
                    onClick={() => onOpenFootnote(doc.blocks[0].footnoteNo)}
                    className="border-border hover:border-ring hover:bg-accent/50 bg-card flex w-full items-start gap-3 rounded-md border px-3 py-3 text-left transition-colors"
                  >
                    <FileText className="text-muted-foreground mt-1 size-4 shrink-0" />
                    <span className="min-w-0 flex-1">
                      <span className="text-foreground text-sm block font-medium">{doc.label}</span>
                      <span className="text-muted-foreground text-sm mt-1 block">
                        {doc.blocks[0].projectName} · 근거{' '}
                        <span className="tnum">{doc.blocks.length}</span>개
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="mt-6">
          <h3 className="win-label">사업 화면</h3>
          <ul className="mt-2 grid gap-2 @md:grid-cols-2">
            {(['dashboard', 'traceability', 'deliverables'] as const).map((view) => (
              <li key={view}>
                <button
                  type="button"
                  onClick={() => onOpenScreen(view)}
                  className="border-border hover:border-ring hover:bg-accent/50 bg-card block w-full rounded-md border px-3 py-3 text-left transition-colors"
                >
                  <span className="text-foreground text-sm block font-medium">
                    {SCREENS[view].label}
                  </span>
                  <span className="text-muted-foreground text-sm mt-1 block">
                    {SCREENS[view].detail}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </Window>
    </PanelFrame>
  );
}

export function ResourcePanel({
  view,
  onViewChange,
  sources,
  activeFootnote,
  onSelectFootnote,
  onClose,
}: {
  view: PanelView;
  onViewChange: (view: PanelView) => void;
  sources: MessageSourceResponse[];
  activeFootnote: number | null;
  onSelectFootnote: (footnoteNo: number) => void;
  onClose: () => void;
}): ReactNode {
  const docs = useMemo(() => groupBySource(sources), [sources]);
  const back = () => onViewChange('library');

  if (view === 'evidence' && docs.length > 0) {
    return (
      <EvidenceViewer
        docs={docs}
        activeFootnote={activeFootnote}
        onSelectFootnote={onSelectFootnote}
        onBack={back}
        onClose={onClose}
      />
    );
  }

  if (view === 'dashboard' || view === 'traceability' || view === 'deliverables') {
    return (
      <ScreenFrame onBack={back} onClose={onClose}>
        {SCREENS[view].render()}
      </ScreenFrame>
    );
  }

  return (
    <Library
      docs={docs}
      onOpenFootnote={(footnoteNo) => {
        onSelectFootnote(footnoteNo);
        onViewChange('evidence');
      }}
      onOpenScreen={onViewChange}
      onClose={onClose}
    />
  );
}
