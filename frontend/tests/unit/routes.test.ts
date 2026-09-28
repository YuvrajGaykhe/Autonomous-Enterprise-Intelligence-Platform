import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ContractError, REQUEST_ID_HEADER, TIMEOUTS } from '@/api/client';
import { fetchEntities, fetchEntityTotal } from '@/api/entities';
import { describeFailure } from '@/api/failures';
import { fetchHealth } from '@/api/health';
import { fetchRun, fetchRunErrors, fetchRuns, startIngestion } from '@/api/ingestion';
import { fetchIngestionMetrics } from '@/api/metrics';
import { PAGE_SIZE, fetchAllPages } from '@/api/pagination';
import { healthQuery, queryKeys } from '@/api/queries';
import {
  fetchAssessment,
  fetchAssessments,
  fetchBrief,
  fetchDecisions,
  recordDecision,
  runAssessment,
} from '@/api/risk';
import { fetchSourceHealth, fetchSources } from '@/api/sources';
import { page } from '@/api/schemas/common';
import { z } from 'zod';

import {
  loadExchanges,
  recorded,
  recordedBriefs,
  recordedPrefix,
  type RecordedExchange,
} from '../support/fixtures';

interface Sent {
  method: string;
  path: string;
  body: unknown;
}

let sent: Sent[];

/** Answer every request with `answer(path)`, recording what was sent. */
function serve(answer: (path: string, method: string) => { status: number; body: unknown }) {
  sent = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: URL, init: RequestInit) => {
      const path = `${input.pathname}${input.search}`;
      const method = init.method ?? 'GET';
      sent.push({
        method,
        path,
        body: typeof init.body === 'string' ? (JSON.parse(init.body) as unknown) : null,
      });
      const { status, body } = answer(path, method);
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { [REQUEST_ID_HEADER]: 'rid-route' },
        }),
      );
    }),
  );
}

function serveExchange(exchange: RecordedExchange) {
  serve(() => ({ status: exchange.status, body: exchange.body }));
}

beforeEach(() => serve(() => ({ status: 500, body: {} })));
afterEach(() => vi.unstubAllGlobals());

describe('health and sources', () => {
  it('reads the recorded health', async () => {
    serveExchange(recorded('health.json', 'GET', '/api/v1/health'));

    const result = await fetchHealth();

    expect(sent).toEqual([{ method: 'GET', path: '/api/v1/health', body: null }]);
    expect(result.data.status).toBe('healthy');
  });

  it('reads a 503 health report as data, not as an error', async () => {
    const healthy = recorded('health.json', 'GET', '/api/v1/health').body as Record<
      string,
      unknown
    >;
    serve(() => ({
      status: 503,
      body: { ...healthy, status: 'unhealthy', checks: { database: 'unavailable' } },
    }));

    const result = await fetchHealth();

    expect(result.status).toBe(503);
    expect(result.data.checks.database).toBe('unavailable');
  });

  it('reads the recorded sources and one source health', async () => {
    serveExchange(recorded('sources.json', 'GET', '/api/v1/sources'));
    const sources = await fetchSources();
    expect(sources.data.sources.map((item) => item.source)).toContain('csv_demo');

    serveExchange(recorded('sources.json', 'GET', '/api/v1/sources/csv_demo/health'));
    const health = await fetchSourceHealth('csv_demo');
    expect(sent[0]?.path).toBe('/api/v1/sources/csv_demo/health');
    expect(health.data.status).toBe('healthy');
  });

  it('builds the health query on the health key', async () => {
    serveExchange(recorded('health.json', 'GET', '/api/v1/health'));
    const options = healthQuery();

    expect(options.queryKey).toEqual(queryKeys.health);
    const queryFn = options.queryFn as (context: { signal: AbortSignal }) => Promise<unknown>;
    await expect(queryFn({ signal: new AbortController().signal })).resolves.toMatchObject({
      status: 200,
    });
  });
});

