import type { ReactNode } from 'react';
import { TriangleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';

const GAP_PREFIX = '격차 경고: ';

/**
 * 일정 경고 모음. 작업 일정 위에 줄줄이 두던 경고를 버튼 하나로 접고 누르면 연다(11-18 사용자
 * 지시). 작업 단위 격차 경고(DEC-20)는 각 작업 줄의 배지로도 남는다(AC-041-4).
 */
export function ScheduleWarnings({ warnings }: { warnings: string[] }): ReactNode {
  if (warnings.length === 0) return null;
  const gaps = warnings
    .filter((w) => w.startsWith(GAP_PREFIX))
    .map((w) => w.slice(GAP_PREFIX.length));
  const others = warnings.filter((w) => !w.startsWith(GAP_PREFIX));
  const label = gaps.length > 0 ? `격차 경고 ${gaps.length}건` : `확인할 점 ${others.length}건`;

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="text-amber-700 dark:text-amber-300"
          data-testid="schedule-warnings"
        >
          <TriangleAlert />
          {label}
          {gaps.length > 0 && others.length > 0 && (
            <span className="text-muted-foreground"> · 그 밖 {others.length}</span>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{gaps.length > 0 ? '격차 경고' : '확인할 점'}</DialogTitle>
          <DialogDescription>
            격차 경고는 WBS 파일에 실적 80% 이상으로 적었는데 산출물이 아직 없거나 연결 이슈가 열려
            있는 작업입니다. 신고한 실적과 증거가 맞지 않는 곳입니다.
          </DialogDescription>
        </DialogHeader>
        {gaps.length > 0 && (
          <section>
            <h3 className="mb-1 text-sm font-medium">총 {gaps.length}건</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {gaps.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </section>
        )}
        {others.length > 0 && (
          <section>
            <h3 className="mb-1 text-sm font-medium">그 밖에 확인할 점</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {others.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}
