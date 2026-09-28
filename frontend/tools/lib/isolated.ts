/**
 * The frontend's isolated databases and the working-tree API over them (spec §12.3, R-F-1).
 *
 * Every run recreates its database from clean, in this order:
 *   1. drop and create `<configured database><suffix>` through the `postgres`
 *      maintenance database;
 *   2. `.venv/bin/alembic upgrade head`;
 *   3. `.venv/bin/python scripts/ingest_demo.py`;
 *   4. serve `.venv/bin/uvicorn app.main:app` on a loopback port;
 *   5. `POST /api/v1/risk/assessments` at the acceptance date.
 *
 * The invariants are what make this safe to run next to the owner's stack:
 * - a name without the `_frontend` or `_frontend_e2e` suffix is refused, so
 *   the development database is never opened, dropped or written;
 * - an unreachable PostgreSQL, a missing virtualenv or a busy port is an
 *   `EnvironmentRefused`, which the commands turn into exit status 2, and
 *   there is never a fallback to another database or stack;
 * - no URL is ever printed, because a URL can carry a credential;
 * - Docker is never touched.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createServer } from 'node:net';
import pg from 'pg';

import { REPO_ROOT } from './settings.ts';

/** The development database suffix; its API is served on DEV_PORT. */
export const DEV_SUFFIX = '_frontend';
/** The end-to-end database suffix; its API is served on an OS-assigned port. */
export const E2E_SUFFIX = '_frontend_e2e';
export const DEV_PORT = 8010;
export const LOOPBACK = '127.0.0.1';
/** The date the fixtures and the end-to-end tests assess at (D-F-14). */
export const ACCEPTANCE_AS_OF = '2026-09-18';
export const SOURCE_SYSTEM = 'csv_demo';

const MAINTENANCE_DATABASE = 'postgres';
const CONNECT_TIMEOUT_MS = 5_000;
const HEALTH_TIMEOUT_MS = 60_000;
const ISOLATED_NAME = /^[a-z][a-z0-9_]*_frontend(?:_e2e)?$/;
const CONFIGURED_NAME = /^[a-z][a-z0-9_]*$/;

type Suffix = typeof DEV_SUFFIX | typeof E2E_SUFFIX;

/** The isolated environment cannot be used or started. The commands exit with status 2. */
export class EnvironmentRefused extends Error {
  override name = 'EnvironmentRefused';
}

/** Refuse any isolated database name the guard does not admit. */
export function checkIsolatedName(name: string, configured: string): string {
  if (!ISOLATED_NAME.test(name) || name === configured) {
    throw new EnvironmentRefused(
      `refusing database ${JSON.stringify(name)}: an isolated frontend database must match ` +
        `[a-z][a-z0-9_]*_frontend or [a-z][a-z0-9_]*_frontend_e2e and differ from the configured ` +
        `database`,
    );
  }
  return name;
}

