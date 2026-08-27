import * as React from 'react';
import { Dialog as SheetPrimitive } from 'radix-ui';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

const OVERLAY_BASE = 'fixed inset-0 z-50 bg-black/50 ax-anim-fade';
const CONTENT_BASE = 'fixed z-50 flex flex-col gap-4 bg-background shadow-lg ax-anim-sheet';
const CLOSE_BASE =
  'absolute right-4 top-4 rounded-sm opacity-70 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 [&_svg]:size-4';

const SIDE_CLASS: Record<'top' | 'bottom' | 'left' | 'right', string> = {
  right: 'inset-y-0 right-0 h-full w-3/4 border-l sm:max-w-md',
  left: 'inset-y-0 left-0 h-full w-3/4 border-r sm:max-w-md',
  top: 'inset-x-0 top-0 h-auto border-b',
  bottom: 'inset-x-0 bottom-0 h-auto border-t',
};

export const Sheet = SheetPrimitive.Root;
export const SheetTrigger = SheetPrimitive.Trigger;
export const SheetPortal = SheetPrimitive.Portal;
export const SheetClose = SheetPrimitive.Close;

export function SheetOverlay({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      data-slot="sheet-overlay"
      className={cn(OVERLAY_BASE, className)}
      {...props}
    />
  );
}

export function SheetContent({
  className,
  children,
  side = 'right',
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & {
  side?: 'top' | 'bottom' | 'left' | 'right';
}) {
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        data-side={side}
        className={cn(CONTENT_BASE, SIDE_CLASS[side], className)}
        {...props}
      >
        {children}
        <SheetPrimitive.Close data-slot="sheet-close" className={CLOSE_BASE}>
          <X />
          <span className="sr-only">Close</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPortal>
  );
}

export function SheetHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="sheet-header"
      className={cn('flex flex-col gap-1.5 border-b p-4', className)}
      {...props}
    />
  );
}

export function SheetFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn('mt-auto flex flex-col gap-2 border-t p-4', className)}
      {...props}
    />
  );
}

export function SheetTitle({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn('text-base font-semibold', className)}
      {...props}
    />
  );
}

export function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  );
}
