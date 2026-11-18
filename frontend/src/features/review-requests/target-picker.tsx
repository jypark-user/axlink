import { useMemo, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Popover as PopoverPrimitive } from 'radix-ui';
import { Check, ChevronDown, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ReviewTargetOption } from '@/types/api';

/** 띄어쓰기·대소문자를 무시하고 찾는다. 「1.2범위」로 쳐도 「1.2 범위·평가기준 합의」가 나온다 */
const norm = (s: string): string => s.toLowerCase().replace(/\s+/g, '');

/**
 * 확인 요청의 대상 고르기(11-18 사용자 지시). 누르면 펼쳐지고 맨 위 검색 칸으로 거르는 고르기다.
 * 찾기어는 공백으로 나눠 모두 들어간 항목만 남긴다. 위·아래 화살표로 옮기고 Enter 로 고른다.
 */
export function TargetPicker({
  id,
  targets,
  value,
  onChange,
}: {
  id?: string;
  targets: ReviewTargetOption[];
  value: string;
  onChange: (key: string) => void;
}): ReactNode {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [active, setActive] = useState(0);
  const shown = useMemo(() => {
    const words = text.split(/\s+/).map(norm).filter(Boolean);
    if (words.length === 0) return targets;
    return targets.filter((t) => {
      const label = norm(t.label);
      return words.every((w) => label.includes(w));
    });
  }, [targets, text]);
  const selected = targets.find((t) => t.key === value);

  const toggle = (next: boolean) => {
    setOpen(next);
    if (next) {
      setText('');
      setActive(
        Math.max(
          0,
          targets.findIndex((t) => t.key === value),
        ),
      );
    }
  };
  const pick = (key: string) => {
    onChange(key);
    setOpen(false);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, shown.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      // 창 안의 폼이라 Enter 가 등록을 누르지 않게 막는다
      e.preventDefault();
      const hit = shown[active];
      if (hit) pick(hit.key);
    }
  };

  return (
    // modal: 확인 요청 창(Dialog) 안에서 열리므로, 자기 스크롤 잠금을 가져야 목록 휠 스크롤이 된다
    <PopoverPrimitive.Root open={open} onOpenChange={toggle} modal>
      <PopoverPrimitive.Trigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          disabled={targets.length === 0}
          className={cn(
            'border-input flex h-9 w-full min-w-0 items-center justify-between gap-2 rounded-md border bg-transparent px-3 text-left text-sm shadow-xs outline-none',
            'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50',
            !selected && 'text-muted-foreground',
          )}
        >
          {/* 이름이 길면 말줄임하고, 마우스를 올리면 전체가 보인다 */}
          <span className="min-w-0 truncate" title={selected?.label}>
            {selected?.label ?? (targets.length ? '대상을 고르세요' : '대상이 없습니다')}
          </span>
          <ChevronDown className="size-4 shrink-0 opacity-50" />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          align="start"
          sideOffset={4}
          className="bg-popover text-popover-foreground z-50 w-(--radix-popover-trigger-width) rounded-md border shadow-md"
          // 펼치면 검색 칸에 바로 친다
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            (e.currentTarget as HTMLElement).querySelector('input')?.focus();
          }}
        >
          <div className="flex items-center gap-2 border-b px-3">
            <Search className="text-muted-foreground size-4 shrink-0" />
            <input
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setActive(0);
              }}
              onKeyDown={onKey}
              placeholder="검색"
              aria-label="대상 찾기"
              className="placeholder:text-muted-foreground h-9 w-full bg-transparent text-sm outline-none"
            />
          </div>
          <div role="listbox" aria-label="대상" className="max-h-64 overflow-y-auto p-1">
            {shown.length === 0 ? (
              <p className="text-muted-foreground px-2 py-1.5 text-sm">찾는 대상이 없습니다.</p>
            ) : (
              shown.map((t, i) => {
                const on = t.key === value;
                return (
                  <button
                    key={t.key}
                    type="button"
                    role="option"
                    aria-selected={on}
                    onClick={() => pick(t.key)}
                    onMouseEnter={() => setActive(i)}
                    ref={(el) => {
                      if (i === active && el) el.scrollIntoView?.({ block: 'nearest' });
                    }}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-left text-sm',
                      i === active && 'bg-accent',
                      on && 'text-primary',
                    )}
                  >
                    <Check className={cn('mt-0.5 size-4 shrink-0', !on && 'invisible')} />
                    <span className="break-keep">{t.label}</span>
                  </button>
                );
              })
            )}
          </div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
