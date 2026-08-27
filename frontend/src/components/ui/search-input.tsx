import { type ComponentProps, type ReactNode } from 'react';
import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

/**
 * 검색 한 줄. 화면마다 다르게 생기지 않도록 이 하나만 쓴다 —
 * shadcn Input 에 앞쪽 돋보기와 지우기 단추를 얹은 것뿐이다.
 */
export function SearchInput({
  value,
  onValueChange,
  className,
  ...props
}: Omit<ComponentProps<typeof Input>, 'value' | 'onChange' | 'type'> & {
  value: string;
  onValueChange: (next: string) => void;
}): ReactNode {
  return (
    <div className={cn('relative', className)}>
      <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
      <Input
        type="search"
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        className="bg-card px-9 [&::-webkit-search-cancel-button]:hidden"
        {...props}
      />
      {value && (
        <button
          type="button"
          aria-label="검색어 지우기"
          onClick={() => onValueChange('')}
          className="text-muted-foreground hover:bg-accent hover:text-foreground absolute top-1/2 right-1.5 flex size-6 -translate-y-1/2 items-center justify-center rounded-full transition-colors"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}
