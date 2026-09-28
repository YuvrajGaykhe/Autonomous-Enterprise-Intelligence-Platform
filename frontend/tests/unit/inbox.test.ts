/**
 * Snapshots, the inbox and bands (spec §7.1, §7.2, R-F-2, AC-F-4), on the recorded lists.
 */

import { describe, expect, it } from 'vitest';

import type { Customer } from '@/api/schemas/entities';
import type { AssessmentListItem, BriefResponse } from '@/api/schemas/risk';
import { BANDS, BANDS_HIGHEST_FIRST, bandCounts, describeBandCounts } from '@/domain/bands';
import {
  chooseSnapshot,
  customerKey,
  customerNames,
  groupSnapshots,
  inboxRows,
  pendingCount,
  selectedRow,
  shortFingerprint,
  snapshotBriefIds,
  type Snapshot,
} from '@/domain/inbox';

import {
  autoRun,
  recordedAssessmentList,
  recordedBriefs,
  recordedEntities,
} from '../support/fixtures';

const list = recordedAssessmentList<{ items: AssessmentListItem[] }>().items;
const customers = recordedEntities<{ items: Customer[] }>('customers').items;
const briefs = new Map(
  recordedBriefs().map((exchange) => {
    const brief = exchange.body as BriefResponse;
    return [brief.id, brief] as const;
  }),
);
const names = customerNames(customers);

function only<T>(items: readonly T[]): T {
  expect(items).toHaveLength(1);
  return items[0] as T;
}

/** A copy of an item in another snapshot: same customer, another fingerprint. */
function inOtherSnapshot(item: AssessmentListItem, fingerprint: string): AssessmentListItem {
  return { ...item, id: item.id.replace(/^./, 'f'), layer1_fingerprint: fingerprint };
}

describe('bands (§7.1, D-F-2)', () => {
  it('orders NONE < WATCH < ELEVATED < CRITICAL, and lists counts highest first', () => {
    expect(BANDS).toEqual(['NONE', 'WATCH', 'ELEVATED', 'CRITICAL']);
    expect(BANDS_HIGHEST_FIRST).toEqual(['CRITICAL', 'ELEVATED', 'WATCH', 'NONE']);
  });

  it('counts customers per band over the recorded snapshot, omitting zero counts', () => {
    const counts = bandCounts(list);
    expect(counts).toEqual([
      { band: 'CRITICAL', count: 1 },
      { band: 'WATCH', count: 2 },
      { band: 'NONE', count: 47 },
    ]);
    expect(describeBandCounts(counts)).toBe('1 CRITICAL · 2 WATCH · 47 NONE');
    expect(bandCounts([])).toEqual([]);
  });
});

describe('snapshots (R-F-2)', () => {
  it('groups the recorded list into one snapshot keyed by as_of, fingerprint and versions', () => {
    const snapshot = only(groupSnapshots(list));
    expect(snapshot.key).toEqual({
      as_of: '2026-09-18',
      source_system: 'csv_demo',
      layer1_fingerprint: '1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00',
      rules_version: 1,
      linker_version: '1',
    });
    expect(snapshot.items).toHaveLength(50);
    expect(shortFingerprint(snapshot.key.layer1_fingerprint)).toBe('1d891b0b543f');
  });

  it('keeps blocks of two snapshots apart, in order of first appearance', () => {
    const other = 'a'.repeat(64);
    const interleaved = [
      ...list.slice(0, 2),
      ...list.slice(0, 2).map((item) => inOtherSnapshot(item, other)),
    ];
    const snapshots = groupSnapshots(interleaved);
    expect(snapshots.map((snapshot) => snapshot.key.layer1_fingerprint)).toEqual([
      list[0]?.layer1_fingerprint,
      other,
    ]);
    expect(snapshots.map((snapshot) => snapshot.items.length)).toEqual([2, 2]);
    expect(new Set(snapshots.map((snapshot) => snapshot.id)).size).toBe(2);
  });

  it('chooses the URL snapshot, else the run snapshot, else the first; null when none exists', () => {
    const other = `b${'0'.repeat(63)}`;
    const second = list.slice(0, 3).map((item) => inOtherSnapshot(item, other));
    const snapshots = groupSnapshots([...list, ...second]);
    const [first, run] = snapshots as [Snapshot, Snapshot];

    expect(chooseSnapshot(snapshots, { fingerprintParam: null, runAssessmentIds: [] })).toBe(first);
    expect(
      chooseSnapshot(snapshots, {
        fingerprintParam: null,
        runAssessmentIds: [second[1]?.id ?? ''],
      }),
    ).toBe(run);
    expect(
      chooseSnapshot(snapshots, {
        fingerprintParam: shortFingerprint(first.key.layer1_fingerprint),
        runAssessmentIds: [second[1]?.id ?? ''],
      }),
    ).toBe(first);
    expect(
      chooseSnapshot(snapshots, { fingerprintParam: 'not-a-print', runAssessmentIds: ['nope'] }),
    ).toBe(first);
    expect(chooseSnapshot([], { fingerprintParam: null, runAssessmentIds: [] })).toBeNull();
  });
});

