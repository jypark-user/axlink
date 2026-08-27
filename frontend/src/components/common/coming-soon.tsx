import { type ReactNode } from 'react';
import { Construction } from 'lucide-react';

/** 메뉴만 먼저 열어 둔 화면. 구현되면 실제 페이지로 교체한다. */
export function ComingSoon({ title }: { title: string }): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
      <Construction className="text-muted-foreground size-10" />
      <h1 className="text-lg font-semibold">{title}</h1>
      <p className="text-muted-foreground text-sm">준비 중인 화면입니다.</p>
    </div>
  );
}
