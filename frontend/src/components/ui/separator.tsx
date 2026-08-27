import * as React from 'react';
import { Separator as SeparatorPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';

const SEPARATOR_BASE =
  'shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px';

export function Separator({
  className,
  orientation = 'horizontal',
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(SEPARATOR_BASE, className)}
      {...props}
    />
  );
}
