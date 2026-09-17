import { type ReactNode } from 'react';
import type { Components } from 'react-markdown';
import { Markdown } from '@/components/ui/markdown';
import { cn } from '@/lib/utils';
import { resolveWidgetRenderer } from '@/features/widgets/renderer-registry';
import { formatCell, rowValues } from '@/features/widgets/widget-data';
import type { MessageSourceResponse, SseInfographicEvent, WidgetSpec } from '@/types/api';

export interface FootnoteSegment {
  kind: 'text' | 'footnote' | 'figure';
  value: string;
  footnoteNo: number | null;
  /** kind 가 figure 일 때 그림 자리 번호 */
  slot?: number;
}

/**
 * 본문을 글·각주·그림 자리로 나눈다.
 *
 * 각주는 `[1]`, 그림 자리는 `[그림 1]` 이다. 서버가 본문에 표식을 놓고 그림을 따로 보내면,
 * 화면은 그 자리에 위젯 렌더러를 끼운다(ARC-013). 표식 뒤의 자리는 문단을 끊는다.
 */
export function parseFootnotes(content: string): FootnoteSegment[] {
  const segments: FootnoteSegment[] = [];
  const re = /\[그림\s*(\d{1,2})\]|\[(\d{1,2})\]/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) {
      segments.push({ kind: 'text', value: content.slice(last, match.index), footnoteNo: null });
    }
    if (match[1] !== undefined) {
      segments.push({
        kind: 'figure',
        value: match[0],
        footnoteNo: null,
        slot: Number(match[1]),
      });
    } else {
      segments.push({ kind: 'footnote', value: match[0], footnoteNo: Number(match[2]) });
    }
    last = match.index + match[0].length;
  }
  if (last < content.length) {
    segments.push({ kind: 'text', value: content.slice(last), footnoteNo: null });
  }
  return segments;
}

const FOOTNOTE_HREF = '#fn-';

/**
 * 본문 조각을 마크다운 한 덩어리로 되돌린다. 아는 각주는 링크로 바꿔 렌더러가 버튼으로 그린다.
 * 답변은 문서에서 옮긴 글이라 강조·코드·목록 표기가 섞여 온다. 그대로 보이면 기호가 남는다.
 */
function toMarkdown(segments: FootnoteSegment[], known: Set<number>): string {
  return segments
    .map((seg) =>
      seg.kind === 'footnote' && seg.footnoteNo !== null && known.has(seg.footnoteNo)
        ? `[${seg.footnoteNo}](${FOOTNOTE_HREF}${seg.footnoteNo})`
        : seg.value,
    )
    .join('');
}

