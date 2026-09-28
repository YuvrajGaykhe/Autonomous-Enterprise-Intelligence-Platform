import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge class names, letting later Tailwind utilities win (shadcn/ui's `cn`). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
