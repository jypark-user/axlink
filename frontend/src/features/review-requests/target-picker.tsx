import { useMemo, useState, type ReactNode } from 'react';
import { Check } from 'lucide-react';
import { SearchInput } from '@/components/ui/search-input';
import { cn } from '@/lib/utils';
import type { ReviewTargetOption } from '@/types/api';

/** 띄어쓰기·대소문자를 무시하고 찾는다. 「1.2범위」로 쳐도 「1.2 범위·평가기준 합의」가 나온다 */
const norm = (s: string): string => s.toLowerCase().replace(/\s+/g, '');

/**
 * 확인 요청의 대상 고르기(11-18 사용자 지시). 항목이 수십 개면 펼침 목록에서 찾기 어려워, 찾기 칸과
 * 스크롤되는 목록을 창 안에 바로 둔다. 찾기어는 공백으로 나눠 모두 들어간 항목만 남긴다.
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
  const [text, setText] = useState('');
  const shown = useMemo(() => {
    const words = text.split(/\s+/).map(norm).filter(Boolean);
    if (words.length === 0) return targets;
    return targets.filter((t) => {
      const label = norm(t.label);
      return words.every((w) => label.includes(w));
    });
  }, [targets, text]);
  const selected = targets.find((t) => t.key === value);

  if (targets.length === 0) {
    return <p className="text-muted-foreground text-sm">고를 대상이 없습니다.</p>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      <SearchInput
        id={id}
        value={text}
        onValueChange={setText}
        placeholder="번호·이름으로 찾기"
        aria-label="대상 찾기"
        // 창 안의 폼이라 Enter 가 등록을 누르지 않게 막는다. 하나만 남았으면 그것을 고른다
        onKeyDown={(e) => {
          if (e.key !== 'Enter') return;
          e.preventDefault();
          if (shown.length === 1) onChange(shown[0].key);
        }}
      />
      <div
        role="listbox"
        aria-label="대상"
        className="max-h-56 overflow-y-auto rounded-md border"
        data-testid="review-target-list"
      >
        {shown.length === 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-sm">찾는 대상이 없습니다.</p>
        ) : (
          shown.map((t) => {
            const on = t.key === value;
            return (
              <button
                key={t.key}
                type="button"
                role="option"
                aria-selected={on}
                onClick={() => onChange(t.key)}
                className={cn(
                  'flex w-full items-start gap-2 px-3 py-1.5 text-left text-sm',
                  on ? 'bg-primary-muted text-primary' : 'hover:bg-accent',
                )}
              >
                <Check className={cn('mt-0.5 size-4 shrink-0', !on && 'invisible')} />
                <span className="break-keep">{t.label}</span>
              </button>
            );
          })
        )}
      </div>
      <p className="text-muted-foreground tnum text-xs">
        {text ? `${targets.length}건 중 ${shown.length}건` : `${targets.length}건`}
        {selected ? ` · 고른 대상: ${selected.label}` : ' · 아직 고르지 않았습니다'}
      </p>
    </div>
  );
}
