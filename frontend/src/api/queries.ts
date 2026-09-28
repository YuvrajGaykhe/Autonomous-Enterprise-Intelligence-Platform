/**
 * TanStack Query keys, options and invalidation (spec §6.7, PROPOSED).
 *
 * Every query result carries the calls behind it, for "Show the API call" (§8.3). Retries are the
 * client's (§6.2), so the query layer never retries on its own.
 */

import { queryOptions, type QueryClient } from '@tanstack/react-query';

import type { ApiCall } from './client';
import { fetchEntities, fetchEntityTotal } from './entities';
import { fetchHealth } from './health';
import { fetchRunErrors, fetchRuns } from './ingestion';
import { fetchIngestionMetrics } from './metrics';
import { fetchAssessment, fetchAssessments, fetchBrief, fetchDecisions } from './risk';
import type { EntityType } from './schemas/entities';
import { fetchSourceHealth, fetchSources } from './sources';

/** A query's data and every request that produced it. */
export interface Fetched<T> {
  data: T;
  calls: ApiCall[];
}

export const queryKeys = {
  health: ['health'] as const,
  sources: ['sources'] as const,
  sourceHealth: (source: string) => ['source-health', source] as const,
  runs: ['runs'] as const,
  runErrors: (runId: string) => ['run-errors', runId] as const,
  metrics: ['metrics'] as const,
  entities: (type: EntityType) => ['entities', type] as const,
  entityTotal: (type: EntityType) => ['entity-total', type] as const,
  /** The prefix of every assessment list, at every `as_of`. */
  assessmentLists: ['assessments'] as const,
  assessments: (asOf: string) => ['assessments', asOf] as const,
  assessment: (id: string) => ['assessment', id] as const,
  brief: (id: string) => ['brief', id] as const,
  decisions: (briefId: string) => ['decisions', briefId] as const,
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

export function sourcesQuery() {
  return queryOptions({
    queryKey: queryKeys.sources,
    queryFn: async ({ signal }) => {
      const result = await fetchSources({ signal });
      return { data: result.data.sources, calls: [result.call] };
    },
  });
}

export function sourceHealthQuery(source: string) {
  return queryOptions({
    queryKey: queryKeys.sourceHealth(source),
    queryFn: async ({ signal }) => {
      const result = await fetchSourceHealth(source, { signal });
      return { data: result.data, calls: [result.call] };
    },
  });
}

export function runsQuery() {
  return queryOptions({
    queryKey: queryKeys.runs,
    queryFn: async ({ signal }) => {
      const pages = await fetchRuns({ signal });
      return { data: pages.items, calls: pages.calls };
    },
  });
}

export function runErrorsQuery(runId: string) {
  return queryOptions({
    queryKey: queryKeys.runErrors(runId),
    queryFn: async ({ signal }) => {
      const pages = await fetchRunErrors(runId, { signal });
      return { data: pages.items, calls: pages.calls };
    },
  });
}

export function metricsQuery() {
  return queryOptions({
    queryKey: queryKeys.metrics,
    queryFn: async ({ signal }) => {
      const result = await fetchIngestionMetrics({ signal });
      return { data: result.data, calls: [result.call] };
    },
  });
}

export function entitiesQuery<T extends EntityType>(type: T) {
  return queryOptions({
    queryKey: queryKeys.entities(type),
    queryFn: async ({ signal }) => {
      const pages = await fetchEntities(type, { signal });
      return { data: pages.items, calls: pages.calls };
    },
  });
}

export function entityTotalQuery(type: EntityType) {
  return queryOptions({
    queryKey: queryKeys.entityTotal(type),
    queryFn: async ({ signal }) => {
      const result = await fetchEntityTotal(type, { signal });
      return { data: result.total, calls: [result.call] };
    },
  });
}

export function assessmentsQuery(asOf: string) {
  return queryOptions({
    queryKey: queryKeys.assessments(asOf),
    queryFn: async ({ signal }) => {
      const pages = await fetchAssessments(asOf, { signal });
      return { data: pages.items, calls: pages.calls };
    },
  });
}

export function assessmentQuery(id: string) {
  return queryOptions({
    queryKey: queryKeys.assessment(id),
    queryFn: async ({ signal }) => {
      const result = await fetchAssessment(id, { signal });
      return { data: result.data, calls: [result.call] };
    },
  });
}

export function briefQuery(id: string) {
  return queryOptions({
    queryKey: queryKeys.brief(id),
    queryFn: async ({ signal }) => {
      const result = await fetchBrief(id, { signal });
      return { data: result.brief, calls: [result.call] };
    },
  });
}

export function decisionsQuery(briefId: string) {
  return queryOptions({
    queryKey: queryKeys.decisions(briefId),
    queryFn: async ({ signal }) => {
      const result = await fetchDecisions(briefId, { signal });
      return { data: result.data.items, calls: [result.call] };
    },
  });
}

/** After a decision succeeds or conflicts: that brief, its decisions and the inbox (§6.7). */
export async function invalidateAfterDecision(client: QueryClient, briefId: string): Promise<void> {
  await Promise.all([
    client.invalidateQueries({ queryKey: queryKeys.brief(briefId) }),
    client.invalidateQueries({ queryKey: queryKeys.decisions(briefId) }),
    client.invalidateQueries({ queryKey: queryKeys.assessmentLists }),
  ]);
}

/** After an assessment run returns: every assessment list, which the inbox is built on (§6.7). */
export async function invalidateAfterAssessment(client: QueryClient): Promise<void> {
  await client.invalidateQueries({ queryKey: queryKeys.assessmentLists });
}
