import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Markdown } from '@/components/ui/markdown';
import { fetchBlob } from '@/lib/http';
import { cn } from '@/lib/utils';
import { assetPathOf, routeOf, splitAnchor } from '@/features/help/guide-links';

/**
 * 문서 안 화면 캡처. 그림 API 도 로그인이 필요해 img 에 주소를 바로 걸 수 없다. 토큰을 실어
 * 받아 잠시 쓰는 주소로 그린다. 대체 글은 그림 아래 설명으로도 보인다.
 * onSettled 는 그림을 다 받았거나 못 받았을 때 한 번 부른다(인쇄 화면이 기다린다).
 */
function GuideImage({
  src,
  alt,
  onSettled,
}: {
  src?: string;
  alt?: string;
  onSettled?: (path: string) => void;
}): ReactNode {
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
      .catch(() => {
        if (alive) {
          setFailed(true);
          onSettled?.(path);
        }
      });
    return () => {
      alive = false;
      if (href) URL.revokeObjectURL(href);
    };
  }, [path, onSettled]);
  const shown = path ? url : (src ?? null);
  return (
    <span className="my-2 block break-inside-avoid">
      {shown ? (
        <img
          src={shown}
          alt={alt ?? ''}
          onLoad={() => path && onSettled?.(path)}
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

const heading =
  (Tag: 'h2' | 'h3', className: string) =>
  ({ children }: { children?: ReactNode }) => {
    const { id, children: text } = splitAnchor(children);
    return (
      <Tag id={id} className={cn('scroll-mt-4 break-after-avoid', className)}>
        {text}
      </Tag>
    );
  };

const H2 = heading('h2', 'text-lg font-semibold tracking-tight mt-4 first:mt-0');
const H3 = heading('h3', 'text-sm font-semibold mt-2 first:mt-0');

/**
 * 설명서 본문. 설명서 화면과 인쇄 화면이 같이 쓴다. 제목 끝 `{#id}` 는 앵커로, 문서 안
 * `파일.md#절` 링크는 설명서 주소로, `images/…` 그림은 그림 API 로 바꿔 그린다.
 */
export function GuideMarkdown({
  markdown,
  files,
  onImageSettled,
}: {
  markdown: string;
  /** 설명서 파일 이름 → 주소 이름. GET /api/help 목차에서 만든다 */
  files: Map<string, string>;
  onImageSettled?: (path: string) => void;
}): ReactNode {
  return (
    <Markdown
      components={{
        h2: H2,
        h3: H3,
        img: ({ src, alt }) => (
          <GuideImage
            src={typeof src === 'string' ? src : undefined}
            alt={alt}
            onSettled={onImageSettled}
          />
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
      {markdown}
    </Markdown>
  );
}
