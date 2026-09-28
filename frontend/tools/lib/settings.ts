/**
 * The backend's database settings, read the way `app/core/config.py` reads them
 * (spec §12.3, R-F-1).
 *
 * pydantic-settings takes each value from the process environment first and
 * from the repository `.env` second, matching names case-insensitively.
 * `DATABASE_URL` wins when it is set; otherwise the URL is built from the
 * `POSTGRES_*` values and their defaults. This module only reads: it never
 * prints a URL, because a URL can carry a credential.
 */

import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/** The repository root: `frontend/tools/lib` is three levels below it. */
export const REPO_ROOT = fileURLToPath(new URL('../../../', import.meta.url));

type Environment = Readonly<Record<string, string | undefined>>;

/** The backend's own defaults, by setting name (app/core/config.py). */
const DEFAULTS = new Map<string, string>([
  ['POSTGRES_HOST', 'localhost'],
  ['POSTGRES_PORT', '5432'],
  ['POSTGRES_DB', 'ai_ceo_layer1'],
  ['POSTGRES_USER', 'ai_ceo'],
  ['POSTGRES_PASSWORD', 'changeme'],
]);

/** Parse the simple `NAME=value` lines of a dotenv file; comments and blanks are skipped. */
export function parseDotenv(text: string): Map<string, string> {
  const values = new Map<string, string>();
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/^export\s+/, '');
    if (line === '' || line.startsWith('#')) continue;
    const separator = line.indexOf('=');
    if (separator <= 0) continue;
    const name = line.slice(0, separator).trim().toUpperCase();
    const value = line.slice(separator + 1).trim();
    const quoted = /^(["'])(.*)\1$/.exec(value);
    values.set(name, quoted ? (quoted[2] ?? '') : value);
  }
  return values;
}

function lookup(
  name: string,
  environment: Environment,
  dotenv: ReadonlyMap<string, string>,
): string | undefined {
  for (const [key, value] of Object.entries(environment)) {
    if (key.toUpperCase() === name && value !== undefined) return value;
  }
  return dotenv.get(name);
}

/** The URL the backend would connect to, before any isolation is applied. */
export function configuredDatabaseUrl(
  environment: Environment = process.env,
  dotenvPath = `${REPO_ROOT}.env`,
): string {
  const dotenv = existsSync(dotenvPath)
    ? parseDotenv(readFileSync(dotenvPath, 'utf8'))
    : new Map<string, string>();
  const explicit = lookup('DATABASE_URL', environment, dotenv);
  if (explicit) return explicit;
  const setting = (name: string): string =>
    lookup(name, environment, dotenv) ?? DEFAULTS.get(name) ?? '';
  const user = encodeURIComponent(setting('POSTGRES_USER'));
  const credential = encodeURIComponent(setting('POSTGRES_PASSWORD'));
  return (
    `postgresql://${user}:${credential}` +
    `@${setting('POSTGRES_HOST')}:${setting('POSTGRES_PORT')}/${setting('POSTGRES_DB')}`
  );
}
