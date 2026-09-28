// Adapted from shadcn/ui's Card (new-york style).

import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

export function Card({ className, ...props }: ComponentProps<'section'>) {
  return (
    <section
      className={cn('rounded-xl border bg-card p-5 text-foreground shadow-xs', className)}
      {...props}
    />
  );
}

export function CardTitle({ className, children, ...props }: ComponentProps<'h2'>) {
  return (
    <h2 className={cn('text-base font-semibold', className)} {...props}>
      {children}
    </h2>
  );
}
