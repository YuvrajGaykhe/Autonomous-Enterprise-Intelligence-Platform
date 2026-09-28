/**
 * `npm run record-fixtures`: record the frontend's test fixtures from the real API (spec §12.2).
 *
 * The API is the working tree's, served over `<database>_frontend_e2e`, which is recreated from
 * clean and assessed at 2026-09-18 first (§12.3). Every exchange is written exactly as parsed
 * from the wire, and `PROVENANCE.json` states where the recording came from. Nothing here
 * edits a recorded body. Never run it while the end-to-end tests run: both use the same
 * isolated database.
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
    const briefs = await Promise.all(briefIds.map((id) => get(base, `/api/v1/risk/briefs/${id}`)));
    files['briefs.json'] = write(
      'briefs.json',
      briefs.map((item) => expectStatus(item, 200)),
    );

    const chains = await Promise.all(
      briefIds.map((id) => get(base, `/api/v1/risk/briefs/${id}/decisions`)),
    );
    files['decisions.json'] = write(
      'decisions.json',
      chains.map((item) => expectStatus(item, 200)),
    );

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
