/**
 * The roster, the rooms, evidence records and timestamps (spec §7.8, §8.4, §9.1, §9.2, §9.13).
 */

import { describe, expect, it } from 'vitest';

import type { Customer, Document } from '@/api/schemas/entities';
import { ROLE_LINES } from '@/copy';
import { formatDuration, formatTimestamp } from '@/domain/dates';
import { entityTypeOf, findRecord, recordFields } from '@/domain/records';
import {
  FIXED_AGENTS,
  ROOMS,
  agentById,
  connectorAgent,
  isLocked,
  isMockSource,
  rosterFor,
} from '@/domain/roster';

import { recordedBody, recordedEntities } from '../support/fixtures';

const sources = recordedBody<{ sources: { source: string }[] }>(
  'sources.json',
  'GET',
  '/api/v1/sources',
).sources;

describe('the roster (§9.2)', () => {
  it('puts one connector per recorded source first, in API order, then the fixed agents', () => {
    const roster = rosterFor(sources);
    expect(roster.map((agent) => agent.tag)).toEqual([
      'CSV_DEMO_AGENT',
      'ODOO_MOCK_AGENT',
      'REST_MOCK_AGENT',
      'MEMORY',
      'LINKER_AGENT',
      'SIGNALS_AGENT',
      'SALES_AGENT',
      'SUPPORT_AGENT',
      'RECONCILER_AGENT',
      'BRIEF_WRITER',
      'CEO',
    ]);
    expect(roster.map((agent) => agent.id)).toEqual([
      'csv_demo',
      'odoo_mock',
      'rest_mock',
      'memory',
      'linker',
      'signals',
      'sales',
      'support',
      'reconciler',
      'brief-writer',
      'ceo',
    ]);
  });

  it('gives each agent its Appendix A role line', () => {
    expect(connectorAgent('csv_demo')).toMatchObject({
      kind: 'connector',
      module: 'app/connectors/*',
      role: ROLE_LINES.connector,
      room: 'data-dock',
    });
    const roles = FIXED_AGENTS.map((agent) => agent.role);
    expect(new Set(roles).size).toBe(FIXED_AGENTS.length);
    expect(roles.every((role) => (Object.values(ROLE_LINES) as string[]).includes(role))).toBe(
      true,
    );
  });

  it('keeps a fixed id for its agent when a source takes the same name', () => {
    const roster = rosterFor([{ source: 'memory' }, { source: 'csv_demo' }]);
    expect(roster.filter((agent) => agent.id === 'memory').map((agent) => agent.kind)).toEqual([
      'memory',
    ]);
    expect(agentById(roster, 'csv_demo')?.kind).toBe('connector');
    expect(agentById(roster, 'nobody')).toBeNull();
  });

  it('knows the local mock servers by their source names (§16)', () => {
    expect(sources.map((item) => [item.source, isMockSource(item.source)])).toEqual([
      ['csv_demo', false],
      ['odoo_mock', true],
      ['rest_mock', true],
    ]);
  });

  it('opens the eight VS-01 rooms and locks VS-02 to VS-05 (D-F-4)', () => {
    expect(ROOMS.filter((room) => !isLocked(room))).toHaveLength(8);
    expect(ROOMS.filter(isLocked).map((room) => [room.name, room.opensWith])).toEqual([
      ['Pipeline Room', 2],
      ['Account 360', 3],
      ['War Room', 4],
      ['Copilot Desk', 5],
    ]);
    const rooms = new Set(ROOMS.map((room) => room.id));
    expect(FIXED_AGENTS.every((agent) => rooms.has(agent.room))).toBe(true);
  });
});

describe('evidence records (§8.4)', () => {
  const customers = recordedEntities<{ items: Customer[] }>('customers').items;

  it('opens only the seven entity lists', () => {
    expect(entityTypeOf('support_tickets')).toBe('support_tickets');
    expect(entityTypeOf('documents')).toBe('documents');
    expect(entityTypeOf('tickets')).toBeNull();
  });

  it('finds a record by source system and source id', () => {
    const [customer] = customers as [Customer];
    expect(findRecord(customers, 'csv_demo', customer.source_id)).toBe(customer);
    expect(findRecord(customers, 'rest_mock', customer.source_id)).toBeNull();
  });

  it('lists every field as the API stated it', () => {
    const [document] = recordedEntities<{ items: Document[] }>('documents').items as [Document];
    const fields = recordFields({ ...document, title: null });
    expect(fields.map((field) => field.name)).toEqual(Object.keys(document));
    expect(fields.find((field) => field.name === 'title')?.value).toBe('null');
    expect(recordFields({ is_active: true, count: 3 })).toEqual([
      { name: 'is_active', value: 'true' },
      { name: 'count', value: '3' },
    ]);
  });
});

describe('timestamps (§7.8)', () => {
  it('shows a timestamp in the given zone, with its UTC form', () => {
    const view = formatTimestamp('2026-09-28T01:55:24.923Z', {
      locale: 'en-GB',
      timeZone: 'Asia/Kolkata',
    });
    expect(view.utc).toBe('2026-09-28 01:55:24 UTC');
    expect(view.local).toContain('07:25:24');
  });

  it('uses the viewer zone by default and refuses a non-timestamp', () => {
    expect(formatTimestamp('2026-09-28T00:00:00+00:00').utc).toBe('2026-09-28 00:00:00 UTC');
    expect(() => formatTimestamp('yesterday')).toThrow(/not a timestamp/);
  });

  it('shows a duration in whole milliseconds', () => {
    expect(formatDuration(12.6)).toBe('13 ms');
  });
});
