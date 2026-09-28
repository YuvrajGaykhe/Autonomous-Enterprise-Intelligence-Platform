/**
 * The query layer (spec §6.7): every query returns its data with the calls behind it, and the
 * writes invalidate exactly the keys §6.7 names. `countAssessments` reads a total in one request.
 */

import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { REQUEST_ID_HEADER } from '@/api/client';
import {
  assessmentQuery,
  assessmentsQuery,
  briefQuery,
  decisionsQuery,
  entitiesQuery,
  entityTotalQuery,
  invalidateAfterAssessment,
  invalidateAfterDecision,
  metricsQuery,
  queryKeys,
  runErrorsQuery,
  runsQuery,
  sourceHealthQuery,
  sourcesQuery,
} from '@/api/queries';
import { countAssessments } from '@/api/risk';

import { EXCHANGE_FILES, loadExchanges, type RecordedExchange } from '../support/fixtures';

const recordings = EXCHANGE_FILES.filter((file) => file !== 'decision-flow.json').flatMap((file) =>
  loadExchanges(file).filter((item) => item.method === 'GET'),
);
let paths: string[];

/** Answer each GET from the recording of its exact path, else of its pathname. */
beforeEach(() => {
  paths = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: URL) => {
      const path = `${input.pathname}${input.search}`;
      paths.push(path);
      const exact = recordings.find((item) => item.path === path);
      const byPathname = recordings.find((item) => item.path.split('?')[0] === input.pathname);
      const found = (exact ?? byPathname) as RecordedExchange;
      return Promise.resolve(
        new Response(JSON.stringify(found.body), {
          status: found.status,
          headers: { [REQUEST_ID_HEADER]: 'rid-query' },
        }),
      );
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const signal = new AbortController().signal;

async function run<T>(options: { queryFn?: unknown }): Promise<T> {
  const queryFn = options.queryFn as (context: { signal: AbortSignal }) => Promise<T>;
  return await queryFn({ signal });
}

type Result = { data: unknown; calls: { requestId: string | null }[] };

describe('every query carries its calls', () => {
  const briefId = (loadExchanges('briefs.json')[0]?.path ?? '').split('/').pop() ?? '';
  const assessmentId =
    (loadExchanges('assessment-details.json')[0]?.path ?? '').split('/').pop() ?? '';
  const runId = (loadExchanges('ingestion.json')[1]?.path ?? '').split('/').pop() ?? '';

  it.each([
    ['sources', sourcesQuery(), ['sources']],
    ['source health', sourceHealthQuery('csv_demo'), ['source-health', 'csv_demo']],
    ['runs', runsQuery(), ['runs']],
    ['run errors', runErrorsQuery(runId), ['run-errors', runId]],
    ['metrics', metricsQuery(), ['metrics']],
    ['entities', entitiesQuery('customers'), ['entities', 'customers']],
    ['entity total', entityTotalQuery('deals'), ['entity-total', 'deals']],
    ['assessments', assessmentsQuery('2026-09-18'), ['assessments', '2026-09-18']],
    ['assessment', assessmentQuery(assessmentId), ['assessment', assessmentId]],
    ['brief', briefQuery(briefId), ['brief', briefId]],
    ['decisions', decisionsQuery(briefId), ['decisions', briefId]],
  ] as const)('%s', async (_name, options, key) => {
    expect(options.queryKey).toEqual(key);
    const result = await run<Result>(options);
    expect(result.calls.length).toBeGreaterThan(0);
    expect(result.calls.every((call) => call.requestId === 'rid-query')).toBe(true);
    expect(result.data).toBeDefined();
  });

  it('reads the recorded values through the queries', async () => {
    expect((await run<{ data: unknown[] }>(sourcesQuery())).data).toHaveLength(3);
    expect((await run<{ data: number }>(entityTotalQuery('customers'))).data).toBe(50);
    expect((await run<{ data: unknown[] }>(assessmentsQuery('2026-09-18'))).data).toHaveLength(50);
    expect((await run<{ data: { supported: boolean } }>(briefQuery(briefId))).data.supported).toBe(
      true,
    );
    expect((await run<{ data: unknown[] }>(decisionsQuery(briefId))).data).toEqual([]);
  });
});

describe('countAssessments', () => {
  it('reads the total at one as_of with a single-row request', async () => {
    const result = await countAssessments('2026-09-18');
    expect(paths).toEqual(['/api/v1/risk/assessments?as_of=2026-09-18&limit=1&offset=0']);
    expect(result.total).toBe(50);
    expect(result.call.requestId).toBe('rid-query');
  });

  it('reads the total at every date for Auto', async () => {
    await countAssessments(null);
    expect(paths).toEqual(['/api/v1/risk/assessments?limit=1&offset=0']);
  });
});

describe('invalidation (§6.7)', () => {
  function seeded() {
    const client = new QueryClient();
    const keys = [
      queryKeys.brief('b1'),
      queryKeys.brief('b2'),
      queryKeys.decisions('b1'),
      queryKeys.decisions('b2'),
      queryKeys.assessments('2026-09-18'),
      queryKeys.assessments('2026-08-27'),
      queryKeys.assessment('a1'),
      queryKeys.sources,
    ];
    for (const key of keys) client.setQueryData(key, { data: null, calls: [] });
    return client;
  }

  function stale(client: QueryClient): string[] {
    return client
      .getQueryCache()
      .getAll()
      .filter((query) => query.state.isInvalidated)
      .map((query) => query.queryKey.join('/'))
      .sort();
  }

  it('after a decision: that brief, its decisions and every assessment list', async () => {
    const client = seeded();
    await invalidateAfterDecision(client, 'b1');
    expect(stale(client)).toEqual([
      'assessments/2026-08-27',
      'assessments/2026-09-18',
      'brief/b1',
      'decisions/b1',
    ]);
  });

  it('after an assessment run: every assessment list', async () => {
    const client = seeded();
    await invalidateAfterAssessment(client);
    expect(stale(client)).toEqual(['assessments/2026-08-27', 'assessments/2026-09-18']);
  });
});
