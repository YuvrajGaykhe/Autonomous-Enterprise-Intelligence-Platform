/**
 * `npm run record-fixtures`: record the frontend's test fixtures from the real API (spec §12.2).
 *
 * The API is the working tree's, served over `<database>_frontend_e2e`, which is recreated from
 * clean and assessed at 2026-09-18 first (§12.3). Every exchange is written exactly as parsed
 * from the wire, and `PROVENANCE.json` states where the recording came from. Nothing here
 * edits a recorded body. Never run it while the end-to-end tests run: both use the same
 * isolated database.
 *
 * Every recorded brief body goes into `briefs.json` and nowhere else (owner ruling 3 of F1): the
 * three at 2026-09-18 first, then the Auto run's. That file is the only one the secret scanner's
 * allow-list names for a brief's `matched_token`.
 *
 * Exit status 2 means the isolated environment could not be used or started.
 */

import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  ACCEPTANCE_AS_OF,
  E2E_SUFFIX,
  EnvironmentRefused,
  SOURCE_SYSTEM,
  databaseOf,
  databaseRevision,
  isolatedUrl,
  startIsolatedBackend,
} from './lib/isolated.ts';
import { REPO_ROOT, configuredDatabaseUrl } from './lib/settings.ts';

const FIXTURES = fileURLToPath(new URL('../tests/fixtures/', import.meta.url));
const PAGE = 'limit=500&offset=0';
const ENTITY_TYPES = [
  'organizations',
  'employees',
  'customers',
  'deals',
  'projects',
  'support_tickets',
  'documents',
] as const;
/** Paths whose content decides what the API answers. */
const BACKEND_PATHS = ['app', 'config', 'migrations', 'alembic.ini', 'data'];

interface Exchange {
  method: 'GET' | 'POST';
  path: string;
  request_body?: unknown;
  status: number;
  body: unknown;
}

async function exchange(
  baseUrl: string,
  method: Exchange['method'],
  path: string,
  requestBody?: unknown,
): Promise<Exchange> {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers:
      requestBody === undefined
        ? { Accept: 'application/json' }
        : { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: requestBody === undefined ? null : JSON.stringify(requestBody),
  });
  const body: unknown = await response.json();
  return requestBody === undefined
    ? { method, path, status: response.status, body }
    : { method, path, request_body: requestBody, status: response.status, body };
}

const get = (baseUrl: string, path: string) => exchange(baseUrl, 'GET', path);

function write(name: string, exchanges: readonly Exchange[]): string[] {
  writeFileSync(`${FIXTURES}${name}`, `${JSON.stringify(exchanges, null, 2)}\n`);
  return exchanges.map((item) => `${item.method} ${item.path} ${item.status}`);
}

function git(...args: string[]): string {
  return execFileSync('git', args, { cwd: REPO_ROOT, encoding: 'utf8' }).trim();
}

function expectStatus(item: Exchange, status: number): Exchange {
  if (item.status !== status) {
    throw new Error(`${item.method} ${item.path} answered ${item.status}, expected ${status}`);
  }
  return item;
}

interface ListItem {
  id: string;
  customer_source_id: string | null;
  brief_ids: string[];
}

/** An id no row carries, for the not-found and foreign-predecessor answers. */
const UNKNOWN_ID = '00000000-0000-4000-8000-000000000000';
/** A well-formed payload hash that is no brief's. */
const STALE_HASH = '0'.repeat(64);
const RECORDER_ACTOR = 'Fixture Recorder';

/**
 * The decision writes and refusals the pages render (spec §7.5, §7.6), on the first brief. It runs
 * after every other recording, because it writes: the brief and chain files above stay PENDING.
 */
