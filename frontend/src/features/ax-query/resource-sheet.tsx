import {
  useCallback,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { cn } from '@/lib/utils';

const WIDTH_KEY = 'ax-link.sheet-width';
const DEFAULT_WIDTH = 640;
const MIN_WIDTH = 360;
const MIN_CHAT_WIDTH = 420;
const KEY_STEP = 32;

function storedWidth() {
  if (typeof window === 'undefined') return DEFAULT_WIDTH;
  const raw = Number(window.localStorage.getItem(WIDTH_KEY));
  return Number.isFinite(raw) && raw >= MIN_WIDTH ? raw : DEFAULT_WIDTH;
}

/** 오른쪽 사이드바 영역의 자료 칸. ax-pms ResourceSheet 와 같다 — 경계를 끌어 폭을 바꾼다. */
export function ResourceSheet({
  label,
  resizable = true,
  fixedWidth = 320,
  children,
}: {
  label: string;
  /** 폭을 끌어 바꿀 수 있는지 — 자료 원문은 넓혀 보지만, 편집 자리는 고정이다. */
  resizable?: boolean;
  /** 고정일 때의 폭(px). */
  fixedWidth?: number;
  children: ReactNode;
}): ReactNode {
  const sheetRef = useRef<HTMLElement>(null);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const [width, setWidth] = useState(storedWidth);
  const [dragging, setDragging] = useState(false);

  const clamp = useCallback((value: number) => {
    let box = sheetRef.current?.parentElement ?? null;
    while (box && box.clientWidth === 0) box = box.parentElement;
    const available = box?.clientWidth || window.innerWidth;
    const max = Math.max(MIN_WIDTH, available - MIN_CHAT_WIDTH);
    return Math.round(Math.min(max, Math.max(MIN_WIDTH, value)));
  }, []);

  const commit = useCallback(
    (value: number) => {
      const next = clamp(value);
      setWidth(next);
      window.localStorage.setItem(WIDTH_KEY, String(next));
    },
    [clamp],
  );

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { startX: e.clientX, startWidth: width };
    setDragging(true);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    setWidth(clamp(drag.startWidth + (drag.startX - e.clientX)));
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.releasePointerCapture(e.pointerId);
    dragRef.current = null;
    setDragging(false);
    commit(width);
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft') commit(width + KEY_STEP);
    else if (e.key === 'ArrowRight') commit(width - KEY_STEP);
    else if (e.key === 'Home') commit(DEFAULT_WIDTH);
    else return;
    e.preventDefault();
  };

  return (
    <aside
      ref={sheetRef}
      aria-label={label}
      style={{ '--sheet-width': `${resizable ? width : fixedWidth}px` } as CSSProperties}
      className={cn(
        // 왼쪽 사이드바와 같은 결 — 화면 높이를 다 쓰고, 모서리도 바깥 여백도 두지 않는다.
        'bg-background border-border flex w-full max-w-full border-l',
        'absolute inset-y-0 right-0 z-30 shadow-float',
        'lg:relative lg:z-auto lg:w-[var(--sheet-width)] lg:shrink-0 lg:shadow-none',
        !dragging && '[animation:ax-panel-in_180ms_ease-out]',
      )}
    >
      {resizable && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={`${label} 폭 조절`}
          aria-valuenow={width}
          aria-valuemin={MIN_WIDTH}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onDoubleClick={() => commit(DEFAULT_WIDTH)}
          onKeyDown={onKeyDown}
          className="group absolute inset-y-0 -left-1 hidden w-2 cursor-col-resize touch-none lg:block"
        >
          <span
            aria-hidden
            className={cn(
              'absolute inset-y-6 left-1/2 w-px -translate-x-1/2 transition-colors',
              dragging ? 'bg-ring' : 'bg-transparent group-hover:bg-ring',
            )}
          />
        </div>
      )}

      <div className="min-w-0 flex-1 lg:overflow-hidden">{children}</div>
    </aside>
  );
}