describe('the inbox rows (§7.2, AC-F-4)', () => {
  const snapshot = only(groupSnapshots(list));

  it('holds one row per brief, CUST-007 pinned CRITICAL and EXECUTIVE, then CUST-025 and CUST-036', () => {
    expect(snapshotBriefIds(snapshot)).toHaveLength(3);
    const rows = inboxRows(snapshot, briefs, names);
    expect(rows.map((row) => [row.customerId, row.band, row.executiveWorthy])).toEqual([
      ['CUST-007', 'CRITICAL', true],
      ['CUST-025', 'WATCH', false],
      ['CUST-036', 'WATCH', false],
    ]);
    expect(rows[0]).toMatchObject({
      customerName: 'Meridian Textiles',
      decisionStatus: 'PENDING',
      versions: null,
    });
    expect(pendingCount(rows)).toBe(3);
  });

  it('keeps API order inside each group while moving executive-worthy rows first, stably', () => {
    const [top, ...rest] = snapshot.items as [AssessmentListItem, ...AssessmentListItem[]];
    const reordered: Snapshot = {
      ...snapshot,
      items: [...rest.filter((item) => item.brief_ids.length > 0), top],
    };
    const rows = inboxRows(reordered, briefs, names);
    expect(rows.map((row) => row.customerId)).toEqual(['CUST-007', 'CUST-025', 'CUST-036']);
    const noneExecutive: Snapshot = {
      ...snapshot,
      items: snapshot.items.map((item) => ({ ...item, executive_worthy: false })),
    };
    expect(inboxRows(noneExecutive, briefs, names).map((row) => row.customerId)).toEqual([
      'CUST-007',
      'CUST-025',
      'CUST-036',
    ]);
  });

  it('shows policy and template versions only when an assessment has more than one brief', () => {
    const [top] = snapshot.items as [AssessmentListItem];
    const briefed = snapshot.items.filter((item) => item.brief_ids.length > 0);
    const extraId = briefed[1]?.brief_ids[0] ?? '';
    const doubled: Snapshot = {
      ...snapshot,
      items: [{ ...top, brief_ids: [...top.brief_ids, extraId] }],
    };
    const rows = inboxRows(doubled, briefs, names);
    expect(rows).toHaveLength(2);
    expect(rows.every((row) => row.versions !== null)).toBe(true);
    expect(rows[0]?.versions).toEqual({ policy: 1, template: '1' });
  });

  it('shows the id alone when no name matches, and no id when the list has none', () => {
    const [top] = snapshot.items as [AssessmentListItem];
    const unnamed: Snapshot = {
      ...snapshot,
      items: [top, { ...top, id: `x${top.id.slice(1)}`, customer_source_id: null }],
    };
    const rows = inboxRows(unnamed, briefs, new Map());
    expect(rows.map((row) => [row.customerId, row.customerName])).toEqual([
      ['CUST-007', null],
      [null, null],
    ]);
  });

  it('matches names on source system and source id together', () => {
    const [customer] = customers as [Customer];
    expect(names.get(customerKey(customer.source_system, customer.source_id))).toBe(customer.name);
    expect(names.get(customerKey('another_source', customer.source_id))).toBeUndefined();
  });

  it('never renders a row whose brief is not loaded', () => {
    expect(() => inboxRows(snapshot, new Map(), names)).toThrow(/is not loaded/);
  });

  it('selects the chosen brief when it is in the inbox, else the first row, else nothing', () => {
    const rows = inboxRows(snapshot, briefs, names);
    expect(selectedRow(rows, rows[2]?.briefId ?? null)).toBe(rows[2]);
    expect(selectedRow(rows, 'elsewhere')).toBe(rows[0]);
    expect(selectedRow(rows, null)).toBe(rows[0]);
    expect(selectedRow([], null)).toBeNull();
  });

  it('builds the Auto snapshot from its own recorded list', () => {
    const [, detail, autoList] = autoRun();
    const asOf = (detail?.body as { as_of: string }).as_of;
    const items = (autoList?.body as { items: AssessmentListItem[] }).items;
    const autoSnapshot = only(groupSnapshots(items));
    expect(autoSnapshot.key.as_of).toBe(asOf);
    expect(snapshotBriefIds(autoSnapshot).length).toBeGreaterThan(0);
  });
});
