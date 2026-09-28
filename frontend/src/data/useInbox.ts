/**
 * The CEO inbox's data (spec §7.2, R-F-2): the assessment list at the shown `as_of`, the customer
 * names, then one `GET /risk/briefs/{id}` per brief of the one snapshot shown.
 *
 * The inbox renders only when every one of those requests has succeeded: partially loaded data is
 * never rendered. Auto has no date of its own until a run resolves one, so under Auto the inbox
 * shows the snapshot of this session's Auto run, and otherwise says how to get one.
 */

import { useQueries, useQuery } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

import type { ApiCall } from '@/api/client';
import { assessmentsQuery, briefQuery, entitiesQuery } from '@/api/queries';
import type { Brief } from '@/api/risk';
import type { BriefResponse } from '@/api/schemas/risk';
import type { AsOf } from '@/domain/asOf';
import {
  chooseSnapshot,
  customerNames,
  groupSnapshots,
  inboxRows,
  snapshotBriefIds,
  type InboxRow,
  type Snapshot,
} from '@/domain/inbox';
import { useSession, type LastRun } from '@/state/session';

export const SNAPSHOT_PARAM = 'snapshot';

export type InboxState =
  | { status: 'auto-unresolved'; calls: ApiCall[] }
  | { status: 'loading'; calls: ApiCall[] }
  | { status: 'error'; error: unknown; retry: () => void; calls: ApiCall[] }
  | {
      status: 'ready';
      asOf: string;
      snapshots: Snapshot[];
      snapshot: Snapshot | null;
      rows: InboxRow[];
      names: ReadonlyMap<string, string>;
      calls: ApiCall[];
    };

/** The date the inbox shows: the chosen one, or the one this session's Auto run resolved to. */
export function shownDate(asOf: AsOf, lastRun: LastRun | null): string | null {
  if (asOf.kind === 'date') return asOf.date;
  return lastRun?.requested.kind === 'auto' ? lastRun.asOf : null;
}

/** The `snapshot` URL parameter (§8.1) and a setter that clears it with null. */
export function useSnapshotParam(): [string | null, (next: string | null) => void] {
  const [params, setParams] = useSearchParams();
  const set = useCallback(
    (next: string | null) =>
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          if (next === null) updated.delete(SNAPSHOT_PARAM);
          else updated.set(SNAPSHOT_PARAM, next);
          return updated;
        },
        { replace: true },
      ),
    [setParams],
  );
  return [params.get(SNAPSHOT_PARAM), set];
}

export function useInbox(asOf: AsOf, snapshotParam: string | null): InboxState {
  const lastRun = useSession((state) => state.lastRun);
  const date = shownDate(asOf, lastRun);
  const list = useQuery({ ...assessmentsQuery(date ?? ''), enabled: date !== null });
  const customers = useQuery(entitiesQuery('customers'));

  const snapshots = list.data === undefined ? [] : groupSnapshots(list.data.data);
  const snapshot = chooseSnapshot(snapshots, {
    fingerprintParam: snapshotParam,
    runAssessmentIds: lastRun !== null && lastRun.asOf === date ? lastRun.assessmentIds : [],
  });
  const briefIds = snapshot === null ? [] : snapshotBriefIds(snapshot);
  const briefs = useQueries({ queries: briefIds.map((id) => briefQuery(id)) });

  const calls = [
    ...(list.data?.calls ?? []),
    ...(customers.data?.calls ?? []),
    ...briefs.flatMap((brief) => brief.data?.calls ?? []),
  ];
  if (date === null) return { status: 'auto-unresolved', calls };

  const failed = [list, customers, ...briefs].filter((query) => query.isError);
  if (failed.length > 0) {
    return {
      status: 'error',
      error: failed[0]?.error,
      retry: () => failed.forEach((query) => void query.refetch()),
      calls,
    };
  }
  if (
    list.data === undefined ||
    customers.data === undefined ||
    briefs.some((brief) => brief.data === undefined)
  ) {
    return { status: 'loading', calls };
  }

  const loaded = new Map<string, BriefResponse>(
    briefs.map((brief) => {
      const data = brief.data?.data as Brief;
      return [data.response.id, data.response];
    }),
  );
  const names = customerNames(customers.data.data);
  return {
    status: 'ready',
    asOf: date,
    snapshots,
    snapshot,
    rows: snapshot === null ? [] : inboxRows(snapshot, loaded, names),
    names,
    calls,
  };
}
