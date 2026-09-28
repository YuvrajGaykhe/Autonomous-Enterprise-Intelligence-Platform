/**
 * The recorded fixtures (spec §12.2). They are read here and in tests only: ESLint forbids
 * `src/**` importing anything under `tests/`.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

// import.meta.dirname, not import.meta.url: under jsdom, Vitest's module URL is not a file URL.
export const FRONTEND_ROOT = resolve(import.meta.dirname, '../..');
export const FIXTURE_DIR = `${resolve(FRONTEND_ROOT, 'tests/fixtures')}/`;
export const REPO_ROOT = `${resolve(FRONTEND_ROOT, '..')}/`;

export interface RecordedExchange {
  method: 'GET' | 'POST';
  path: string;
  request_body?: unknown;
  status: number;
  body: unknown;
}

/** Every exchange file, by name. `openapi.json` and `PROVENANCE.json` are not exchanges. */
export const EXCHANGE_FILES = readdirSync(FIXTURE_DIR)
  .filter((name) => name.endsWith('.json') && name !== 'openapi.json' && name !== 'PROVENANCE.json')
  .sort();

export function loadJson(name: string): unknown {
  return JSON.parse(readFileSync(`${FIXTURE_DIR}${name}`, 'utf8')) as unknown;
}

export function loadExchanges(name: string): RecordedExchange[] {
  return loadJson(name) as RecordedExchange[];
}

/** The one recorded exchange for a method and an exact path (query included). */
export function recorded(name: string, method: 'GET' | 'POST', path: string): RecordedExchange {
  const found = loadExchanges(name).filter((item) => item.method === method && item.path === path);
  if (found.length !== 1) throw new Error(`${name} has ${found.length} ${method} ${path}`);
  return found[0] as RecordedExchange;
}

/** The first recorded exchange whose path starts with `prefix`. */
export function recordedPrefix(name: string, prefix: string): RecordedExchange {
  const found = loadExchanges(name).find((item) => item.path.startsWith(prefix));
  if (found === undefined) throw new Error(`${name} has no exchange under ${prefix}`);
  return found;
}

/** Every recorded brief: the three at 2026-09-18, then the Auto run's (owner ruling 3, F1). */
export function allRecordedBriefs(): RecordedExchange[] {
  return loadExchanges('briefs.json');
}

/** The recorded briefs at 2026-09-18 (§3), CUST-007 first, in the list's order. */
export function recordedBriefs(): RecordedExchange[] {
  return allRecordedBriefs().filter(
    (exchange) =>
      (exchange.body as { payload: { scope: { as_of: string } } }).payload.scope.as_of ===
      '2026-09-18',
  );
}

/** The recorded body of the one exchange for a method and path, typed by the caller. */
export function recordedBody<T>(name: string, method: 'GET' | 'POST', path: string): T {
  return recorded(name, method, path).body as T;
}

/** The recorded assessment list at 2026-09-18, every page. */
export function recordedAssessmentList<T>(): T {
  return recordedPrefix('assessments.json', '/api/v1/risk/assessments?as_of=2026-09-18').body as T;
}

/** The recorded entity list of one type. */
export function recordedEntities<T>(type: string): T {
  return recorded('entities.json', 'GET', `/api/v1/entities/${type}?limit=500&offset=0`).body as T;
}

/** The decision flow, recorded after every other fixture because it writes (§7.5, §7.6). */
export function decisionFlow(): RecordedExchange[] {
  return loadExchanges('decision-flow.json');
}

/** The Auto run (as_of null), the date it resolved to, that snapshot and its refusals. */
export function autoRun(): RecordedExchange[] {
  return loadExchanges('auto-run.json');
}
