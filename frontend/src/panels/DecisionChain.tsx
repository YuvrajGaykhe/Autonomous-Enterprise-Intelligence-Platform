/**
 * The decision chain (spec §8.6): a numbered timeline, first to head. Each entry shows its actor,
 * decision, note, time and the first twelve characters of the payload hash it was bound to.
 */

import type { UseQueryResult } from '@tanstack/react-query';
import { CircleCheck, CircleX } from 'lucide-react';

import type { Fetched } from '@/api/queries';
import type { DecisionResponse } from '@/api/schemas/risk';
import { COPY } from '@/copy';
import { chainEntries } from '@/domain/decisionChain';
import { formatTimestamp } from '@/domain/dates';
import { SHORT_FINGERPRINT } from '@/domain/inbox';
import { EmptyState, QueryView } from '@/states/states';

export function decisionAnchor(id: string): string {
  return `decision-${id}`;
}

function Entry({ entry }: { entry: ReturnType<typeof chainEntries>[number] }) {
  const { decision } = entry;
  const time = formatTimestamp(decision.decided_at);
  const Icon = decision.decision === 'APPROVED' ? CircleCheck : CircleX;
  return (
    <li id={decisionAnchor(decision.id)} className="relative border-l-2 pb-4 pl-4 last:pb-0">
      <p className="flex flex-wrap items-center gap-2">
        <span className="text-lg leading-none" aria-label={`Decision ${entry.ordinal}`}>
          {entry.mark}
        </span>
        <span
          className={
            decision.decision === 'APPROVED'
              ? 'inline-flex items-center gap-1 font-semibold text-ok'
              : 'inline-flex items-center gap-1 font-semibold text-bad'
          }
        >
          <Icon aria-hidden="true" className="size-4" />
          {decision.decision}
        </span>
        <span className="text-sm">by {decision.actor}</span>
      </p>
      <p className="mt-1 text-sm whitespace-pre-wrap">
        {decision.note ?? <span className="text-muted-foreground">No note.</span>}
      </p>
      <p className="mt-1 flex flex-wrap gap-x-3 font-mono text-xs text-muted-foreground">
        <time dateTime={decision.decided_at} title={time.utc}>
          {time.local}
        </time>
        <span title={decision.payload_hash}>
          hash {decision.payload_hash.slice(0, SHORT_FINGERPRINT)}
        </span>
        {entry.supersedes !== null && (
          <a className="underline" href={`#${decisionAnchor(entry.supersedes.id)}`}>
            supersedes {entry.supersedes.mark}
          </a>
        )}
      </p>
    </li>
  );
}

export function DecisionChainView({ items }: { items: readonly DecisionResponse[] }) {
  if (items.length === 0) return <EmptyState message={COPY.emptyDecisionChain} art="corkboard" />;
  return (
    <ol aria-label="Decision chain, first to head" className="space-y-0">
      {chainEntries(items).map((entry) => (
        <Entry key={entry.decision.id} entry={entry} />
      ))}
    </ol>
  );
}

export function DecisionChain({ query }: { query: UseQueryResult<Fetched<DecisionResponse[]>> }) {
  return (
    <QueryView query={query} label="the decision chain">
      {({ data }) => <DecisionChainView items={data} />}
    </QueryView>
  );
}
