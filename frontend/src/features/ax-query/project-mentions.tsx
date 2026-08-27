import {
  useMemo,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { AtSign } from 'lucide-react';
import { api } from '@/lib/http';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import type { PageResponse, ProjectSummaryResponse } from '@/types/api';

/** 커서 바로 앞의 `@…` 토큰. 사업명에 띄어쓰기가 있어 20자까지는 공백을 허용한다. */
const TOKEN = /(?:^|\s)@([^@\n]{0,20})$/;
const MAX_MATCHES = 6;

export interface ProjectMentions {
  open: boolean;
  matches: ProjectSummaryResponse[];
  activeIndex: number;
  /** 본문에 아직 남아 있는 멘션의 프로젝트 id. */
  scope: string[];
  onChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  /** 멘션 목록이 먹은 키면 true — 부르는 쪽은 전송하지 않는다. */
  onKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => boolean;
  pick: (project: ProjectSummaryResponse) => void;
  clear: () => void;
}

/**
 * 사업 안에서는 멘션을 쓰지 않는다 — 질문 범위가 이미 그 사업으로 정해져 있어
 * 다른 사업을 끌어올 자리가 없다. 그럴 때는 `enabled` 를 false 로 두고 목록도 읽지 않는다.
 */
export function useProjectMentions(
  text: string,
  setText: (value: string) => void,
  inputRef: RefObject<HTMLTextAreaElement | null>,
  enabled = true,
): ProjectMentions {
  const [query, setQuery] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [picked, setPicked] = useState<ProjectSummaryResponse[]>([]);

  const projects = useAsync<PageResponse<ProjectSummaryResponse> | null>(
    () =>
      enabled
        ? api.get<PageResponse<ProjectSummaryResponse>>('/projects?size=100')
        : Promise.resolve(null),
    [enabled],
  );

  const matches = useMemo(() => {
    if (query === null) return [];
    const needle = query.trim();
    const all = projects.data?.content ?? [];
    return all
      .filter((p) => !needle || p.name.includes(needle) || p.clientOrgName.includes(needle))
      .slice(0, MAX_MATCHES);
  }, [query, projects.data]);

  const scope = useMemo(
    () => picked.filter((p) => text.includes(`@${p.name}`)).map((p) => p.id),
    [picked, text],
  );

  const close = () => {
    setQuery(null);
    setActiveIndex(0);
  };

  const onChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setText(value);
    if (!enabled) return;
    const found = TOKEN.exec(value.slice(0, e.target.selectionStart ?? value.length));
    setQuery(found ? found[1] : null);
    setActiveIndex(0);
  };

  const pick = (project: ProjectSummaryResponse) => {
    const input = inputRef.current;
    const caret = input?.selectionStart ?? text.length;
    const before = text.slice(0, caret);
    const at = before.lastIndexOf('@');
    if (at < 0) return;
    const inserted = `@${project.name} `;
    const next = before.slice(0, at) + inserted + text.slice(caret);
    setText(next);
    setPicked((current) =>
      current.some((p) => p.id === project.id) ? current : [...current, project],
    );
    close();
    requestAnimationFrame(() => {
      const caretAfter = at + inserted.length;
      input?.focus();
      input?.setSelectionRange(caretAfter, caretAfter);
    });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // 조합 중인 글자를 확정하는 Enter 다 — 목록이 가로채면 그 글자를 잃는다.
    if (e.nativeEvent.isComposing) return false;
    if (query === null || matches.length === 0) return false;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % matches.length);
      return true;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + matches.length) % matches.length);
      return true;
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      pick(matches[activeIndex]);
      return true;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return true;
    }
    return false;
  };

  return {
    open: query !== null && matches.length > 0,
    matches,
    activeIndex,
    scope,
    onChange,
    onKeyDown,
    pick,
    clear: close,
  };
}

/**
 * 컴포저 위에 뜨는 프로젝트 멘션 목록.
 * shadcn DropdownMenu 와 같은 표면을 쓰되, 입력줄에서 초점을 뺏으면 안 되어 목록만 직접 그린다.
 */
export function MentionMenu({ mentions }: { mentions: ProjectMentions }): ReactNode {
  if (!mentions.open) return null;
  return (
    <div
      role="listbox"
      aria-label="프로젝트 멘션"
      className="bg-popover text-popover-foreground ax-anim-pop absolute bottom-full left-0 z-50 mb-2 w-full max-w-md overflow-hidden rounded-md border p-1 shadow-md"
    >
      {mentions.matches.map((p, i) => (
        <button
          key={p.id}
          type="button"
          role="option"
          aria-selected={i === mentions.activeIndex}
          onMouseDown={(e) => {
            e.preventDefault();
            mentions.pick(p);
          }}
          className={cn(
            'relative flex w-full cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm transition-colors outline-none select-none',
            i === mentions.activeIndex && 'bg-accent text-accent-foreground',
          )}
        >
          <AtSign className="text-muted-foreground size-4 shrink-0" />
          <span className="min-w-0 flex-1 truncate text-left">{p.name}</span>
          <span className="text-muted-foreground text-xs font-semibold tracking-wide shrink-0">
            {p.clientOrgName}
          </span>
        </button>
      ))}
    </div>
  );
}