/** 각주 링크만 버튼으로. 그 밖의 링크는 기본 렌더러가 새 창으로 연다. */
function footnoteLinks(onFootnoteClick?: (footnoteNo: number) => void): Partial<Components> {
  return {
    a: ({ href, children }) => {
      if (href?.startsWith(FOOTNOTE_HREF)) {
        const no = Number(href.slice(FOOTNOTE_HREF.length));
        return (
          <button
            type="button"
            title={`[${no}] 근거 보기`}
            className="text-primary hover:bg-accent focus-visible:bg-accent text-xs font-semibold tracking-wide mx-0.5 rounded-sm px-1 align-super font-mono transition-colors"
            onClick={() => onFootnoteClick?.(no)}
          >
            {no}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="text-primary hover:underline">
          {children}
        </a>
      );
    },
  };
}

export function AnswerBody({
  content,
  sources,
  infographics,
  onFootnoteClick,
}: {
  content: string;
  sources: MessageSourceResponse[];
  /** 답변에 딸린 그림들. 값은 서버가 DB 에서 뽑아 보낸다. */
  infographics?: SseInfographicEvent[] | null;
  onFootnoteClick?: (footnoteNo: number) => void;
}): ReactNode {
  const known = new Set(sources.map((s) => s.footnoteNo));
  const made = infographics ?? [];
  const bySlot = new Map(made.map((b) => [b.slot, b]));
  // 본문을 그림 자리에서 끊는다. 표식 앞뒤 글은 각각 한 문단이고, 그 사이에 그림이 들어간다.
  const parts: { text: FootnoteSegment[]; figure: SseInfographicEvent | null }[] = [];
  let buffer: FootnoteSegment[] = [];
  for (const seg of parseFootnotes(content)) {
    if (seg.kind === 'figure') {
      const block = seg.slot === undefined ? undefined : bySlot.get(seg.slot);
      if (block) {
        parts.push({ text: buffer, figure: block });
        bySlot.delete(seg.slot as number);
        buffer = [];
        continue;
      }
      // 그림이 안 온 표식은 글에서 지운다. 사용자에게 [그림 1] 이라는 글자를 보일 이유가 없다
      continue;
    }
    buffer.push(seg);
  }
  // 본문이 자리를 안 잡은 그림은 끝에 붙인다
  const leftovers = made.filter((b) => bySlot.has(b.slot));
  parts.push({ text: buffer, figure: null });

  return (
    <>
      {parts.map((part, pi) => (
        <div key={pi}>
          {part.text.some((seg) => seg.value.trim() !== '') && (
            <Markdown components={footnoteLinks(onFootnoteClick)}>
              {toMarkdown(part.text, known)}
            </Markdown>
          )}
          {part.figure && <InfographicBlock infographic={part.figure} />}
        </div>
      ))}
      {leftovers.map((block) => (
        <InfographicBlock key={block.slot} infographic={block} />
      ))}
    </>
  );
}

/** 답변에 딸려 온 인포그래픽. 값은 답변이 싣고 오고, 그림은 대시보드 위젯 렌더러를 그대로 쓴다. */
function InfographicBlock({ infographic }: { infographic: SseInfographicEvent }): ReactNode {
  const Renderer = resolveWidgetRenderer(infographic.template);
  const spec = {
    template: infographic.template,
    title: infographic.title,
    query: null as unknown as WidgetSpec['query'],
    options: null,
  };
  return (
    <figure className="border-border mt-4 rounded-md border p-4">
      {infographic.title && (
        <figcaption className="text-xs font-semibold tracking-wide text-muted-foreground mb-3">
          {infographic.title}
        </figcaption>
      )}
      <Renderer spec={spec} data={infographic.data} />
      {infographic.template !== 'DATA_TABLE' && <ValueTable infographic={infographic} />}
      <figcaption className="text-xs font-semibold tracking-wide text-muted-foreground mt-3">
        {infographic.note ?? '연결된 도구·문서에서 수집한 값을 집계했습니다.'}
      </figcaption>
    </figure>
  );
}

/** 근거 산출물 칩. 원문은 오른쪽 자료 시트가 맡는다. */
export function SourceEvidence({
  sources,
  activeFootnote,
  onSelect,
}: {
  sources: MessageSourceResponse[];
  activeFootnote: number | null;
  onSelect: (footnoteNo: number) => void;
}): ReactNode {
  if (sources.length === 0) return null;

  return (
    <div className="mt-4">
      <p className="text-muted-foreground text-xs font-semibold tracking-wide mb-3">
        근거 산출물 · 누르면 오른쪽에서 원문을 보여줍니다
      </p>

      <ul className="flex flex-wrap gap-2">
        {sources.map((s) => {
          const isActive = s.footnoteNo === activeFootnote;
          return (
            <li key={s.docChunkId}>
              <button
                type="button"
                onClick={() => onSelect(s.footnoteNo)}
                className={cn(
                  'text-sm flex items-center gap-2 rounded-sm px-2 py-1 transition-colors',
                  isActive
                    ? 'bg-evidence-muted ring-evidence text-foreground ring-1'
                    : 'bg-accent text-muted-foreground hover:text-primary',
                )}
              >
                <span className="font-mono font-semibold">[{s.footnoteNo}]</span>
                <span className="max-w-56 truncate font-medium">{s.sourceLabel}</span>
                {s.pageNo !== null && (
                  <span className="text-muted-foreground text-xs font-semibold tracking-wide">
                    p.{s.pageNo}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * 그림에 쓰인 값 그대로의 표. 그림은 크기만 보여 주고 정확한 수를 감추므로,
 * 옮겨 적어야 할 때를 위해 접어서 함께 둔다. 여닫기는 <details> 가 알아서 한다.
 */
function ValueTable({ infographic }: { infographic: SseInfographicEvent }): ReactNode {
  const { columns, rows, total } = infographic.data;
  if (columns.length === 0 || rows.length === 0) return null;
  return (
    <details className="border-border/60 mt-3 border-t pt-2">
      <summary className="text-muted-foreground hover:text-foreground text-xs font-semibold tracking-wide cursor-pointer select-none">
        값 {rows.length}줄 보기
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="text-sm w-full border-collapse">
          <thead>
            <tr className="text-muted-foreground border-border border-b text-left">
              {columns.map((c) => (
                <th key={c.key} className="py-1 pr-4 font-medium whitespace-nowrap">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rowValues(rows).map((row, i) => (
              <tr key={i} className="border-border/50 border-b last:border-0">
                {columns.map((c) => (
                  <td key={c.key} className="tnum py-1 pr-4 whitespace-nowrap">
                    {formatCell(row[c.key])}
                  </td>
                ))}
              </tr>
            ))}
            {total && (
              <tr className="border-border border-t font-medium">
                {columns.map((c, i) => (
                  <td key={c.key} className="tnum py-1 pr-4 whitespace-nowrap">
                    {i === 0 ? '합계' : formatCell(total.values?.[c.key])}
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </details>
  );
}