/** The database a URL names, decoded. */
export function databaseOf(url: string): string {
  return decodeURIComponent(new URL(url).pathname.replace(/^\//, ''));
}

function withDatabase(url: string, database: string): string {
  const parsed = new URL(url);
  parsed.pathname = `/${encodeURIComponent(database)}`;
  return parsed.toString();
}

/** `<configured database><suffix>` on the configured server, with its address and credentials. */
export function isolatedUrl(configuredUrl: string, suffix: Suffix): string {
  let configured: string;
  try {
    configured = databaseOf(configuredUrl);
  } catch {
    throw new EnvironmentRefused('the configured database URL cannot be parsed');
  }
  if (!CONFIGURED_NAME.test(configured)) {
    throw new EnvironmentRefused(
      `the configured database name ${JSON.stringify(configured)} is not a plain identifier`,
    );
  }
  return withDatabase(configuredUrl, checkIsolatedName(`${configured}${suffix}`, configured));
}

/** A SQLAlchemy URL (which may name a driver, as in postgresql+psycopg2) for node-postgres. */
function nodePostgresUrl(url: string): string {
  const parsed = new URL(url);
  return `postgresql://${parsed.href.slice(parsed.protocol.length + 2)}`;
}

/** Drop and create the isolated database. Refuses any name the guard does not admit. */
export async function recreateDatabase(url: string, configured: string): Promise<void> {
  const name = checkIsolatedName(databaseOf(url), configured);
  const client = new pg.Client({
    connectionString: nodePostgresUrl(withDatabase(url, MAINTENANCE_DATABASE)),
    connectionTimeoutMillis: CONNECT_TIMEOUT_MS,
  });
  try {
    await client.connect();
    await client.query(`DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`);
    await client.query(`CREATE DATABASE "${name}"`);
  } catch (error) {
    throw new EnvironmentRefused(
      `the isolated database ${name} could not be recreated through the ` +
        `${MAINTENANCE_DATABASE} maintenance database (${errorKind(error)}); ` +
        `is PostgreSQL reachable?`,
    );
  } finally {
    await client.end().catch(() => undefined);
  }
}

/** The Alembic revision an isolated database is at. Refuses any other database. */
export async function databaseRevision(url: string, configured: string): Promise<string> {
  checkIsolatedName(databaseOf(url), configured);
  const client = new pg.Client({
    connectionString: nodePostgresUrl(url),
    connectionTimeoutMillis: CONNECT_TIMEOUT_MS,
  });
  try {
    await client.connect();
    const result = await client.query<{ version_num: string }>(
      'SELECT version_num FROM alembic_version',
    );
    const revisions = result.rows.map((row) => row.version_num);
    if (revisions.length !== 1 || revisions[0] === undefined) {
      throw new EnvironmentRefused(`expected one Alembic revision, found ${revisions.length}`);
    }
    return revisions[0];
  } finally {
    await client.end().catch(() => undefined);
  }
}

function errorKind(error: unknown): string {
  if (error instanceof Error) {
    const code = (error as { code?: unknown }).code;
    return typeof code === 'string' ? code : error.name;
  }
  return 'unknown error';
}

function venvTool(tool: string): string {
  const path = `${REPO_ROOT}.venv/bin/${tool}`;
  if (!existsSync(path)) {
    throw new EnvironmentRefused(`.venv/bin/${tool} is missing: run make install first`);
  }
  return path;
}

function backendEnvironment(url: string): NodeJS.ProcessEnv {
  return { ...process.env, DATABASE_URL: url, PYTHONDONTWRITEBYTECODE: '1' };
}

/** Run one backend command to completion in the repository root. */
async function runStep(label: string, argv: readonly string[], url: string, quiet: boolean) {
  const [command, ...args] = argv;
  if (command === undefined) throw new Error('empty command');
  const child = spawn(command, args, {
    cwd: REPO_ROOT,
    env: backendEnvironment(url),
    stdio: ['ignore', quiet ? 'pipe' : 'inherit', quiet ? 'pipe' : 'inherit'],
  });
  const output: string[] = [];
  child.stdout?.on('data', (chunk: Buffer) => output.push(chunk.toString('utf8')));
  child.stderr?.on('data', (chunk: Buffer) => output.push(chunk.toString('utf8')));
  const status = await new Promise<number | null>((resolve) => child.on('close', resolve));
  if (status !== 0) {
    if (quiet) process.stderr.write(output.join('').slice(-4_000));
    throw new EnvironmentRefused(`${label} exited with status ${String(status)}`);
  }
}

/** A loopback port that was free a moment ago. */
export async function freePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, LOOPBACK, () => {
      const address = server.address();
      server.close(() => {
        if (address !== null && typeof address === 'object') resolve(address.port);
        else reject(new Error('no port assigned'));
      });
    });
  });
}

/** Refuse a port another process is listening on, rather than sharing or taking it. */
export async function requirePortFree(port: number): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const server = createServer();
    server.once('error', () =>
      reject(new EnvironmentRefused(`port ${port} on ${LOOPBACK} is already in use`)),
    );
    server.listen(port, LOOPBACK, () => server.close(() => resolve()));
  });
}

