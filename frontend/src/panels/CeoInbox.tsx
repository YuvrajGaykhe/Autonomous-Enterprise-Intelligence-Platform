/**
 * The CEO inbox (spec §7.2, D-F-3): one snapshot, one row per brief, in the API's ranking order
 * with executive-worthy briefs pinned first. Inbox items are briefs, never "tickets".
 */

import { useId } from 'react';
import { Link, useLocation, type To } from 'react-router';

import { COPY } from '@/copy';
import { useInbox, useSnapshotParam, type InboxState } from '@/data/useInbox';
import { bandCounts, describeBandCounts } from '@/domain/bands';
import { pendingCount, shortFingerprint, type InboxRow, type Snapshot } from '@/domain/inbox';
import { RunAssessmentButton } from '@/hud/RunAssessmentControls';
import { useAsOf } from '@/hud/useAsOf';
import { useSession } from '@/state/session';
import { EmptyState, ErrorState, LoadingState } from '@/states/states';

import { ApiXray } from './ApiXray';
import { BandChip, BandLegend, DecisionStatusChip, ExecutiveBadge } from './chips';

/** Under Auto, before any Auto run in this session (PROPOSED copy). */
export const AUTO_UNRESOLVED =
  'Auto takes its date from the latest support ticket when an assessment runs. Run one from the top bar, or choose a date.';

function snapshotLabel(snapshot: Snapshot): string {
  const { key } = snapshot;
  return `${shortFingerprint(key.layer1_fingerprint)} · rules ${key.rules_version} · linker ${key.linker_version}`;
}

function SnapshotHeader({
  asOf,
  snapshots,
  snapshot,
}: {
  asOf: string;
  snapshots: readonly Snapshot[];
  snapshot: Snapshot;
}) {
  const [, setSnapshotParam] = useSnapshotParam();
  const selectId = useId();
  return (
    <div className="space-y-2 text-sm">
      <p className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          <span className="text-muted-foreground">as_of</span>{' '}
          <span className="font-mono">{asOf}</span>
        </span>
        <span>
          <span className="text-muted-foreground">snapshot</span>{' '}
          <span className="font-mono" title={snapshot.key.layer1_fingerprint}>
            {snapshotLabel(snapshot)}
          </span>
        </span>
        <span>
          <span className="text-muted-foreground">customers</span>{' '}
          {describeBandCounts(bandCounts(snapshot.items))}
        </span>
      </p>
      {snapshots.length > 1 && (
        <div className="flex items-center gap-2">
          <label htmlFor={selectId} className="text-muted-foreground">
            Snapshot at this date
          </label>
          <select
            id={selectId}
            className="h-8 rounded-md border bg-card px-2 font-mono text-xs"
            value={snapshot.id}
            onChange={(event) => {
              const chosen = snapshots.find((item) => item.id === event.target.value);
              if (chosen) setSnapshotParam(shortFingerprint(chosen.key.layer1_fingerprint));
            }}
          >
            {snapshots.map((item) => (
              <option key={item.id} value={item.id}>
                {snapshotLabel(item)}
              </option>
            ))}
          </select>
        </div>
      )}
      <BandLegend />
    </div>
  );
}

function Row({ row, hrefFor }: { row: InboxRow; hrefFor: (briefId: string) => To }) {
  const selectBrief = useSession((state) => state.selectBrief);
  return (
    <li>
      <Link
        to={hrefFor(row.briefId)}
        onClick={() => selectBrief(row.briefId)}
        className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-card px-3 py-2 hover:bg-muted"
        data-testid="inbox-row"
      >
        <span className="flex items-center gap-1.5">
          <BandChip band={row.band} />
          {row.executiveWorthy && (
            <>
              <span aria-hidden="true">·</span>
              <ExecutiveBadge />
            </>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="font-medium">
            {row.customerName ?? row.customerId ?? 'Unnamed customer'}
          </span>{' '}
          <span className="font-mono text-xs text-muted-foreground">
            {row.customerId ?? 'no customer id'}
          </span>
          {row.versions !== null && (
            <span className="ml-2 font-mono text-xs text-muted-foreground">
              policy {row.versions.policy} · template {row.versions.template}
            </span>
          )}
        </span>
        <DecisionStatusChip status={row.decisionStatus} />
      </Link>
    </li>
  );
}

function InboxBody({ state, hrefFor }: { state: InboxState; hrefFor: (briefId: string) => To }) {
  switch (state.status) {
    case 'auto-unresolved':
      return <EmptyState message={AUTO_UNRESOLVED} />;
    case 'loading':
      return <LoadingState label="the CEO inbox" lines={4} />;
    case 'error':
      return <ErrorState error={state.error} onRetry={state.retry} />;
    case 'ready': {
      if (state.snapshot === null) {
        return (
          <div className="space-y-3">
            <EmptyState message={COPY.inboxNoAssessment} />
            <RunAssessmentButton />
          </div>
        );
      }
      return (
        <div className="space-y-3">
          <SnapshotHeader asOf={state.asOf} snapshots={state.snapshots} snapshot={state.snapshot} />
          {state.rows.length === 0 ? (
            <EmptyState message={COPY.inboxNoBrief} />
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                {state.rows.length} {state.rows.length === 1 ? 'brief' : 'briefs'},{' '}
                {pendingCount(state.rows)} awaiting your decision.
              </p>
              <ol aria-label="Briefs, executive-worthy first" className="space-y-2">
                {state.rows.map((row) => (
                  <Row key={row.briefId} row={row} hrefFor={hrefFor} />
                ))}
              </ol>
            </>
          )}
        </div>
      );
    }
  }
}

/** The inbox at the HUD's `as_of`, with its requests. */
export function CeoInbox({ hrefFor }: { hrefFor: (briefId: string) => To }) {
  const [asOf] = useAsOf();
  const [snapshotParam] = useSnapshotParam();
  const state = useInbox(asOf, snapshotParam);
  return (
    <div className="space-y-4">
      <InboxBody state={state} hrefFor={hrefFor} />
      <ApiXray calls={state.calls} />
    </div>
  );
}

/** Links to a brief keep the page's query, so `as_of` and the snapshot travel with them. */
export function useBriefHref(pathname: (briefId: string) => string): (briefId: string) => To {
  const { search } = useLocation();
  return (briefId: string) => ({ pathname: pathname(briefId), search });
}