async function recordDecisionFlow(
  base: string,
  briefId: string | undefined,
  brief: Exchange | undefined,
): Promise<Exchange[]> {
  if (briefId === undefined || brief === undefined) throw new Error('no brief to decide on');
  const path = `/api/v1/risk/briefs/${briefId}/decision`;
  const decide = async (body: Record<string, unknown>, status: number) =>
    expectStatus(await exchange(base, 'POST', path, body), status);
  const approval = {
    actor: RECORDER_ACTOR,
    decision: 'APPROVED',
    note: 'Recorded by the fixture tool.',
    payload_hash: (brief.body as { payload_hash: string }).payload_hash,
    supersedes_id: null,
  };
  const approve = await decide(approval, 201);
  const firstId = (approve.body as { id: string }).id;
  const flow = [
    approve,
    // SUPERSEDES_REQUIRED, REQUEST_HASH_MISMATCH, PREDECESSOR_NOT_ON_BRIEF, INVALID_REQUEST.
    await decide({ ...approval, decision: 'REJECTED', note: null }, 409),
    await decide({ ...approval, payload_hash: STALE_HASH, supersedes_id: firstId }, 409),
    await decide({ ...approval, supersedes_id: UNKNOWN_ID }, 409),
    await decide({ ...approval, actor: '', supersedes_id: firstId }, 422),
  ];
  const rejection = {
    ...approval,
    decision: 'REJECTED',
    note: 'Superseded by the fixture tool.',
    supersedes_id: firstId,
  };
  flow.push(await decide(rejection, 201));
  // PREDECESSOR_NOT_HEAD: the first decision is no longer the head.
  flow.push(await decide(rejection, 409));
  flow.push(
    expectStatus(await get(base, `/api/v1/risk/briefs/${briefId}/decisions`), 200),
    expectStatus(await get(base, `/api/v1/risk/briefs/${UNKNOWN_ID}`), 404),
    expectStatus(await get(base, `/api/v1/risk/briefs/${UNKNOWN_ID}/decisions`), 404),
    expectStatus(await get(base, `/api/v1/risk/assessments/${UNKNOWN_ID}`), 404),
  );
  return flow;
}

/**
 * Auto (`as_of: null`, D-F-14): the run, the date it resolved to and that date's snapshot, then
 * the refusal of a scope with no ticket to resolve a date from (SCOPE_UNRESOLVED). The snapshot's
 * briefs are returned apart, for `briefs.json`.
 */
async function recordAutoRun(base: string): Promise<{ exchanges: Exchange[]; briefs: Exchange[] }> {
  const run = expectStatus(
    await exchange(base, 'POST', '/api/v1/risk/assessments', {
      as_of: null,
      source_system: SOURCE_SYSTEM,
    }),
    201,
  );
  const [first] = (run.body as { items: { assessment_id: string }[] }).items;
  if (first === undefined) throw new Error('the Auto run assessed no customer');
  const detail = expectStatus(
    await get(base, `/api/v1/risk/assessments/${first.assessment_id}`),
    200,
  );
  const asOf = (detail.body as { as_of: string }).as_of;
  const list = expectStatus(await get(base, `/api/v1/risk/assessments?as_of=${asOf}&${PAGE}`), 200);
  const briefIds = (list.body as { items: ListItem[] }).items.flatMap((item) => item.brief_ids);
  const briefs = await Promise.all(briefIds.map((id) => get(base, `/api/v1/risk/briefs/${id}`)));
  const unresolved = expectStatus(
    await exchange(base, 'POST', '/api/v1/risk/assessments', {
      as_of: null,
      source_system: 'rest_mock',
    }),
    422,
  );
  return {
    exchanges: [run, detail, list, unresolved],
    briefs: briefs.map((item) => expectStatus(item, 200)),
  };
}

