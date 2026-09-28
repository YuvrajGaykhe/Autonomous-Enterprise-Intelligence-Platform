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

/** The recorded brief exchanges, CUST-007 first, in the list's order. */
export function recordedBriefs(): RecordedExchange[] {
  return loadExchanges('briefs.json');
}