async function waitForHealth(baseUrl: string, child: ChildProcess): Promise<void> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new EnvironmentRefused(`the API exited with status ${child.exitCode} during startup`);
    }
    try {
      const response = await fetch(`${baseUrl}/api/v1/health`);
      if (response.status === 200) return;
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new EnvironmentRefused(`the API was not healthy within ${HEALTH_TIMEOUT_MS / 1000} s`);
}

export interface AssessmentSummary {
  status: number;
  items: number;
  briefs: number;
  /** The response body, exactly as parsed from the wire. */
  body: unknown;
}

/** POST the acceptance assessment; a clean database must answer 201. */
export async function assess(baseUrl: string): Promise<AssessmentSummary> {
  const response = await fetch(`${baseUrl}/api/v1/risk/assessments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ as_of: ACCEPTANCE_AS_OF, source_system: SOURCE_SYSTEM }),
  });
  const body = (await response.json()) as { items?: { brief_id: string | null }[] };
  const items = body.items ?? [];
  if (response.status !== 201) {
    throw new EnvironmentRefused(`the acceptance assessment answered ${response.status}, not 201`);
  }
  return {
    status: response.status,
    items: items.length,
    briefs: items.filter((item) => item.brief_id !== null).length,
    body,
  };
}

export interface IsolatedBackend {
  database: string;
  port: number;
  baseUrl: string;
  assessment: AssessmentSummary;
  process: ChildProcess;
  stop(): Promise<void>;
}

export interface StartOptions {
  suffix: Suffix;
  configuredUrl: string;
  /** A fixed port (development) or 0 for an OS-assigned one (end-to-end). */
  port: number;
  /** Capture the backend's output instead of passing it through. */
  quiet: boolean;
  log?: (line: string) => void;
}

/** Recreate the isolated database from clean and serve the working-tree API over it. */
export async function startIsolatedBackend(options: StartOptions): Promise<IsolatedBackend> {
  const log = options.log ?? ((line: string) => process.stdout.write(`${line}\n`));
  const configured = databaseOf(options.configuredUrl);
  const url = isolatedUrl(options.configuredUrl, options.suffix);
  const database = databaseOf(url);
  const alembic = venvTool('alembic');
  const python = venvTool('python');
  const uvicorn = venvTool('uvicorn');
  const port = options.port === 0 ? await freePort() : options.port;
  await requirePortFree(port);

  log(`[isolated] recreating database ${database}`);
  await recreateDatabase(url, configured);
  log('[isolated] alembic upgrade head');
  await runStep('alembic upgrade head', [alembic, 'upgrade', 'head'], url, options.quiet);
  log('[isolated] ingesting the demo dataset');
  await runStep('scripts/ingest_demo.py', [python, 'scripts/ingest_demo.py'], url, options.quiet);

  const baseUrl = `http://${LOOPBACK}:${port}`;
  log(`[isolated] serving the working-tree API on ${baseUrl}`);
  const child = spawn(
    uvicorn,
    ['app.main:app', '--host', LOOPBACK, '--port', String(port), '--no-access-log'],
    {
      cwd: REPO_ROOT,
      env: backendEnvironment(url),
      stdio: ['ignore', options.quiet ? 'ignore' : 'inherit', options.quiet ? 'ignore' : 'inherit'],
    },
  );
  const stop = async (): Promise<void> => {
    if (child.exitCode !== null || child.signalCode !== null) return;
    const closed = new Promise((resolve) => child.once('close', resolve));
    child.kill('SIGTERM');
    await closed;
  };
  try {
    await waitForHealth(baseUrl, child);
    const assessment = await assess(baseUrl);
    log(
      `[isolated] assessed at ${ACCEPTANCE_AS_OF}: ${assessment.items} customers, ` +
        `${assessment.briefs} briefs (HTTP ${assessment.status})`,
    );
    return { database, port, baseUrl, assessment, process: child, stop };
  } catch (error) {
    await stop();
    throw error;
  }
}
