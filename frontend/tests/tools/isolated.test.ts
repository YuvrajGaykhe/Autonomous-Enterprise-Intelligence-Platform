/**
 * The isolated-database tooling (spec §12.3, R-F-1, AC-F-17): it refuses every database but its
 * own two, derives them from the backend's own settings, and exits 2 with no fallback when
 * PostgreSQL is unreachable. Nothing here connects to a database that exists.
 */

import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  DEV_PORT,
  DEV_SUFFIX,
  E2E_SUFFIX,
  EnvironmentRefused,
  checkIsolatedName,
  databaseOf,
  freePort,
  isolatedUrl,
  recreateDatabase,
  requirePortFree,
} from '../../tools/lib/isolated.ts';
import { configuredDatabaseUrl, parseDotenv } from '../../tools/lib/settings.ts';
import { FRONTEND_ROOT } from '../support/fixtures';

const CONFIGURED = 'postgresql://someone:fake-credential-7c1@db.example:5432/ai_ceo_layer1';

function dotenvFile(text: string): string {
  const directory = mkdtempSync(join(tmpdir(), 'aiceohq-'));
  const path = join(directory, '.env');
  writeFileSync(path, text);
  return path;
}

describe('the isolated database names', () => {
  it('are the configured database plus _frontend or _frontend_e2e', () => {
    expect(databaseOf(isolatedUrl(CONFIGURED, DEV_SUFFIX))).toBe('ai_ceo_layer1_frontend');
    expect(databaseOf(isolatedUrl(CONFIGURED, E2E_SUFFIX))).toBe('ai_ceo_layer1_frontend_e2e');
  });

  it('keep the configured server, driver and credentials', () => {
    const url = new URL(isolatedUrl(`${CONFIGURED}?sslmode=require`, DEV_SUFFIX));
    expect(url.host).toBe('db.example:5432');
    expect(url.username).toBe('someone');
    expect(url.search).toBe('?sslmode=require');
    const withDriver = isolatedUrl(
      CONFIGURED.replace('postgresql', 'postgresql+psycopg2'),
      E2E_SUFFIX,
    );
    expect(withDriver.startsWith('postgresql+psycopg2://')).toBe(true);
  });

  it.each([
    'ai_ceo_layer1',
    'ai_ceo_layer1_test',
    'ai_ceo_layer1_vs01',
    'ai_ceo_layer1_frontend_x',
    'ai_ceo_layer1_frontend_e2e_test',
    'AI_CEO_frontend',
    'postgres',
    '_frontend',
  ])('refuse %j', (name) => {
    expect(() => checkIsolatedName(name, 'ai_ceo_layer1')).toThrow(EnvironmentRefused);
  });

  it('refuse a name equal to the configured database, even with the suffix', () => {
    expect(() => checkIsolatedName('shop_frontend', 'shop_frontend')).toThrow(EnvironmentRefused);
  });

  it('refuse a configured database that is not a plain identifier, or an unparseable URL', () => {
    expect(() => isolatedUrl('postgresql://u:p@h:5432/Weird-Name', DEV_SUFFIX)).toThrow(
      EnvironmentRefused,
    );
    expect(() => isolatedUrl('not a url', DEV_SUFFIX)).toThrow(EnvironmentRefused);
  });

  it('are refused before any connection when the guard does not admit them', async () => {
    await expect(recreateDatabase(CONFIGURED, 'ai_ceo_layer1')).rejects.toThrow(
      /refusing database "ai_ceo_layer1"/,
    );
  });
});

describe("the backend's settings", () => {
  it('prefer DATABASE_URL from the environment, then from .env', () => {
    const dotenv = dotenvFile('DATABASE_URL=postgresql://a:b@from-file:1/filedb\n');
    expect(configuredDatabaseUrl({ DATABASE_URL: 'postgresql://a:b@env:1/envdb' }, dotenv)).toBe(
      'postgresql://a:b@env:1/envdb',
    );
    expect(configuredDatabaseUrl({}, dotenv)).toBe('postgresql://a:b@from-file:1/filedb');
  });

  it('build the URL from POSTGRES_* when DATABASE_URL is empty, environment first', () => {
    const dotenv = dotenvFile(
      [
        '# comment',
        'export POSTGRES_HOST="filehost"',
        'POSTGRES_DB=filedb',
        'not a setting',
        '=nameless',
      ].join('\n'),
    );
    expect(
      configuredDatabaseUrl(
        { DATABASE_URL: '', postgres_port: '6543', POSTGRES_USER: 'u s' },
        dotenv,
      ),
    ).toBe('postgresql://u%20s:changeme@filehost:6543/filedb');
  });

  it("fall back to the backend's defaults with no .env at all", () => {
    expect(configuredDatabaseUrl({}, '/nonexistent/.env')).toBe(
      'postgresql://ai_ceo:changeme@localhost:5432/ai_ceo_layer1',
    );
  });

  it('parse quoted and unquoted dotenv values', () => {
    expect(parseDotenv("A='one'\nb = two\n")).toEqual(
      new Map([
        ['A', 'one'],
        ['B', 'two'],
      ]),
    );
  });
});

describe('ports', () => {
  it('serve development on 127.0.0.1:8010', () => {
    expect(DEV_PORT).toBe(8010);
  });

  it('refuse a port that another process holds, rather than share it', async () => {
    const { createServer } = await import('node:net');
    const port = await freePort();
    const holder = createServer().listen(port, '127.0.0.1');
    await new Promise((done) => holder.once('listening', done));
    try {
      await expect(requirePortFree(port)).rejects.toThrow(
        `port ${port} on 127.0.0.1 is already in use`,
      );
    } finally {
      holder.close();
    }
    await expect(requirePortFree(port)).resolves.toBeUndefined();
  });
});

const UNREACHABLE = {
  ...process.env,
  DATABASE_URL: 'postgresql://nobody:fake-credential-7c1@127.0.0.1:1/ai_ceo_layer1',
};

function runTool(script: string, ...args: string[]) {
  const result = spawnSync(process.execPath, [resolve(FRONTEND_ROOT, script), ...args], {
    cwd: FRONTEND_ROOT,
    encoding: 'utf8',
    timeout: 30_000,
    env: UNREACHABLE,
  });
  return { status: result.status, output: `${result.stdout}${result.stderr}` };
}

function expectNoCredential(output: string) {
  expect(output).not.toContain('fake-credential-7c1');
  expect(output).not.toContain('postgresql://');
}

describe('the tools without PostgreSQL', () => {
  it('record-fixtures exits 2 before any migration, never falls back, and prints no credential', () => {
    const { status, output } = runTool('tools/record-fixtures.ts');

    expect(status).toBe(2);
    expect(output).toContain('ai_ceo_layer1_frontend_e2e could not be recreated');
    expect(output).toContain('ECONNREFUSED');
    expect(output).not.toContain('alembic');
    expectNoCredential(output);
  });

  it('frontend-backend exits 2 and prints no credential', () => {
    // Port 8010 is checked first, so a developer's running backend is refused, not replaced.
    const { status, output } = runTool('tools/backend.ts');

    expect(status).toBe(2);
    expect(output).toMatch(
      /ai_ceo_layer1_frontend could not be recreated .*ECONNREFUSED|port 8010 on 127\.0\.0\.1 is already in use/,
    );
    expect(output).not.toContain('alembic');
    expectNoCredential(output);
  });

  it('frontend-backend rejects arguments with exit status 2', () => {
    const { status, output } = runTool('tools/backend.ts', 'x');

    expect(status).toBe(2);
    expect(output).toContain('usage: node tools/backend.ts');
  });
});
