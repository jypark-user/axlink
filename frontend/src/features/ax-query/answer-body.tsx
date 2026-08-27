import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { resolveWidgetRenderer } from '@/features/widgets/renderer-registry';
import { formatCell, rowValues } from '@/features/widgets/widget-data';
import type { MessageSourceResponse, SseInfographicEvent, WidgetSpec } from '@/types/api';

export interface FootnoteSegment {
  kind: 'text' | 'footnote';
  value: string;
  footnoteNo: number | null;
}

export function parseFootnotes(content: string): FootnoteSegment[] {
  const segments: FootnoteSegment[] = [];
  const re = /\[(\d{1,2})\]/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) {
      segments.push({ kind: 'text', value: content.slice(last, match.index), footnoteNo: null });
    }
    segments.push({ kind: 'footnote', value: match[0], footnoteNo: Number(match[1]) });
    last = match.index + match[0].length;
  }
  if (last < content.length) {
    segments.push({ kind: 'text', value: content.slice(last), footnoteNo: null });
  }
  return segments;
}

export function AnswerBody({
  content,
  sources,
  infographic,
  onFootnoteClick,
}: {
  content: string;
  sources: MessageSourceResponse[];
  /** 답변에 딸린 그림. 값은 서버가 DB 에서 뽑아 보낸다. */
  infographic?: SseInfographicEvent | null;
  onFootnoteClick?: (footnoteNo: number) => void;
}): ReactNode {
  const known = new Set(sources.map((s) => s.footnoteNo));
  const body = content;
  return (
    <>
      <p className="text-foreground text-base leading-7 whitespace-pre-line">
        {parseFootnotes(body).map((seg, i) => {
          if (seg.kind === 'text' || seg.footnoteNo === null || !known.has(seg.footnoteNo)) {
            return <span key={i}>{seg.value}</span>;
          }
          const no = seg.footnoteNo;
          return (
            <button
              key={i}
              type="button"
              title={`[${no}] 근거 보기`}
              className="text-primary hover:bg-accent focus-visible:bg-accent text-xs font-semibold tracking-wide mx-0.5 rounded-sm px-1 align-super font-mono transition-colors"
              onClick={() => onFootnoteClick?.(no)}
            >
              {no}
            </button>
          );
        })}
      </p>
      {infographic && <InfographicBlock infographic={infographic} />}
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
        연결된 도구·문서에서 수집한 값을 집계했습니다.
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