describe('ingestion and metrics', () => {
  it('pages the recorded runs, then reads one run and its errors', async () => {
    const list = recordedPrefix('ingestion.json', '/api/v1/ingestion/runs?');
    serveExchange(list);
    const runs = await fetchRuns();
    expect(sent[0]?.path).toBe(`/api/v1/ingestion/runs?limit=${PAGE_SIZE}&offset=0`);
    const runId = runs.items[0]?.run_id ?? '';

    serveExchange(recorded('ingestion.json', 'GET', `/api/v1/ingestion/runs/${runId}`));
    expect((await fetchRun(runId)).data.status).toBe('SUCCESS');

    serveExchange(
      recorded(
        'ingestion.json',
        'GET',
        `/api/v1/ingestion/runs/${runId}/errors?limit=500&offset=0`,
      ),
    );
    const errors = await fetchRunErrors(runId);
    expect(errors.total).toBe(0);
    expect(sent[0]?.path).toBe(`/api/v1/ingestion/runs/${runId}/errors?limit=500&offset=0`);
  });

  it('starts an ingestion with the source only', async () => {
    const run = loadExchanges('ingestion.json')[1]?.body as Record<string, unknown>;
    serve(() => ({ status: 201, body: { ...run, batches_committed: 1, entities: [] } }));

    const result = await startIngestion('csv_demo');

    expect(sent).toEqual([
      { method: 'POST', path: '/api/v1/ingestion/runs', body: { source: 'csv_demo' } },
    ]);
    expect(result.status).toBe(201);
  });

  it('reads the recorded metrics', async () => {
    serveExchange(recorded('metrics.json', 'GET', '/api/v1/metrics/ingestion'));

    const result = await fetchIngestionMetrics();

    expect(result.data.totals.canonical_records.customers).toBe(50);
  });
});

describe('entities', () => {
  it('pages every record of a type', async () => {
    serveExchange(
      recorded('entities.json', 'GET', '/api/v1/entities/customers?limit=500&offset=0'),
    );

    const customers = await fetchEntities('customers');

    expect(customers.total).toBe(50);
    expect(customers.items).toHaveLength(50);
    expect(customers.calls).toHaveLength(1);
  });

  it('filters by source system when asked', async () => {
    serveExchange(
      recorded('entities.json', 'GET', '/api/v1/entities/documents?limit=500&offset=0'),
    );

    await fetchEntities('documents', { sourceSystem: 'csv_demo' });

    expect(sent[0]?.path).toBe(
      '/api/v1/entities/documents?limit=500&offset=0&source_system=csv_demo',
    );
  });

  it('reads a total with one single-record request', async () => {
    const full = recorded('entities.json', 'GET', '/api/v1/entities/deals?limit=500&offset=0')
      .body as { items: unknown[]; total: number };
    serve(() => ({ status: 200, body: { ...full, items: full.items.slice(0, 1), limit: 1 } }));

    const result = await fetchEntityTotal('deals');

    expect(sent[0]?.path).toBe('/api/v1/entities/deals?limit=1&offset=0');
    expect(result.total).toBe(44);
  });
});

describe('pagination', () => {
  const numbers = page(z.number().int());

  it('keeps requesting until offset plus items reaches the total', async () => {
    serve((path) => {
      const offset = Number(new URL(path, 'http://x').searchParams.get('offset'));
      return { status: 200, body: { items: [offset], total: 3, limit: 1, offset } };
    });

    const result = await fetchAllPages(
      (limit, offset) => `/n?limit=${limit}&offset=${offset}`,
      numbers,
    );

    expect(result.items).toEqual([0, 1, 2]);
    expect(sent.map((item) => item.path)).toEqual([
      '/n?limit=500&offset=0',
      '/n?limit=500&offset=1',
      '/n?limit=500&offset=2',
    ]);
    expect(result.calls).toHaveLength(3);
  });

  it('stops on an empty page rather than looping', async () => {
    serve(() => ({ status: 200, body: { items: [], total: 5, limit: 500, offset: 0 } }));

    const result = await fetchAllPages(
      (limit, offset) => `/n?limit=${limit}&offset=${offset}`,
      numbers,
    );

    expect(result).toMatchObject({ items: [], total: 5 });
    expect(sent).toHaveLength(1);
  });
});