async function main(): Promise<number> {
  const configuredUrl = configuredDatabaseUrl();
  const backend = await startIsolatedBackend({
    suffix: E2E_SUFFIX,
    configuredUrl,
    port: 0,
    quiet: true,
  });
  try {
    const base = backend.baseUrl;
    mkdirSync(FIXTURES, { recursive: true });
    const files: Record<string, string[]> = {};

    const runRequest = { as_of: ACCEPTANCE_AS_OF, source_system: SOURCE_SYSTEM };
    const firstRun: Exchange = {
      method: 'POST',
      path: '/api/v1/risk/assessments',
      request_body: runRequest,
      status: backend.assessment.status,
      body: backend.assessment.body,
    };
    const repeatRun = expectStatus(
      await exchange(base, 'POST', '/api/v1/risk/assessments', runRequest),
      200,
    );
    files['assessment-runs.json'] = write('assessment-runs.json', [firstRun, repeatRun]);

    const health = expectStatus(await get(base, '/api/v1/health'), 200);
    files['health.json'] = write('health.json', [health]);

    const sources = expectStatus(await get(base, '/api/v1/sources'), 200);
    const sourceNames = (sources.body as { sources: { source: string }[] }).sources.map(
      (item) => item.source,
    );
    const sourceHealth = await Promise.all(
      sourceNames.map((name) => get(base, `/api/v1/sources/${encodeURIComponent(name)}/health`)),
    );
    files['sources.json'] = write('sources.json', [sources, ...sourceHealth]);

    const runs = expectStatus(await get(base, `/api/v1/ingestion/runs?${PAGE}`), 200);
    const runIds = (runs.body as { items: { run_id: string }[] }).items.map((item) => item.run_id);
    const runDetails = await Promise.all(
      runIds.map((id) => get(base, `/api/v1/ingestion/runs/${id}`)),
    );
    const runErrors = await Promise.all(
      runIds.map((id) => get(base, `/api/v1/ingestion/runs/${id}/errors?${PAGE}`)),
    );
    files['ingestion.json'] = write('ingestion.json', [runs, ...runDetails, ...runErrors]);

    const entities = await Promise.all(
      ENTITY_TYPES.map((type) => get(base, `/api/v1/entities/${type}?${PAGE}`)),
    );
    files['entities.json'] = write(
      'entities.json',
      entities.map((item) => expectStatus(item, 200)),
    );

    const metrics = expectStatus(await get(base, '/api/v1/metrics/ingestion'), 200);
    files['metrics.json'] = write('metrics.json', [metrics]);

    const list = expectStatus(
      await get(base, `/api/v1/risk/assessments?as_of=${ACCEPTANCE_AS_OF}&${PAGE}`),
      200,
    );
    files['assessments.json'] = write('assessments.json', [list]);

    const briefed = (list.body as { items: ListItem[] }).items.filter(
      (item) => item.brief_ids.length > 0,
    );
    const details = await Promise.all(
      briefed.map((item) => get(base, `/api/v1/risk/assessments/${item.id}`)),
    );
    files['assessment-details.json'] = write(
      'assessment-details.json',
      details.map((item) => expectStatus(item, 200)),
    );

    const briefIds = briefed.flatMap((item) => item.brief_ids);
    const briefs = (
      await Promise.all(briefIds.map((id) => get(base, `/api/v1/risk/briefs/${id}`)))
    ).map((item) => expectStatus(item, 200));

    const chains = await Promise.all(
      briefIds.map((id) => get(base, `/api/v1/risk/briefs/${id}/decisions`)),
    );
    files['decisions.json'] = write(
      'decisions.json',
      chains.map((item) => expectStatus(item, 200)),
    );

    files['decision-flow.json'] = write(
      'decision-flow.json',
      await recordDecisionFlow(base, briefIds[0], briefs[0]),
    );
    const auto = await recordAutoRun(base);
    files['auto-run.json'] = write('auto-run.json', auto.exchanges);
    files['briefs.json'] = write('briefs.json', [...briefs, ...auto.briefs]);

    const openapi = await fetch(`${base}/openapi.json`);
    if (openapi.status !== 200) throw new Error(`GET /openapi.json answered ${openapi.status}`);
    writeFileSync(`${FIXTURES}openapi.json`, `${JSON.stringify(await openapi.json(), null, 2)}\n`);
    files['openapi.json'] = ['GET /openapi.json 200'];

    const isolated = isolatedUrl(configuredUrl, E2E_SUFFIX);
    const provenance = {
      recorded_at: new Date().toISOString(),
      commit: git('rev-parse', 'HEAD'),
      backend_paths: BACKEND_PATHS,
      backend_paths_clean: git('status', '--porcelain', '--', ...BACKEND_PATHS) === '',
      database: databaseOf(isolated),
      database_revision: await databaseRevision(isolated, databaseOf(configuredUrl)),
      as_of: ACCEPTANCE_AS_OF,
      source_system: SOURCE_SYSTEM,
      api_version: (health.body as { version: string }).version,
      files,
    };
    writeFileSync(`${FIXTURES}PROVENANCE.json`, `${JSON.stringify(provenance, null, 2)}\n`);
    process.stdout.write(
      `[record] ${Object.keys(files).length} fixture files and PROVENANCE.json written\n`,
    );
    return 0;
  } finally {
    await backend.stop();
  }
}

main().then(
  (status) => process.exit(status),
  (error: unknown) => {
    if (error instanceof EnvironmentRefused) {
      process.stderr.write(`record-fixtures: ${error.message}\n`);
      process.exit(2);
    }
    throw error;
  },
);
