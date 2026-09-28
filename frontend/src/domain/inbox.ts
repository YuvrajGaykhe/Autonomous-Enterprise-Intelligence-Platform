/**
 * Snapshots and the CEO inbox (spec §7.2, R-F-2, D-F-3).
 *
 * `GET /risk/assessments` orders by `as_of`, then by fingerprint and versions, and only then by the
 * ranking key (DERIVED, `_LISTING_ORDER` in `app/persistence/repositories/risk_queries.py`). Two
 * snapshots at one `as_of` therefore arrive in blocks, and the inbox shows exactly one of them.
 * Inside a snapshot the API order is the ranking order, so it is kept; executive-worthy rows are
 * then moved first, stably.
 */

import type { AssessmentListItem, BriefResponse } from '@/api/schemas/risk';
import type { Customer } from '@/api/schemas/entities';

/** The characters of a fingerprint the URL and the selector show (§8.1). */
export const SHORT_FINGERPRINT = 12;

export interface SnapshotKey {
  as_of: string;
  source_system: string;
  layer1_fingerprint: string;
  rules_version: number;
  linker_version: string;
}

export interface Snapshot {
  /** A stable text form of the key, for React keys and selectors. */
  id: string;
  key: SnapshotKey;
  /** The snapshot's assessments, in API order. */
  items: AssessmentListItem[];
}

export function shortFingerprint(fingerprint: string): string {
  return fingerprint.slice(0, SHORT_FINGERPRINT);
}

function keyOf(item: AssessmentListItem): SnapshotKey {
  return {
    as_of: item.as_of,
    source_system: item.source_system,
    layer1_fingerprint: item.layer1_fingerprint,
    rules_version: item.rules_version,
    linker_version: item.linker_version,
  };
}

function idOf(key: SnapshotKey): string {
  return [
    key.as_of,
    key.source_system,
    key.layer1_fingerprint,
    key.rules_version,
    key.linker_version,
  ].join('|');
}

/** Group a list into snapshots, in the order each snapshot first appears. */
export function groupSnapshots(items: readonly AssessmentListItem[]): Snapshot[] {
  const byId = new Map<string, Snapshot>();
  for (const item of items) {
    const key = keyOf(item);
    const id = idOf(key);
    const snapshot = byId.get(id) ?? { id, key, items: [] };
    snapshot.items.push(item);
    byId.set(id, snapshot);
  }
  return [...byId.values()];
}

export interface SnapshotChoice {
  /** The `snapshot` URL parameter: the first twelve characters of a fingerprint. */
  fingerprintParam: string | null;
  /** The assessment ids a run in this browser session returned. */
  runAssessmentIds: readonly string[];
}

/**
 * The one snapshot the inbox shows: the one the URL names, else the one containing this
 * session's run, else the first in API order. Null when there is no snapshot at all.
 */
export function chooseSnapshot(
  snapshots: readonly Snapshot[],
  choice: SnapshotChoice,
): Snapshot | null {
  const named = snapshots.find(
    (snapshot) => shortFingerprint(snapshot.key.layer1_fingerprint) === choice.fingerprintParam,
  );
  if (named !== undefined) return named;
  const ran = new Set(choice.runAssessmentIds);
  const fromRun = snapshots.find((snapshot) => snapshot.items.some((item) => ran.has(item.id)));
  return fromRun ?? snapshots[0] ?? null;
}

/** Every brief id in a snapshot, in row order before pinning. */
export function snapshotBriefIds(snapshot: Snapshot): string[] {
  return snapshot.items.flatMap((item) => item.brief_ids);
}

/** Customers are matched on their source system and source id. */
export function customerKey(sourceSystem: string, sourceId: string): string {
  return `${sourceSystem}\u0000${sourceId}`;
}

/** Customer names by `customerKey`. */
export function customerNames(customers: readonly Customer[]): Map<string, string> {
  return new Map(
    customers.map((customer) => [
      customerKey(customer.source_system, customer.source_id),
      customer.name,
    ]),
  );
}

export interface InboxRow {
  briefId: string;
  assessmentId: string;
  customerId: string | null;
  /** The customer's name from `GET /entities/customers`; null when none matched. */
  customerName: string | null;
  band: AssessmentListItem['band'];
  executiveWorthy: boolean;
  decisionStatus: BriefResponse['decision_status'];
  /** Shown only when the assessment has more than one brief (§7.2). */
  versions: { policy: number; template: string } | null;
}

/**
 * One row per brief of the snapshot, in API order, executive-worthy rows stably first. Every brief
 * must be loaded: partially loaded data is never rendered.
 */
export function inboxRows(
  snapshot: Snapshot,
  briefs: ReadonlyMap<string, BriefResponse>,
  names: ReadonlyMap<string, string>,
): InboxRow[] {
  const rows = snapshot.items.flatMap((item) =>
    item.brief_ids.map((briefId): InboxRow => {
      const brief = briefs.get(briefId);
      if (brief === undefined) throw new Error(`brief ${briefId} is not loaded`);
      const customerId = item.customer_source_id;
      return {
        briefId,
        assessmentId: item.id,
        customerId,
        customerName:
          customerId === null
            ? null
            : (names.get(customerKey(item.source_system, customerId)) ?? null),
        band: item.band,
        executiveWorthy: item.executive_worthy,
        decisionStatus: brief.decision_status,
        versions:
          item.brief_ids.length > 1
            ? { policy: brief.policy_version, template: brief.template_version }
            : null,
      };
    }),
  );
  return [
    ...rows.filter((row) => row.executiveWorthy),
    ...rows.filter((row) => !row.executiveWorthy),
  ];
}

/** The selected brief's row: the one chosen, when it is in the inbox, else the first (§9.2). */
export function selectedRow(
  rows: readonly InboxRow[],
  selectedBriefId: string | null,
): InboxRow | null {
  return rows.find((row) => row.briefId === selectedBriefId) ?? rows[0] ?? null;
}

/** How many rows still wait for the CEO's decision. */
export function pendingCount(rows: readonly InboxRow[]): number {
  return rows.filter((row) => row.decisionStatus === 'PENDING').length;
}