describe('risk', () => {
  it('runs an assessment at a date, with the assessment timeout', async () => {
    const [first] = loadExchanges('assessment-runs.json');
    serveExchange(first as RecordedExchange);

    const result = await runAssessment('2026-09-18');

    expect(sent).toEqual([
      {
        method: 'POST',
        path: '/api/v1/risk/assessments',
        body: { as_of: '2026-09-18', source_system: 'csv_demo' },
      },
    ]);
    expect(result.status).toBe(201);
    expect(TIMEOUTS.assessment).toBe(60_000);
  });

  it('sends a null as_of for Auto', async () => {
    const [, repeat] = loadExchanges('assessment-runs.json');
    serveExchange(repeat as RecordedExchange);

    const result = await runAssessment(null);

    expect(sent[0]?.body).toEqual({ as_of: null, source_system: 'csv_demo' });
    expect(result.status).toBe(200);
  });

  it('pages the assessments at one as_of and reads one in detail', async () => {
    serveExchange(recordedPrefix('assessments.json', '/api/v1/risk/assessments?as_of=2026-09-18'));
    const list = await fetchAssessments('2026-09-18');
    expect(sent[0]?.path).toBe('/api/v1/risk/assessments?as_of=2026-09-18&limit=500&offset=0');
    expect(list.total).toBe(50);

    const detail = loadExchanges('assessment-details.json')[0] as RecordedExchange;
    serveExchange(detail);
    const result = await fetchAssessment(detail.path.split('/').pop() ?? '');
    expect(result.data.customer_source_id).toBe('CUST-007');
  });

  it('parses a version-1 brief', async () => {
    const exchange = recordedBriefs()[0] as RecordedExchange;
    serveExchange(exchange);

    const { brief } = await fetchBrief(exchange.path.split('/').pop() ?? '');

    expect(brief.supported).toBe(true);
    if (brief.supported) expect(brief.payload.band).toBe('CRITICAL');
  });

  it('refuses to render a payload version it does not support', async () => {
    const exchange = recordedBriefs()[0] as RecordedExchange;
    const body = exchange.body as { payload: Record<string, unknown> };
    serve(() => ({
      status: 200,
      body: { ...body, payload: { ...body.payload, payload_version: 2 } },
    }));

    const { brief } = await fetchBrief('b');

    expect(brief).toMatchObject({ supported: false, payloadVersion: 2 });
  });

  it('treats a version-1 payload that breaks its schema as a contract error', async () => {
    const exchange = recordedBriefs()[0] as RecordedExchange;
    const body = exchange.body as { payload: Record<string, unknown> };
    serve(() => ({ status: 200, body: { ...body, payload: { ...body.payload, band: 'SEVERE' } } }));

    const error = await fetchBrief('b').catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ContractError);
    expect(describeFailure(error).issues.some((issue) => issue.startsWith('band:'))).toBe(true);
  });

  it('records a decision and reads the chain', async () => {
    const decided = {
      id: '11111111-1111-4111-8111-111111111111',
      brief_id: '22222222-2222-4222-8222-222222222222',
      payload_hash: 'a'.repeat(64),
      actor: 'Owner',
      decision: 'APPROVED',
      note: null,
      decided_at: '2026-09-28T00:00:00Z',
      supersedes_id: null,
    };
    serve(() => ({ status: 201, body: decided }));
    const request = {
      actor: 'Owner',
      decision: 'APPROVED' as const,
      note: null,
      payload_hash: 'a'.repeat(64),
      supersedes_id: null,
    };

    const result = await recordDecision(decided.brief_id, request);

    expect(sent).toEqual([
      { method: 'POST', path: `/api/v1/risk/briefs/${decided.brief_id}/decision`, body: request },
    ]);
    expect(result.data.decision).toBe('APPROVED');

    const chain = loadExchanges('decisions.json')[0] as RecordedExchange;
    serveExchange(chain);
    const history = await fetchDecisions('b');
    expect(sent[0]?.path).toBe('/api/v1/risk/briefs/b/decisions');
    expect(history.data.items).toEqual([]);
  });
});
