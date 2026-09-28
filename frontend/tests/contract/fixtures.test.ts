/**
 * The recorded fixtures are genuine and this frontend's schemas accept them (spec §12.2, AC-F-16).
 *
 * The anchors are the specification's §3 values, observed at `733b19b` and re-measured at F1:
 * the three payload hashes, the pinned Layer 1 fingerprint and the golden CUST-007 narrative,
 * which is read here and never written.
 */

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';
import type { z } from 'zod';

import { briefPayloadV1 } from '@/api/schemas/briefPayloadV1';
import { ENTITY_TYPES, entityPages } from '@/api/schemas/entities';
import {
  errorListResponse,
  healthResponse,
  ingestionMetricsResponse,
  ingestionRunResponse,
  runListResponse,
  sourceHealthResponse,
  sourceListResponse,
} from '@/api/schemas/operations';
import {
  assessmentDetailResponse,
  assessmentListResponse,
  assessmentRunResponse,
  briefResponse,
  decisionHistoryResponse,
} from '@/api/schemas/risk';

import {
  EXCHANGE_FILES,
  FIXTURE_DIR,
  REPO_ROOT,
  loadExchanges,
  loadJson,
  recordedBriefs,
  type RecordedExchange,
} from '../support/fixtures';

/** Specification §3 (OBSERVED at 733b19b; re-measured at F1's baseline). */
const PINNED_FINGERPRINT = '1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00';
const PAYLOAD_HASHES = {
  'CUST-007': 'e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946',
  'CUST-025': '08c99ced40996611c8f7bb4ea48e918fabe0e9cd68390122d0f86faa50738770',
  'CUST-036': 'a6240ac1edd4890724568adc7a8bd8f99add305638b9dcb179429ae67d06b637',
} as const;
const MIGRATION_HEAD = '070e4968a497';
const GOLDEN_BRIEF = 'tests/golden/vs01_cust007_brief.txt';

const UUID = '[0-9a-f-]{36}';
const ROUTES: readonly (readonly [RegExp, z.ZodType])[] = [
  [/^GET \/api\/v1\/health$/, healthResponse],
  [/^GET \/api\/v1\/sources$/, sourceListResponse],
  [/^GET \/api\/v1\/sources\/[a-z_]+\/health$/, sourceHealthResponse],
  [/^GET \/api\/v1\/ingestion\/runs\?/, runListResponse],
  [new RegExp(`^GET /api/v1/ingestion/runs/${UUID}$`), ingestionRunResponse],
  [new RegExp(`^GET /api/v1/ingestion/runs/${UUID}/errors\\?`), errorListResponse],
  [/^GET \/api\/v1\/metrics\/ingestion$/, ingestionMetricsResponse],
  [/^POST \/api\/v1\/risk\/assessments$/, assessmentRunResponse],
  [/^GET \/api\/v1\/risk\/assessments\?/, assessmentListResponse],
  [new RegExp(`^GET /api/v1/risk/assessments/${UUID}$`), assessmentDetailResponse],
  [new RegExp(`^GET /api/v1/risk/briefs/${UUID}$`), briefResponse],
  [new RegExp(`^GET /api/v1/risk/briefs/${UUID}/decisions$`), decisionHistoryResponse],
  ...ENTITY_TYPES.map(
    (type) => [new RegExp(`^GET /api/v1/entities/${type}\\?`), entityPages[type]] as const,
  ),
];

function schemaFor(exchange: RecordedExchange): z.ZodType {
  const key = `${exchange.method} ${exchange.path}`;
  const matches = ROUTES.filter(([pattern]) => pattern.test(key));
  if (matches.length !== 1) throw new Error(`${key} matches ${matches.length} routes`);
  return (matches[0] as readonly [RegExp, z.ZodType])[1];
}

