import * as React from 'react';
import { Slot } from 'radix-ui';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

// ax-pms 배지 — 알약 모양에 옅은 바탕, 글자만 상태색.
const badgeVariants = cva(
  'inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden whitespace-nowrap rounded-full border border-transparent px-2 py-0.5 text-xs font-medium transition-[color,box-shadow] [&>svg]:pointer-events-none [&>svg]:size-3',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground [a&]:hover:bg-primary/90',
        secondary: 'bg-secondary text-secondary-foreground [a&]:hover:bg-secondary/90',
        destructive: 'bg-destructive-muted text-destructive',
        outline: 'border-border text-foreground [a&]:hover:bg-accent',
        ghost: '[a&]:hover:bg-accent [a&]:hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 [a&]:hover:underline',
        muted: 'bg-muted text-muted-foreground',
        primary: 'bg-primary-muted text-primary',
        success: 'bg-success-muted text-success',
        warning: 'bg-warning-muted text-warning',
        info: 'bg-info-muted text-info',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export type BadgeProps = React.ComponentProps<'span'> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean };

export function Badge({ className, variant = 'default', asChild = false, ...props }: BadgeProps) {
  const Comp = asChild ? Slot.Root : 'span';
  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

export { badgeVariants };
