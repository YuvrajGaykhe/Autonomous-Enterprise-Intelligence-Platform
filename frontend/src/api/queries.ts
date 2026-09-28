/**
 * TanStack Query keys and options (spec §6.7, PROPOSED).
 *
 * Retries are the client's (§6.2), so the query layer never retries on its own.
 */

import { queryOptions } from '@tanstack/react-query';

import { fetchHealth } from './health';

export const queryKeys = {
  health: ['health'] as const,
};

/** The HUD's health light refreshes every 30 s. */
export const HEALTH_REFRESH_MS = 30_000;

export function healthQuery() {
  return queryOptions({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => fetchHealth({ signal }),
    refetchInterval: HEALTH_REFRESH_MS,
  });
}
