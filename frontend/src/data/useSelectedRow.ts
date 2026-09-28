/**
 * The selected customer (spec §9.2): panels that show one customer's data show the selected
 * brief's customer. That is the brief the user last opened when it is in the inbox shown now, and
 * otherwise the inbox's first row.
 */

import type { ApiCall } from '@/api/client';
import { selectedRow, type InboxRow, type Snapshot } from '@/domain/inbox';
import { useAsOf } from '@/hud/useAsOf';
import { useSession } from '@/state/session';

import { useInbox, useSnapshotParam } from './useInbox';

export type SelectedRowState =
  | { status: 'auto-unresolved'; calls: ApiCall[] }
  | { status: 'loading'; calls: ApiCall[] }
  | { status: 'error'; error: unknown; retry: () => void; calls: ApiCall[] }
  | { status: 'no-assessment'; calls: ApiCall[] }
  | { status: 'no-brief'; calls: ApiCall[] }
  | {
      status: 'ready';
      row: InboxRow;
      asOf: string;
      snapshot: Snapshot;
      names: ReadonlyMap<string, string>;
      calls: ApiCall[];
    };

export function useSelectedRow(): SelectedRowState {
  const [asOf] = useAsOf();
  const [snapshotParam] = useSnapshotParam();
  const inbox = useInbox(asOf, snapshotParam);
  const selectedBriefId = useSession((state) => state.selectedBriefId);
  if (inbox.status !== 'ready') return inbox;
  if (inbox.snapshot === null) return { status: 'no-assessment', calls: inbox.calls };
  const row = selectedRow(inbox.rows, selectedBriefId);
  if (row === null) return { status: 'no-brief', calls: inbox.calls };
  return {
    status: 'ready',
    row,
    asOf: inbox.asOf,
    snapshot: inbox.snapshot,
    names: inbox.names,
    calls: inbox.calls,
  };
}
