/**
 * The four states every panel and Classic page has (spec §8.7): loading, empty, error, success.
 * The main surfaces' empty states, and the office while it loads, carry pixel art (F6).
 */

import type { UseQueryResult } from '@tanstack/react-query';
import { AlertTriangle, Inbox, RotateCw } from 'lucide-react';
import type { ReactNode } from 'react';

import { describeFailure } from '@/api/failures';
import { Button } from '@/ui/button';
import { Skeleton } from '@/ui/skeleton';

import { PixelArt, type ArtName } from './art';

export function LoadingState({ label, lines = 3 }: { label: string; lines?: number }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="space-y-2">
      <span className="sr-only">{`Loading ${label}…`}</span>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className="h-4 w-full last:w-2/3" />
      ))}
    </div>
  );
}

/**
 * The office's loading screen: an agent at work beside a desk while the 3D world downloads. The
 * status is the same as `LoadingState`'s for assistive technology.
 */
export function LoadingArt({ label, caption }: { label: string; caption: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="flex flex-col items-center gap-3 text-sm text-[#f3e6c9]"
    >
      <span className="sr-only">{`Loading ${label}…`}</span>
      <div className="flex items-end gap-3">
        <PixelArt name="agent" className="h-20 animate-bounce" />
        <PixelArt name="desk" className="h-20" />
      </div>
      <p aria-hidden="true" className="font-pixel text-xs tracking-wide uppercase">
        {caption}
      </p>
    </div>
  );
}

/** An empty state. On a main surface, `art` adds its picture above the words. */
export function EmptyState({ message, art }: { message: string; art?: ArtName }) {
  if (art !== undefined) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-6 text-center text-sm">
        <PixelArt name={art} className="h-14" />
        <p>{message}</p>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-3 rounded-lg border border-dashed p-4 text-sm">
      <Inbox aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
      <p>{message}</p>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const failure = describeFailure(error);
  return (
    <div role="alert" className="space-y-3 rounded-lg border border-bad/40 p-4 text-sm">
      <p className="flex items-center gap-2 font-medium text-bad">
        <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
        {failure.message}
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-xs">
        <dt className="text-muted-foreground">Code</dt>
        <dd>{failure.code}</dd>
        <dt className="text-muted-foreground">Request id</dt>
        <dd>{failure.requestId ?? 'none received'}</dd>
      </dl>
      {failure.issues.length > 0 && (
        <ul className="list-disc pl-5 font-mono text-xs">
          {failure.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCw aria-hidden="true" />
          Retry
        </Button>
      )}
    </div>
  );
}

interface QueryViewProps<T> {
  query: UseQueryResult<T>;
  /** What is loading, for screen readers. */
  label: string;
  /** Whether the data is empty; the empty copy is shown instead of `children`. */
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

/** Render a GET query in its current state. The error state offers Retry. */
export function QueryView<T>({ query, label, isEmpty, emptyMessage, children }: QueryViewProps<T>) {
  if (query.isPending) return <LoadingState label={label} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (isEmpty?.(query.data) && emptyMessage !== undefined) {
    return <EmptyState message={emptyMessage} />;
  }
  return <>{children(query.data)}</>;
}
