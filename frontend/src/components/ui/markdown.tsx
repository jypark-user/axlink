import { type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

/**
 * 마크다운 본문. 문서에서 뽑은 글은 제목·목록·표가 섞여 있어 그대로 두면 한 덩어리로 보인다.
 * 앱 타이포에 맞춰 최소한만 입힌다 — 색이나 장식은 넣지 않는다.
 */
export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}): ReactNode {
  return (
    <div className={cn('text-foreground text-base leading-7 flex flex-col gap-3', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children: c }) => (
            <h3 className="text-lg font-semibold tracking-tight mt-2 first:mt-0">{c}</h3>
          ),
          h2: ({ children: c }) => (
            <h4 className="text-lg font-semibold tracking-tight mt-2 first:mt-0">{c}</h4>
          ),
          h3: ({ children: c }) => <h5 className="text-sm mt-2 font-semibold first:mt-0">{c}</h5>,
          p: ({ children: c }) => <p className="whitespace-pre-line">{c}</p>,
          ul: ({ children: c }) => <ul className="ml-5 list-disc space-y-1">{c}</ul>,
          ol: ({ children: c }) => <ol className="ml-5 list-decimal space-y-1">{c}</ol>,
          li: ({ children: c }) => <li className="text-sm">{c}</li>,
          a: ({ href, children: c }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              {c}
            </a>
          ),
          blockquote: ({ children: c }) => (
            <blockquote className="border-border text-muted-foreground border-l-2 pl-3">
              {c}
            </blockquote>
          ),
          code: ({ children: c }) => (
            <code className="bg-muted rounded-sm px-1 py-0.5 font-mono text-sm">{c}</code>
          ),
          pre: ({ children: c }) => (
            <pre className="bg-muted overflow-x-auto rounded-md p-3 font-mono text-sm">{c}</pre>
          ),
          table: ({ children: c }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">{c}</table>
            </div>
          ),
          th: ({ children: c }) => (
            <th className="border-border border-b px-2 py-1.5 text-left font-medium">{c}</th>
          ),
          td: ({ children: c }) => <td className="border-border/60 border-b px-2 py-1.5">{c}</td>,
          hr: () => <hr className="border-border" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
