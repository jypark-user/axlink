import * as React from 'react';
import { Dialog as DialogPrimitive } from 'radix-ui';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

const OVERLAY_BASE = 'fixed inset-0 z-50 bg-black/50 ax-anim-fade';
const CONTENT_BASE =
  'fixed left-1/2 top-1/2 z-50 grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-lg border bg-background p-6 shadow-lg ax-anim-pop';
const CLOSE_BASE =
  'absolute right-4 top-4 rounded-sm opacity-70 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none [&_svg]:size-4';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogPortal = DialogPrimitive.Portal;
export const DialogClose = DialogPrimitive.Close;

export function DialogOverlay({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(OVERLAY_BASE, className)}
      {...props}
    />
  );
}

/** 머리(제목 줄)를 잡아 끌 때 무시할 것. 머리 안의 단추·입력은 끌기가 아니라 그대로 누른다 */
const NO_DRAG = 'button, a, input, textarea, select, [role="button"], [contenteditable="true"]';

/**
 * 가운데 뜨는 창. 머리(DialogHeader)를 잡고 끌어 옮길 수 있다(11-19 사용자 지시). 옆에 붙는
 * 창(Sheet)은 해당 없다. 닫으면 다음에 열 때 다시 가운데다.
 */
export function DialogContent({
  className,
  children,
  showCloseButton = true,
  style,
  onPointerDown,
  onCloseAutoFocus,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { showCloseButton?: boolean }) {
  const [offset, setOffset] = React.useState({ x: 0, y: 0 });

  const startDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    onPointerDown?.(e);
    const target = e.target as HTMLElement;
    if (e.button !== 0 || !target.closest('[data-slot="dialog-header"]')) return;
    if (target.closest(NO_DRAG)) return;
    e.preventDefault();
    const from = { x: e.clientX - offset.x, y: e.clientY - offset.y };
    // 창이 화면 밖으로 다 나가지 않게 가운데에서 화면 반 너비·높이까지만 옮긴다
    const limit = { x: window.innerWidth / 2, y: window.innerHeight / 2 - 24 };
    const move = (ev: PointerEvent) => {
      setOffset({
        x: Math.max(-limit.x, Math.min(limit.x, ev.clientX - from.x)),
        y: Math.max(-limit.y, Math.min(limit.y, ev.clientY - from.y)),
      });
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
  };

  const moved = offset.x !== 0 || offset.y !== 0;
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        className={cn(CONTENT_BASE, className)}
        style={
          moved
            ? { ...style, translate: `calc(-50% + ${offset.x}px) calc(-50% + ${offset.y}px)` }
            : style
        }
        onPointerDown={startDrag}
        onCloseAutoFocus={(e) => {
          setOffset({ x: 0, y: 0 });
          onCloseAutoFocus?.(e);
        }}
        {...props}
      >
        {children}
        {showCloseButton ? (
          <DialogPrimitive.Close data-slot="dialog-close" className={CLOSE_BASE}>
            <X />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        ) : null}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
}

export function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="dialog-header"
      className={cn('flex cursor-move flex-col gap-2 text-left select-none', className)}
      {...props}
    />
  );
}

export function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)}
      {...props}
    />
  );
}

export function DialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn('text-lg font-semibold leading-none', className)}
      {...props}
    />
  );
}

export function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  );
}
