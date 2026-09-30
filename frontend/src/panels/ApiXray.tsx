/**
 * "Show the API call" (spec §8.3): the route, status, duration and `X-Request-ID` of every request
 * behind a panel.
 */

import { Code } from 'lucide-react';

import type { ApiCall } from '@/api/client';
import { formatDuration } from '@/domain/dates';

export function ApiXray({ calls }: { calls: readonly ApiCall[] }) {
  return (
    <details className="group rounded-lg border bg-muted/40 text-sm">
      <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 font-medium">
        <Code aria-hidden="true" className="size-4" />
        Show the API call
        <span className="font-normal text-muted-foreground">
          ({calls.length} {calls.length === 1 ? 'request' : 'requests'})
        </span>
      </summary>
      <div className="overflow-x-auto px-3 pb-3">
        {calls.length === 0 ? (
          <p className="text-muted-foreground">No request has completed yet.</p>
        ) : (
          <table className="w-full text-left font-mono text-xs wrap-anywhere">
            <caption className="sr-only">Requests behind this panel</caption>
            <thead className="text-muted-foreground">
              <tr>
                <th scope="col" className="py-1 pr-3 font-normal">
                  Route
                </th>
                <th scope="col" className="py-1 pr-3 font-normal">
                  Status
                </th>
                <th scope="col" className="py-1 pr-3 font-normal">
                  Duration
                </th>
                <th scope="col" className="py-1 font-normal">
                  X-Request-ID
                </th>
              </tr>
            </thead>
            <tbody>
              {calls.map((call, index) => (
                <tr key={`${index}-${call.path}`} className="border-t align-top">
                  <td className="py-1 pr-3 break-all">
                    {call.method} {call.path}
                  </td>
                  <td className="py-1 pr-3">{call.status ?? 'no answer'}</td>
                  <td className="py-1 pr-3 whitespace-nowrap">{formatDuration(call.durationMs)}</td>
                  <td className="py-1 break-all" data-request-id="">
                    {call.requestId ?? 'none received'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </details>
  );
}
