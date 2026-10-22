import { Children, type ReactNode } from 'react';

const ANCHOR = /\s*\{#([\w-]+)\}\s*$/;

/** 제목 끝의 `{#id}` 를 떼어 앵커로 쓴다. 화면에서 특정 절로 바로 오려고 둔다(pandoc 과 같은 표기). */
export function splitAnchor(children: ReactNode): { id?: string; children: ReactNode } {
  const list = Children.toArray(children);
  const last = list[list.length - 1];
  if (typeof last !== 'string') return { children };
  const m = last.match(ANCHOR);
  if (!m) return { children };
  return { id: m[1], children: [...list.slice(0, -1), last.slice(0, m.index)] };
}

/** 문서의 절 목록(## 제목 중 앵커가 있는 것). 왼쪽 목차가 쓴다. */
export function sectionsOf(markdown: string): { id: string; title: string }[] {
  const out: { id: string; title: string }[] = [];
  for (const line of markdown.split('\n')) {
    const m = line.match(/^## (.+?)\s*\{#([\w-]+)\}\s*$/);
    if (m) out.push({ id: m[2], title: m[1].replace(/\*\*/g, '') });
  }
  return out;
}

/**
 * 문서 안 링크를 화면 주소로 바꾼다. 문서끼리는 파일 이름으로 링크한다(저장소에서도 열리게).
 * `요구사항-등록.md#spec-format` → `/guide/requirement-baseline#spec-format`, `#x` 는 그 문서 안.
 * 설명서 문서가 아니면 null 이다(바깥 링크로 연다).
 */
export function routeOf(href: string, files: Map<string, string>): string | null {
  if (href.startsWith('#')) return href;
  if (/^[a-z]+:/i.test(href)) return null;
  const [path, hash] = decodeURIComponent(href).split('#');
  const slug = files.get(path.split('/').pop() ?? '');
  if (!slug) return null;
  return `/guide/${slug}${hash ? `#${hash}` : ''}`;
}