/** M1's canonical_json: sorted keys at every depth, compact separators, non-ASCII as itself. */
function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const members = Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`);
    return `{${members.join(',')}}`;
  }
  return JSON.stringify(value);
}

interface BriefBody {
  payload_hash: string;
  narrative: string;
  payload: { customer: { id: string }; scope: { layer1_fingerprint: string } };
}

const briefs = recordedBriefs().map((exchange) => exchange.body as BriefBody);

describe('every recorded exchange', () => {
  const all = EXCHANGE_FILES.flatMap((file) =>
    loadExchanges(file).map((exchange) => [file, exchange] as const),
  );

  it('covers the fixture set of PROVENANCE.json', () => {
    const provenance = loadJson('PROVENANCE.json') as { files: Record<string, string[]> };
    expect(Object.keys(provenance.files).sort()).toEqual(
      [...EXCHANGE_FILES, 'openapi.json'].sort(),
    );
    for (const file of EXCHANGE_FILES) {
      expect(provenance.files[file]).toEqual(
        loadExchanges(file).map((item) => `${item.method} ${item.path} ${item.status}`),
      );
    }
  });

  it.each(
    all.map(([file, exchange]) => [`${file}: ${exchange.method} ${exchange.path}`, exchange]),
  )('parses strictly: %s', (_name, exchange) => {
    const parsed = schemaFor(exchange).safeParse(exchange.body);
    expect(parsed.error?.issues ?? []).toEqual([]);
  });
});

describe('the recorded briefs', () => {
  it('are exactly the three briefs of §3, CUST-007 first', () => {
    expect(briefs.map((brief) => brief.payload.customer.id)).toEqual([
      'CUST-007',
      'CUST-025',
      'CUST-036',
    ]);
  });

  it.each(briefs.map((brief) => [brief.payload.customer.id, brief] as const))(
    '%s parses as payload version 1 and carries its §3 hash and the pinned fingerprint',
    (customer, brief) => {
      expect(briefPayloadV1.safeParse(brief.payload).error?.issues ?? []).toEqual([]);
      expect(brief.payload_hash).toBe(PAYLOAD_HASHES[customer as keyof typeof PAYLOAD_HASHES]);
      expect(brief.payload.scope.layer1_fingerprint).toBe(PINNED_FINGERPRINT);
    },
  );

  it.each(briefs.map((brief) => [brief.payload.customer.id, brief] as const))(
    "%s's payload hashes to its payload_hash under canonical_json (a test-only provenance proof)",
    (_customer, brief) => {
      const digest = createHash('sha256')
        .update(canonicalJson(brief.payload), 'utf8')
        .digest('hex');
      expect(digest).toBe(brief.payload_hash);
    },
  );

  it("CUST-007's narrative is byte-identical to the golden brief", () => {
    const golden = readFileSync(`${REPO_ROOT}${GOLDEN_BRIEF}`, 'utf8');
    expect(briefs[0]?.narrative).toBe(golden);
  });
});

describe('PROVENANCE.json', () => {
  const provenance = loadJson('PROVENANCE.json') as {
    commit: string;
    backend_paths: string[];
    backend_paths_clean: boolean;
    database: string;
    database_revision: string;
    as_of: string;
    source_system: string;
    recorded_at: string;
  };

  it('records a clean isolated database at the migration head, assessed at 2026-09-18', () => {
    expect(provenance.database).toMatch(/^[a-z][a-z0-9_]*_frontend_e2e$/);
    expect(provenance.database_revision).toBe(MIGRATION_HEAD);
    expect(provenance.as_of).toBe('2026-09-18');
    expect(provenance.source_system).toBe('csv_demo');
    expect(Number.isNaN(Date.parse(provenance.recorded_at))).toBe(false);
  });

  it('names a commit whose backend is the backend the fixtures still describe', () => {
    expect(provenance.backend_paths_clean).toBe(true);
    expect(provenance.backend_paths).toEqual([
      'app',
      'config',
      'migrations',
      'alembic.ini',
      'data',
    ]);
    const diff = execFileSync(
      'git',
      ['diff', '--stat', provenance.commit, '--', ...provenance.backend_paths],
      { cwd: REPO_ROOT, encoding: 'utf8' },
    );
    expect(diff).toBe('');
  });
});

describe('the generated OpenAPI types', () => {
  it('are exactly what openapi-typescript generates from the recorded schema', () => {
    const generated = execFileSync(
      process.execPath,
      ['node_modules/openapi-typescript/bin/cli.js', `${FIXTURE_DIR}openapi.json`],
      { cwd: `${REPO_ROOT}frontend`, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
    );
    const committed = readFileSync(`${REPO_ROOT}frontend/src/api/generated/openapi.d.ts`, 'utf8');
    expect(committed).toBe(generated);
  });
});
